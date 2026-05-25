import re

def clean_extracted_text(text: str) -> str:
    """
    Normalize raw text from Document Intelligence output.
    Removes page numbers, headers/footers, excessive whitespace.
    Critical step — dirty text produces low-quality embeddings.
    """
    # Remove page numbers e.g. "Page 1 of 12" or "- 3 -"
    text = re.sub(r'[-–]\s*\d+\s*[-–]', '', text)
    text = re.sub(r'[Pp]age\s+\d+\s+of\s+\d+', '', text)

    # Collapse excessive newlines
    text = re.sub(r'\n{3,}', '\n\n', text)

    # Collapse multiple spaces/tabs
    text = re.sub(r'[ \t]+', ' ', text)

    # Remove non-printable characters
    text = re.sub(r'[^\x09\x0A\x0D\x20-\x7E\u00A0-\uFFFF]', '', text)

    # Strip each line, drop single-char noise lines
    lines = [l.strip() for l in text.split('\n')]
    lines = [l for l in lines if len(l) > 2]

    return '\n'.join(lines).strip()

def is_valid_chunk(text: str, min_length: int = 50) -> bool:
    """
    Reject chunks that are too short or mostly non-alphabetic.
    Prevents garbage chunks (page numbers, table borders) from polluting vector index.
    """
    if len(text.strip()) < min_length:
        return False
    alpha_ratio = sum(c.isalpha() for c in text) / max(len(text), 1)
    return alpha_ratio > 0.2
