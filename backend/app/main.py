import ipaddress
import logging
import threading
import time
from collections import defaultdict, deque
from contextlib import asynccontextmanager
from datetime import date
from pathlib import Path
from urllib.parse import quote
from uuid import UUID

from fastapi import BackgroundTasks, Depends, FastAPI, File, Form, HTTPException, Request, Response, UploadFile
from pydantic import BaseModel, Field

from . import auth, engine, llm, rag
from .db import one, pool, query
from .extract import ALLOWED_EXTENSIONS
from .settings import ADMIN_PASSWORD, AGENT_PASSWORD, BANK_NAME, BANK_NOTICE, HANDLE_MINUTES, MAX_UPLOAD_BYTES, VOYAGE_API_KEY

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("karaguruka.api")


@asynccontextmanager
async def lifespan(_: FastAPI):
    for name, password in (("ADMIN_PASSWORD", ADMIN_PASSWORD), ("AGENT_PASSWORD", AGENT_PASSWORD)):
        if password and len(password) < 12:
            raise RuntimeError(f"{name} must be at least 12 characters long.")
    # Processing runs inside this server, so anything still "processing" at startup was interrupted.
    query("UPDATE documents SET status = 'failed', error = 'Traitement interrompu. Remplacez le fichier pour relancer.' WHERE status = 'processing' RETURNING id")
    yield


app = FastAPI(title="Karaguruka AI", lifespan=lifespan)

# --- Sessions ---------------------------------------------------------------


class Login(BaseModel):
    password: str = Field(max_length=200)


LOGIN_WINDOW_SECONDS = 300
LOGIN_FAILURES_PER_IP = 5
# Past this many failures across all addresses, password checks run one at a time and a failure holds the
# slot for 2 seconds. That caps guessing at about 30 per minute from any number of addresses, while a correct
# password still succeeds as soon as a slot is free, so an attacker cannot lock staff out permanently.
LOGIN_FAILURES_ALERT = 50
_login_failures: dict[str, deque] = defaultdict(deque)
_login_slot = threading.Lock()


def _login_key(request: Request) -> str:
    # request.client is the direct peer. Behind a proxy, configure uvicorn's trusted proxies so this is the real client.
    host = request.client.host if request.client else "unknown"
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        return host
    if address.version == 4:
        return host
    # An IPv4 address written in IPv6 form is still one IPv4 client.
    if address.ipv4_mapped:
        return str(address.ipv4_mapped)
    # One IPv6 customer usually controls a whole /64, so those addresses count as one.
    return str(ipaddress.ip_network(f"{host}/64", strict=False))


def _recent_failures(key: str) -> int:
    failures = _login_failures[key]
    now = time.monotonic()
    while failures and now - failures[0] > LOGIN_WINDOW_SECONDS:
        failures.popleft()
    return len(failures)


@app.post("/api/login")
def login(body: Login, request: Request, response: Response):
    ip = _login_key(request)
    if _recent_failures(ip) >= LOGIN_FAILURES_PER_IP:
        log.warning("Login blocked after repeated failures from %s", ip)
        raise HTTPException(429, "Trop de tentatives. Réessayez dans quelques minutes.")
    under_attack = _recent_failures("*") >= LOGIN_FAILURES_ALERT
    if under_attack and not _login_slot.acquire(blocking=False):
        raise HTTPException(429, "Service très sollicité. Réessayez dans quelques secondes.")
    try:
        role = auth.role_for_password(body.password)
        if not role:
            _login_failures[ip].append(time.monotonic())
            _login_failures["*"].append(time.monotonic())
            log.warning("Failed login from %s", ip)
            if under_attack:
                log.error("Possible password guessing: %s failed logins in %s seconds", _recent_failures("*"), LOGIN_WINDOW_SECONDS)
            time.sleep(2 if under_attack else 0.5)
            raise HTTPException(401, "Mot de passe incorrect.")
    finally:
        if under_attack:
            _login_slot.release()
    auth.set_session(response, role)
    return {"role": role}


@app.post("/api/logout")
def logout(response: Response):
    auth.clear_session(response)
    return {"ok": True}


@app.get("/api/me")
def me(role: str | None = Depends(auth.read_role)):
    return {"role": role}


@app.get("/api/status")
def status():
    return {"claude": llm.has_claude(), "semantic_search": bool(VOYAGE_API_KEY), "bank_name": BANK_NAME, "notice": BANK_NOTICE}


# --- Customer assistant -----------------------------------------------------

_hits: dict[str, deque] = defaultdict(deque)
CHAT_LIMIT_PER_MINUTE = 30


def _rate_limit(request: Request) -> None:
    key = request.client.host if request.client else "unknown"
    hits = _hits[key]
    now = time.monotonic()
    while hits and now - hits[0] > 60:
        hits.popleft()
    if len(hits) >= CHAT_LIMIT_PER_MINUTE:
        raise HTTPException(429, "Trop de messages. Patientez une minute puis réessayez.")
    hits.append(now)


class ChatIn(BaseModel):
    conversation_id: UUID | None = None
    message: str = Field(min_length=1, max_length=2000)
    channel: str = Field(default="text", pattern="^(text|voice)$")


@app.post("/api/chat")
def chat(body: ChatIn, request: Request):
    _rate_limit(request)
    conversation_id = engine.ensure_conversation(str(body.conversation_id) if body.conversation_id else None, body.channel)
    return {"conversation_id": conversation_id, **engine.handle_message(conversation_id, body.message)}


@app.get("/api/conversations/{conversation_id}/messages")
def conversation_messages(conversation_id: UUID, after: int = 0):
    rows = query(
        "SELECT id, role, content, sources, created_at FROM messages WHERE conversation_id = %s AND id > %s ORDER BY id",
        (conversation_id, after),
    )
    state = one("SELECT status FROM conversations WHERE id = %s", (conversation_id,))
    if not state:
        raise HTTPException(404, "Conversation introuvable.")
    return {"messages": rows, "status": state["status"]}


# --- Documents (administrator) ----------------------------------------------

DOC_COLUMNS = "id, title, filename, mime, size_bytes, category, audience, status, error, active, effective_from, expires_at, version, page_count, chunk_count, used_ocr, uploaded_at, updated_at"


async def _read_upload(file: UploadFile) -> bytes:
    filename = file.filename or ""
    if Path(filename).suffix.lower() not in ALLOWED_EXTENSIONS:
        raise HTTPException(400, f"Format non pris en charge. Formats acceptés : {', '.join(sorted(ALLOWED_EXTENSIONS))}.")
    data = await file.read(MAX_UPLOAD_BYTES + 1)
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(413, "Fichier trop volumineux (25 Mo maximum).")
    if not data:
        raise HTTPException(400, "Ce fichier est vide.")
    return data


@app.get("/api/documents", dependencies=[Depends(auth.require_admin)])
def list_documents():
    return query(
        f"""SELECT {DOC_COLUMNS}, (SELECT count(embedding)::int FROM chunks c WHERE c.document_id = documents.id) AS embedded_count
            FROM documents ORDER BY uploaded_at DESC"""
    )


@app.post("/api/documents", status_code=201, dependencies=[Depends(auth.require_admin)])
async def upload_document(
    background: BackgroundTasks,
    file: UploadFile = File(...),
    title: str = Form(default=""),
    category: str = Form(default="Général"),
    audience: str = Form(default="public", pattern="^(public|internal)$"),
    effective_from: date | None = Form(default=None),
    expires_at: date | None = Form(default=None),
):
    data = await _read_upload(file)
    filename = Path(file.filename or "document").name
    doc = one(
        f"""INSERT INTO documents (title, filename, mime, size_bytes, file, category, audience, effective_from, expires_at)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING {DOC_COLUMNS}""",
        (title.strip() or Path(filename).stem, filename, file.content_type or "application/octet-stream", len(data), data, category.strip() or "Général", audience, effective_from, expires_at),
    )
    background.add_task(rag.process_document, str(doc["id"]))
    return doc


@app.post("/api/documents/{document_id}/replace", dependencies=[Depends(auth.require_admin)])
async def replace_document(document_id: UUID, background: BackgroundTasks, file: UploadFile = File(...)):
    data = await _read_upload(file)
    filename = Path(file.filename or "document").name
    # The new version and the removal of the old passages happen together, so the old text cannot outlive the file.
    with pool.connection() as conn, conn.transaction():
        doc = conn.execute(
            f"""UPDATE documents SET filename = %s, mime = %s, size_bytes = %s, file = %s, status = 'processing', error = NULL,
                chunk_count = 0, version = version + 1, updated_at = now() WHERE id = %s RETURNING {DOC_COLUMNS}""",
            (filename, file.content_type or "application/octet-stream", len(data), data, document_id),
        ).fetchone()
        conn.execute("DELETE FROM chunks WHERE document_id = %s", (document_id,))
    if not doc:
        raise HTTPException(404, "Document introuvable.")
    background.add_task(rag.process_document, str(document_id))
    return doc


class DocumentPatch(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    category: str | None = Field(default=None, min_length=1, max_length=80)
    audience: str | None = Field(default=None, pattern="^(public|internal)$")
    active: bool | None = None
    effective_from: date | None = None
    expires_at: date | None = None


@app.patch("/api/documents/{document_id}", dependencies=[Depends(auth.require_admin)])
def patch_document(document_id: UUID, body: DocumentPatch):
    changes = body.model_dump(exclude_unset=True)
    if not changes:
        raise HTTPException(400, "Aucune modification.")
    # Column names come from the DocumentPatch fields, never from the request text.
    assignments = ", ".join(f"{column} = %s" for column in changes)
    doc = one(f"UPDATE documents SET {assignments}, updated_at = now() WHERE id = %s RETURNING {DOC_COLUMNS}", [*changes.values(), document_id])
    if not doc:
        raise HTTPException(404, "Document introuvable.")
    return doc


@app.delete("/api/documents/{document_id}", dependencies=[Depends(auth.require_admin)])
def delete_document(document_id: UUID):
    if not one("DELETE FROM documents WHERE id = %s RETURNING id", (document_id,)):
        raise HTTPException(404, "Document introuvable.")
    return {"ok": True}


@app.get("/api/documents/{document_id}/download", dependencies=[Depends(auth.require_admin)])
def download_document(document_id: UUID):
    doc = one("SELECT filename, file FROM documents WHERE id = %s", (document_id,))
    if not doc:
        raise HTTPException(404, "Document introuvable.")
    return Response(
        bytes(doc["file"]),
        media_type="application/octet-stream",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(doc['filename'])}", "X-Content-Type-Options": "nosniff"},
    )


class Ask(BaseModel):
    question: str = Field(min_length=1, max_length=2000)
    audience: str = Field(default="public", pattern="^(public|internal)$")


def _ask_documents(question: str, audiences: list[str]) -> dict:
    passages = rag.search(question, audiences)
    excerpts = [{"title": p["title"], "page": p["page"], "content": p["content"][:400], "coverage": round(p["coverage"], 2), "similarity": p["similarity"]} for p in passages]
    # Staff questions go straight to the documents. Only the customer view applies customer routing.
    if "internal" in audiences:
        staff_answer = llm.answer_staff(question, passages)
        if staff_answer:
            used = [p for p in passages if p["id"] in staff_answer["passage_ids"]]
            found = bool(staff_answer["answer"].strip())
            return {"found": found, "route": "answer" if found else "not_found", "answer": staff_answer["answer"], "sources": rag.to_sources(used), "excerpts": excerpts, "mode": "claude"}
        routed = None
    else:
        routed = llm.answer_customer(question, "", passages)
    if routed:
        used = [p for p in passages if p["id"] in routed["passage_ids"]]
        return {"found": routed["route"] == "answer", "route": routed["route"], "answer": routed["answer"], "sources": rag.to_sources(used), "excerpts": excerpts, "mode": "claude"}
    best = passages[0] if passages else None
    if rag.is_confident(best):
        return {"found": True, "route": "answer", "answer": rag.extractive_answer(best, question), "sources": rag.to_sources([best]), "excerpts": excerpts, "mode": "extrait"}
    return {"found": False, "route": "not_found", "answer": "", "sources": [], "excerpts": excerpts, "mode": "extrait"}


@app.post("/api/admin/ask", dependencies=[Depends(auth.require_admin)])
def admin_ask(body: Ask):
    # "internal" tests what an agent can find, so it searches both levels. "public" matches what customers get.
    return _ask_documents(body.question, ["public", "internal"] if body.audience == "internal" else ["public"])


@app.get("/api/admin/unanswered", dependencies=[Depends(auth.require_admin)])
def unanswered():
    return query("SELECT id, question, created_at FROM unanswered_questions WHERE NOT dismissed ORDER BY created_at DESC LIMIT 200")


@app.post("/api/admin/unanswered/{question_id}/dismiss", dependencies=[Depends(auth.require_admin)])
def dismiss_unanswered(question_id: int):
    query("UPDATE unanswered_questions SET dismissed = true WHERE id = %s", (question_id,))
    return {"ok": True}


@app.get("/api/admin/stats", dependencies=[Depends(auth.require_admin)])
def stats():
    totals = one(
        """SELECT count(*)::int AS conversations,
                  count(*) FILTER (WHERE is_example)::int AS examples,
                  count(*) FILTER (WHERE NOT EXISTS (SELECT 1 FROM tickets t WHERE t.conversation_id = c.id))::int AS handled_by_ai,
                  count(*) FILTER (WHERE status = 'transferred' OR EXISTS (SELECT 1 FROM tickets t WHERE t.conversation_id = c.id AND t.kind IN ('transfert','carte','carte_perdue','fraude')))::int AS transferred,
                  count(*) FILTER (WHERE channel = 'voice')::int AS voice
           FROM conversations c"""
    )
    return {
        **totals,
        "handle_minutes": HANDLE_MINUTES,
        "minutes_saved": totals["handled_by_ai"] * HANDLE_MINUTES,
        "by_intent": query("SELECT COALESCE(primary_intent, 'non classé') AS intent, count(*)::int AS count FROM conversations GROUP BY 1 ORDER BY 2 DESC"),
        "by_day": query(
            """SELECT to_char(d, 'YYYY-MM-DD') AS day, count(c.id)::int AS count
               FROM generate_series(CURRENT_DATE - 6, CURRENT_DATE, interval '1 day') d
               LEFT JOIN conversations c ON c.started_at::date = d::date GROUP BY d ORDER BY d"""
        ),
        "tickets": one(
            """SELECT count(*) FILTER (WHERE status = 'open')::int AS open,
                      count(*) FILTER (WHERE status = 'in_progress')::int AS in_progress,
                      count(*) FILTER (WHERE status = 'resolved')::int AS resolved,
                      count(*) FILTER (WHERE status <> 'resolved' AND priority = 'P1')::int AS urgent
               FROM tickets"""
        ),
        "unanswered": one("SELECT count(*)::int AS n FROM unanswered_questions WHERE NOT dismissed")["n"],
        "documents": one("SELECT count(*) FILTER (WHERE status = 'ready' AND active)::int AS ready, count(*)::int AS total FROM documents"),
    }


# --- Agent desk -------------------------------------------------------------

TICKET_COLUMNS = """t.id, t.ref, t.conversation_id, t.kind, t.department, t.priority, t.status, t.summary, t.contact, t.created_at, t.taken_at, t.resolved_at,
                    c.sentiment, c.channel, c.is_example"""


@app.get("/api/tickets", dependencies=[Depends(auth.require_staff)])
def list_tickets(status: str = "active"):
    where = "t.status = 'resolved'" if status == "resolved" else "t.status <> 'resolved'"
    return query(
        f"""SELECT {TICKET_COLUMNS}, (SELECT count(*)::int FROM messages m WHERE m.conversation_id = t.conversation_id) AS message_count
            FROM tickets t JOIN conversations c ON c.id = t.conversation_id
            WHERE {where} ORDER BY t.priority, t.created_at LIMIT 200"""
    )


@app.get("/api/tickets/{ticket_id}", dependencies=[Depends(auth.require_staff)])
def get_ticket(ticket_id: UUID):
    ticket = one(f"SELECT {TICKET_COLUMNS} FROM tickets t JOIN conversations c ON c.id = t.conversation_id WHERE t.id = %s", (ticket_id,))
    if not ticket:
        raise HTTPException(404, "Dossier introuvable.")
    ticket["messages"] = query("SELECT id, role, content, sources, created_at FROM messages WHERE conversation_id = %s ORDER BY id", (ticket["conversation_id"],))
    return ticket


@app.post("/api/tickets/{ticket_id}/take", dependencies=[Depends(auth.require_staff)])
def take_ticket(ticket_id: UUID):
    if not one("UPDATE tickets SET status = 'in_progress', taken_at = COALESCE(taken_at, now()) WHERE id = %s AND status = 'open' RETURNING id", (ticket_id,)):
        raise HTTPException(409, "Ce dossier a déjà été pris en charge.")
    return {"ok": True}


class AgentReply(BaseModel):
    message: str = Field(min_length=1, max_length=4000)


@app.post("/api/tickets/{ticket_id}/reply", dependencies=[Depends(auth.require_staff)])
def reply_ticket(ticket_id: UUID, body: AgentReply):
    ticket = one("SELECT conversation_id, status FROM tickets WHERE id = %s", (ticket_id,))
    if not ticket:
        raise HTTPException(404, "Dossier introuvable.")
    if ticket["status"] == "resolved":
        raise HTTPException(409, "Ce dossier est clôturé.")
    query("INSERT INTO messages (conversation_id, role, content) VALUES (%s, 'agent', %s)", (ticket["conversation_id"], body.message))
    query("UPDATE tickets SET status = 'in_progress', taken_at = COALESCE(taken_at, now()) WHERE id = %s", (ticket_id,))
    query("UPDATE conversations SET status = 'transferred', flow = NULL, updated_at = now() WHERE id = %s", (ticket["conversation_id"],))
    return {"ok": True}


@app.post("/api/tickets/{ticket_id}/resolve", dependencies=[Depends(auth.require_staff)])
def resolve_ticket(ticket_id: UUID):
    ticket = one("UPDATE tickets SET status = 'resolved', resolved_at = now() WHERE id = %s RETURNING conversation_id", (ticket_id,))
    if not ticket:
        raise HTTPException(404, "Dossier introuvable.")
    if not one("SELECT id FROM tickets WHERE conversation_id = %s AND status <> 'resolved' LIMIT 1", (ticket["conversation_id"],)):
        query("UPDATE conversations SET status = 'active' WHERE id = %s", (ticket["conversation_id"],))
    return {"ok": True}


@app.post("/api/tickets/{ticket_id}/suggest", dependencies=[Depends(auth.require_staff)])
def suggest(ticket_id: UUID):
    ticket = one("SELECT conversation_id, summary FROM tickets WHERE id = %s", (ticket_id,))
    if not ticket:
        raise HTTPException(404, "Dossier introuvable.")
    conversation_id = str(ticket["conversation_id"])
    transcript = engine.transcript_of(conversation_id)
    last_customer = next((l.removeprefix("Client : ") for l in reversed(transcript.split("\n")) if l.startswith("Client : ")), "")
    search_text = f"{ticket['summary']} {last_customer}"
    # A suggestion can be sent to the customer in one click, and the conversation it is based on is customer-written.
    # So it only ever draws on public documents. Internal passages are shown to the agent separately.
    passages = rag.search(search_text, ["public"])
    internal = [p for p in rag.search(search_text, ["internal"], 3) if p["coverage"] > 0 or p["similarity"]]
    references = [{"title": p["title"], "page": p["page"], "content": p["content"][:600]} for p in internal]
    result = llm.suggest_reply(transcript, passages)
    if result:
        used = [p for p in passages if p["id"] in result["passage_ids"]]
        return {"reply": result["reply"], "sources": rag.to_sources(used), "internal_references": references, "mode": "claude"}
    best = passages[0] if passages else None
    if best:
        return {"reply": rag.extractive_answer(best, search_text), "sources": rag.to_sources([best]), "internal_references": references, "mode": "extrait"}
    return {"reply": "", "sources": [], "internal_references": references, "mode": "extrait"}


@app.post("/api/agent/search", dependencies=[Depends(auth.require_staff)])
def agent_search(body: Ask):
    return _ask_documents(body.question, ["public", "internal"])
