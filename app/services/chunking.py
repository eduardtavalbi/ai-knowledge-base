import re


def _split_oversized_paragraph(paragraph: str, chunk_size: int, overlap: int) -> list[str]:
    """Split a long paragraph into bounded windows without dropping characters."""
    step = chunk_size - overlap
    chunks: list[str] = []
    for start in range(0, len(paragraph), step):
        chunks.append(paragraph[start : start + chunk_size])
        # The previous window already covers the tail when it reaches the
        # end of the paragraph. Do not emit a redundant, fully overlapping
        # final chunk for lengths such as chunk_size + overlap.
        if start + chunk_size >= len(paragraph):
            break
    return chunks


def split_text(
    text: str,
    chunk_size: int = 500,
    overlap: int = 100,
) -> list[str]:
    if chunk_size <= 0:
        raise ValueError("chunk_size must be positive")

    if overlap < 0:
        raise ValueError("overlap cannot be negative")

    if overlap >= chunk_size:
        raise ValueError("overlap must be smaller than chunk_size")

    paragraphs = [
        re.sub(r"\s+", " ", paragraph).strip()
        for paragraph in re.split(r"\n\s*\n", text.strip())
        if paragraph.strip()
    ]

    if not paragraphs:
        return []

    chunks: list[str] = []
    current = ""

    for paragraph in paragraphs:
        if len(paragraph) > chunk_size:
            if current:
                chunks.append(current)
                current = ""
            chunks.extend(
                _split_oversized_paragraph(paragraph, chunk_size, overlap)
            )
            continue

        if not current:
            current = paragraph
            continue

        candidate = f"{current}\n\n{paragraph}"
        if len(candidate) <= chunk_size:
            current = candidate
            continue

        chunks.append(current)
        prefix = current[-overlap:] if overlap else ""
        candidate = f"{prefix}\n\n{paragraph}" if prefix else paragraph
        current = candidate if len(candidate) <= chunk_size else paragraph

    if current:
        chunks.append(current)

    return chunks
