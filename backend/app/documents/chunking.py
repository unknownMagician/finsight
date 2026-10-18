"""Split page text into retrieval chunks that never cross a page boundary, so every chunk (and
therefore every citation) maps to exactly one page."""

import re

TARGET_CHARS = 1200
MAX_CHARS = 2000


def chunk_page(text: str, *, target: int = TARGET_CHARS, maximum: int = MAX_CHARS) -> list[str]:
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    chunks: list[str] = []
    current = ""
    for paragraph in paragraphs:
        pieces = [paragraph]
        if len(paragraph) > maximum:  # split very long paragraphs on sentence/line ends
            pieces = [s.strip() for s in re.split(r"(?<=[.;:])\s+|\n", paragraph) if s.strip()]
        for piece in pieces:
            while len(piece) > maximum:  # last resort: hard split
                chunks.append(piece[:maximum])
                piece = piece[maximum:]
            if current and len(current) + len(piece) + 1 > target:
                chunks.append(current)
                current = piece
            else:
                current = f"{current}\n{piece}" if current else piece
    if current:
        chunks.append(current)
    return chunks
