import json
import logging
import re

import httpx

from .db import one, pool, query
from .extract import chunk_text, extract_text
from .intents import normalize
from .settings import VOYAGE_API_KEY

log = logging.getLogger("karaguruka.rag")
VOYAGE_MODEL = "voyage-3.5"


def _embed(texts: list[str], input_type: str) -> list[list[float]] | None:
    if not VOYAGE_API_KEY:
        return None
    vectors: list[list[float]] = []
    for start in range(0, len(texts), 64):
        response = httpx.post(
            "https://api.voyageai.com/v1/embeddings",
            headers={"Authorization": f"Bearer {VOYAGE_API_KEY}"},
            json={"model": VOYAGE_MODEL, "input": texts[start : start + 64], "input_type": input_type, "output_dimension": 1024},
            timeout=60,
        )
        response.raise_for_status()
        vectors.extend(item["embedding"] for item in response.json()["data"])
    return vectors


def process_document(document_id: str) -> None:
    """Extracts and indexes a stored document. Indexing replaces the document's passages in one transaction."""
    doc = one("SELECT filename, title, file FROM documents WHERE id = %s", (document_id,))
    if not doc:
        return
    try:
        extracted = extract_text(doc["filename"], bytes(doc["file"]))
        pieces = [(page, content) for page, text in extracted.pages for content in chunk_text(text)]
        if not pieces:
            raise ValueError("Aucun texte lisible n'a été trouvé dans ce fichier.")
        embeddings = None
        try:
            embeddings = _embed([f"{doc['title']}\n{content}" for _, content in pieces], "document")
        except Exception:
            log.exception("Embedding failed, keyword search only")
        with pool.connection() as conn, conn.transaction():
            conn.execute("DELETE FROM chunks WHERE document_id = %s", (document_id,))
            for i, (page, content) in enumerate(pieces):
                conn.execute(
                    """INSERT INTO chunks (document_id, page, ordinal, content, tsv, embedding)
                       VALUES (%s, %s, %s, %s, to_tsvector('french', unaccent(%s)), %s::vector)""",
                    (document_id, page, i, content, f"{doc['title']} {content}", json.dumps(embeddings[i]) if embeddings else None),
                )
            conn.execute(
                "UPDATE documents SET status = 'ready', error = NULL, chunk_count = %s, page_count = %s, used_ocr = %s, updated_at = now() WHERE id = %s",
                (len(pieces), extracted.page_count, extracted.used_ocr, document_id),
            )
    except Exception as error:
        log.exception("Processing failed for document %s", document_id)
        query("UPDATE documents SET status = 'failed', error = %s, updated_at = now() WHERE id = %s RETURNING id", (str(error)[:500], document_id))


STOPWORDS = set(
    "a au aux avec ce ces comment dans de des du elle en est et etre il je j la le les leur lui ma mais me mes mon ne nos notre nous on ou par pas pour puis qu que quel quelle quelles quels qui sa se ses si son sur ta te tes ton tu un une vos votre vous y bonjour svp merci peux peut pouvez voudrais veux faut quoi combien".split()
)


def _terms(question: str) -> list[str]:
    seen = dict.fromkeys(re.findall(r"[a-z0-9]+", normalize(question)))
    return [t for t in seen if len(t) > 1 and t not in STOPWORDS]


def _coverage(terms: list[str], text: str) -> float:
    if not terms:
        return 0.0
    haystack = normalize(text)
    return sum(t[: max(4, len(t) - 2)] in haystack for t in terms) / len(terms)


VISIBLE = """d.status = 'ready' AND d.active AND d.audience = ANY(%(audiences)s)
  AND (d.effective_from IS NULL OR d.effective_from <= CURRENT_DATE)
  AND (d.expires_at IS NULL OR d.expires_at >= CURRENT_DATE)"""


def search(question: str, audiences: list[str], limit: int = 5) -> list[dict]:
    terms = _terms(question)
    keyword_rows = []
    if terms:
        keyword_rows = query(
            f"""SELECT c.id, c.document_id, d.title, c.page, c.content
                FROM chunks c JOIN documents d ON d.id = c.document_id
                WHERE {VISIBLE} AND c.tsv @@ to_tsquery('french', %(q)s)
                ORDER BY ts_rank_cd(c.tsv, to_tsquery('french', %(q)s)) DESC LIMIT 20""",
            {"audiences": audiences, "q": " | ".join(terms)},
        )
    vector_rows = []
    try:
        vectors = _embed([question], "query")
        if vectors:
            vector_rows = query(
                f"""SELECT c.id, c.document_id, d.title, c.page, c.content, 1 - (c.embedding <=> %(v)s::vector) AS similarity
                    FROM chunks c JOIN documents d ON d.id = c.document_id
                    WHERE {VISIBLE} AND c.embedding IS NOT NULL
                    ORDER BY c.embedding <=> %(v)s::vector LIMIT 20""",
                {"audiences": audiences, "v": json.dumps(vectors[0])},
            )
    except Exception:
        log.exception("Semantic search failed, keyword search only")

    # Reciprocal rank fusion: passages found by both searches rise to the top.
    merged: dict[int, dict] = {}
    for rows in (keyword_rows, vector_rows):
        for rank, row in enumerate(rows):
            entry = merged.setdefault(row["id"], {**row, "score": 0.0, "similarity": None})
            entry["score"] += 1 / (60 + rank)
            if row.get("similarity") is not None:
                entry["similarity"] = float(row["similarity"])
    for entry in merged.values():
        entry["coverage"] = _coverage(terms, f"{entry['title']} {entry['content']}")
        entry["id"] = str(entry["id"])
        entry["document_id"] = str(entry["document_id"])
    return sorted(merged.values(), key=lambda e: e["score"] + e["coverage"] / 10, reverse=True)[:limit]


def is_confident(passage: dict | None) -> bool:
    """Whether a passage is close enough to quote when Claude is not available to judge it."""
    if not passage:
        return False
    return passage["coverage"] >= 0.6 or (passage["similarity"] or 0) >= 0.55


def to_sources(passages: list[dict]) -> list[dict]:
    sources: dict[tuple, dict] = {}
    for p in passages:
        sources.setdefault((p["document_id"], p["page"]), {"document_id": p["document_id"], "title": p["title"], "page": p["page"]})
    return list(sources.values())


def extractive_answer(passage: dict, question: str) -> str:
    """Quotes the paragraphs of a passage that best match the question."""
    terms = _terms(question)
    # A paragraph often names its subject only in its heading ("## Crédit immobilier"), so the two are scored together.
    sections: list[str] = []
    heading = ""
    for block in re.split(r"\n\s*\n", passage["content"]):
        block = block.strip()
        if block.startswith("#"):
            heading = block.lstrip("#").strip()
        elif block:
            sections.append(f"{heading}\n{block}" if heading else block)
    if not sections:
        sections = [heading or passage["content"].strip()]
    best = max(_coverage(terms, s) for s in sections)
    # When no paragraph matches on its own, keep the start of the passage in reading order.
    chosen = [s for s in sections if _coverage(terms, s) == best][:2] if best > 0 else sections[:2]
    body = "\n\n".join(chosen)
    return f"{re.sub(r'\s\S*$', '', body[:700])}…" if len(body) > 700 else body
