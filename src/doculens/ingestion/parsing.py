import hashlib
import io
import re
from dataclasses import dataclass
from pathlib import PurePath

from pypdf import PdfReader

from doculens.errors import DomainError


@dataclass(frozen=True)
class Extracted:
    text: str
    pages: tuple[tuple[int, int, int], ...]
    warnings: tuple[str, ...]


def sha(text: bytes | str) -> str:
    return hashlib.sha256(text.encode("utf-8") if isinstance(text, str) else text).hexdigest()


def validate_file(name: str, mime: str, raw: bytes, limit: int) -> str:
    extension = PurePath(name).suffix.lower()
    kinds = {".pdf": "pdf", ".md": "markdown", ".txt": "text"}
    if extension not in kinds:
        raise DomainError("unsupported_extension", "Upload a PDF, Markdown, or UTF-8 text file")
    if not raw:
        raise DomainError("empty_file", "The uploaded file is empty")
    if len(raw) > limit:
        raise DomainError("file_too_large", "The file exceeds the configured upload limit", 413)
    permitted = {"application/octet-stream", ""}
    permitted |= (
        {"application/pdf"}
        if extension == ".pdf"
        else {"text/plain", "text/markdown", "text/x-markdown"}
    )
    if mime.split(";", 1)[0].lower() not in permitted:
        raise DomainError("content_type_mismatch", "Content type does not match the file extension")
    if extension == ".pdf" and not raw.startswith(b"%PDF-"):
        raise DomainError("corrupt_pdf", "PDF header is missing")
    if extension != ".pdf":
        try:
            decoded = raw.decode("utf-8-sig")
        except UnicodeDecodeError as e:
            raise DomainError("invalid_utf8", "Text files must be UTF-8") from e
        if "\x00" in decoded or any(ord(c) < 9 for c in decoded):
            raise DomainError("binary_text", "Binary content is not a text document")
        if not decoded.strip():
            raise DomainError("empty_extraction", "No readable text was found")
    return kinds[extension]


def normalize(text: str) -> str:
    return text.replace("\r\n", "\n").replace("\r", "\n").strip()


def extract(raw: bytes, kind: str, char_limit: int) -> Extracted:
    if kind != "pdf":
        text = normalize(raw.decode("utf-8-sig"))
        if len(text) > char_limit:
            raise DomainError("extracted_text_too_large", "Extracted text exceeds the safety limit")
        return Extracted(text, (), ())
    try:
        reader = PdfReader(io.BytesIO(raw), strict=True)
        if reader.is_encrypted:
            raise DomainError("encrypted_pdf", "Encrypted PDFs are not supported")
        if len(reader.pages) > 500:
            raise DomainError("too_many_pages", "PDF exceeds 500 pages")
        parts: list[str] = []
        pages: list[tuple[int, int, int]] = []
        warnings: list[str] = []
        offset = 0
        for i, page in enumerate(reader.pages, 1):
            text = normalize(page.extract_text() or "")
            if not text:
                warnings.append(f"Page {i} has no extracted text; OCR may be required")
            if parts:
                offset += 2
            pages.append((i, offset, offset + len(text)))
            parts.append(text)
            offset += len(text)
            if offset > char_limit:
                raise DomainError(
                    "extracted_text_too_large", "Extracted text exceeds the safety limit"
                )
        text = "\n\n".join(parts)
        if not text.strip():
            raise DomainError("ocr_required", "No text layer was found. OCR is required")
        return Extracted(text, tuple(pages), tuple(warnings))
    except DomainError:
        raise
    except Exception as e:
        raise DomainError("corrupt_pdf", "PDF parsing failed; check file integrity") from e


def sections(text: str) -> list[tuple[int, int, str | None]]:
    headings = list(re.finditer(r"(?m)^#{1,6}\s+(.+)$", text))
    if not headings:
        return [(0, len(text), None)]
    boundaries = [0] if headings[0].start() else []
    boundaries += [m.start() for m in headings]
    boundaries.append(len(text))
    labels = {m.start(): m.group(1) for m in headings}
    return [(a, b, labels.get(a)) for a, b in zip(boundaries, boundaries[1:], strict=False)]
