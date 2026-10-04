from pathlib import Path

from docx import Document
from pypdf import PdfReader


def extract_pdf(path: str) -> str:
    reader = PdfReader(path)
    return "\n".join(page.extract_text() or "" for page in reader.pages).strip()


def extract_docx(path: str) -> str:
    document = Document(path)
    return "\n".join(paragraph.text for paragraph in document.paragraphs).strip()


def extract_document(path: str) -> str:
    suffix = Path(path).suffix.lower()
    if suffix == ".pdf":
        return extract_pdf(path)
    if suffix == ".docx":
        return extract_docx(path)
    raise ValueError("Поддерживаются только PDF и DOCX")
