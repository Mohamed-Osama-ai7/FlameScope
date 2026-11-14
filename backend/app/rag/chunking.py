"""Section/page-aware chunking. Table rows and captions are never split (they are atomic evidence)."""

from __future__ import annotations

import hashlib
import re

_SENT = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9(\[])")
_HEADING = re.compile(r"^(#{1,6})\s+(.*\S)\s*$")

MAX_WORDS = 110
OVERLAP_SENTENCES = 1


def content_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def split_sentences(text: str) -> list[str]:
    return [s.strip() for s in _SENT.split(" ".join(text.split())) if s.strip()]


def window_text(text: str, max_words: int = MAX_WORDS, overlap: int = OVERLAP_SENTENCES) -> list[str]:
    """Pack whole sentences into windows of <= max_words (a single longer sentence stays whole)."""
    windows: list[str] = []
    cur: list[str] = []
    fresh = 0  # sentences in `cur` not already emitted (overlap carry-over does not count)
    words = 0
    for s in split_sentences(text):
        n = len(s.split())
        if fresh and words + n > max_words:
            windows.append(" ".join(cur))
            cur = cur[-overlap:] if overlap else []
            fresh = 0
            words = sum(len(x.split()) for x in cur)
        cur.append(s)
        fresh += 1
        words += n
    if fresh:
        windows.append(" ".join(cur))
    return windows


def split_sections(text: str) -> list[tuple[str, str]]:
    """Split markdown-style text into (heading_path, body). Text before any heading has path ''."""
    out: list[tuple[str, str]] = []
    stack: list[tuple[int, str]] = []
    buf: list[str] = []
    path = ""

    def flush() -> None:
        body = "\n".join(buf).strip()
        if body:
            out.append((path, body))
        buf.clear()

    for line in text.splitlines():
        m = _HEADING.match(line)
        if m:
            flush()
            level, title = len(m.group(1)), m.group(2)
            while stack and stack[-1][0] >= level:
                stack.pop()
            stack.append((level, title))
            path = " > ".join(t for _, t in stack)
        else:
            buf.append(line)
    flush()
    return out


def chunk_pages(pages: list[tuple[int, str]]) -> list[tuple[int, str, str]]:
    """(page, text) -> list of (page, section_path, chunk_text); chunks never cross a page boundary."""
    result: list[tuple[int, str, str]] = []
    for page, text in pages:
        for section, body in split_sections(text) or [("", text)]:
            for w in window_text(body):
                result.append((page, section, w))
    return result
