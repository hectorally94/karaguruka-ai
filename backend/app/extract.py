import io
import re
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

from .settings import OCR_LANGUAGES

ALLOWED_EXTENSIONS = {".pdf", ".docx", ".xlsx", ".csv", ".txt", ".md", ".png", ".jpg", ".jpeg"}
CHUNK_SIZE = 1200
CHUNK_OVERLAP = 150


@dataclass
class Extracted:
    pages: list[tuple[int | None, str]]
    page_count: int | None
    used_ocr: bool = False


def _ocr_image(path: Path) -> str:
    result = subprocess.run(["tesseract", str(path), "stdout", "-l", OCR_LANGUAGES], capture_output=True, text=True, timeout=300, check=True)
    return result.stdout


def _ocr_pdf(data: bytes) -> Extracted:
    with tempfile.TemporaryDirectory(prefix="karaguruka-ocr-") as tmp:
        folder = Path(tmp)
        pdf = folder / "input.pdf"
        pdf.write_bytes(data)
        subprocess.run(["pdftoppm", "-r", "200", "-png", str(pdf), str(folder / "page")], check=True, timeout=600)
        images = sorted(folder.glob("page*.png"))
        return Extracted([(i + 1, _ocr_image(image)) for i, image in enumerate(images)], len(images), True)


def _extract_pdf(data: bytes) -> Extracted:
    from pypdf import PdfReader

    reader = PdfReader(io.BytesIO(data))
    texts = [page.extract_text() or "" for page in reader.pages]
    # A page with almost no selectable text is a scan.
    if len(re.sub(r"\s", "", "".join(texts))) < 40 * max(len(texts), 1):
        return _ocr_pdf(data)
    return Extracted([(i + 1, t) for i, t in enumerate(texts)], len(texts))


def _extract_docx(data: bytes) -> Extracted:
    from docx import Document

    doc = Document(io.BytesIO(data))
    parts = [p.text for p in doc.paragraphs if p.text.strip()]
    for table in doc.tables:
        parts.append("\n".join(" | ".join(cell.text.strip() for cell in row.cells) for row in table.rows))
    return Extracted([(None, "\n\n".join(parts))], None)


def _extract_xlsx(data: bytes) -> Extracted:
    from openpyxl import load_workbook

    book = load_workbook(io.BytesIO(data), read_only=True, data_only=True)
    pages = []
    for sheet in book.worksheets:
        rows = [" | ".join("" if v is None else str(v) for v in row) for row in sheet.iter_rows(values_only=True)]
        pages.append((None, f"Feuille : {sheet.title}\n\n" + "\n".join(r for r in rows if r.replace("|", "").strip())))
    return Extracted(pages, None)


def extract_text(filename: str, data: bytes) -> Extracted:
    ext = Path(filename).suffix.lower()
    if ext == ".pdf":
        return _extract_pdf(data)
    if ext == ".docx":
        return _extract_docx(data)
    if ext == ".xlsx":
        return _extract_xlsx(data)
    if ext in {".csv", ".txt", ".md"}:
        return Extracted([(None, data.decode("utf-8", errors="replace"))], None)
    if ext in {".png", ".jpg", ".jpeg"}:
        with tempfile.TemporaryDirectory(prefix="karaguruka-ocr-") as tmp:
            image = Path(tmp) / f"input{ext}"
            image.write_bytes(data)
            return Extracted([(None, _ocr_image(image))], 1, True)
    raise ValueError(f"Format non pris en charge : {ext or 'inconnu'}")


def chunk_text(text: str) -> list[str]:
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text.replace("\r", "")) if p.strip()]
    chunks: list[str] = []
    current = ""
    for paragraph in paragraphs:
        if current and len(current) + len(paragraph) + 2 > CHUNK_SIZE:
            chunks.append(current)
            current = re.sub(r"^\S*\s", "", current[-CHUNK_OVERLAP:])
        if len(paragraph) > CHUNK_SIZE:
            if current:
                chunks.append(current)
                current = ""
            for start in range(0, len(paragraph), CHUNK_SIZE - CHUNK_OVERLAP):
                chunks.append(paragraph[start : start + CHUNK_SIZE])
        else:
            current = f"{current}\n\n{paragraph}" if current else paragraph
    if current:
        chunks.append(current)
    return chunks
