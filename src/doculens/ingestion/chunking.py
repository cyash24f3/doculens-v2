from dataclasses import dataclass

from doculens.errors import DomainError
from doculens.ingestion.parsing import Extracted, sections, sha


@dataclass(frozen=True)
class Piece:
    ordinal: int
    text: str
    start: int
    end: int
    token_count: int
    section: str | None
    page_start: int | None
    page_end: int | None
    content_sha256: str


def chunk(source: Extracted, encoder, size: int, overlap: int, max_chunks: int) -> list[Piece]:
    if size > encoder.max_tokens - 2:
        raise DomainError(
            "chunk_model_limit", "Chunk size exceeds the loaded embedding model input limit"
        )
    result: list[Piece] = []
    for left, right, label in sections(source.text):
        # Fast tokenizer offsets refer to stored extracted text, never original PDF coordinates.
        offsets = encoder.offsets(source.text[left:right])
        cursor = 0
        while cursor < len(offsets):
            stop = min(cursor + size, len(offsets))
            a = left + offsets[cursor][0]
            b = left + offsets[stop - 1][1]
            # Prefer a paragraph boundary if it retains at least half the target tokens.
            if stop < len(offsets):
                boundary = source.text.rfind("\n\n", a, b)
                if boundary > a:
                    count = sum(1 for _, end in offsets[cursor:stop] if left + end <= boundary)
                    if count >= size // 2:
                        stop = cursor + count
                        b = left + offsets[stop - 1][1]
            text = source.text[a:b]
            page_nums = [p for p, x, y in source.pages if x < b and y > a]
            result.append(
                Piece(
                    len(result),
                    text,
                    a,
                    b,
                    len(encoder.offsets(text)),
                    label,
                    min(page_nums) if page_nums else None,
                    max(page_nums) if page_nums else None,
                    sha(text),
                )
            )
            if len(result) > max_chunks:
                raise DomainError("too_many_chunks", "Document exceeds the configured chunk limit")
            if stop == len(offsets):
                break
            cursor = max(cursor + 1, stop - overlap)
    if not result:
        raise DomainError("empty_extraction", "No chunks could be created")
    return result
