"""BM25 (Okapi) baseline with an identifier-preserving tokenizer. Pure Python, no extra dependency."""

from __future__ import annotations

import math
import re
from collections import Counter

_TOKEN = re.compile(r"[a-z0-9]+(?:[._/-][a-z0-9]+)*")
_STOP = frozenset(
    "a an and are as at be been by do does for from has have how in into is it its of on or that the "
    "their there these this to was were what when where which who why with within".split()
)


def _norm(tok: str) -> str:
    if len(tok) > 3 and tok.endswith("s") and not tok.endswith("ss") and not tok[-2].isdigit():
        return tok[:-1]
    return tok


def tokenize(text: str) -> list[str]:
    """Lower-case tokens; compound identifiers (flex-070, 193f001, mm^2/s) are kept whole AND split.

    Zero-padded numbers also yield their plain form so 'FLEX-070' matches 'test 70'.
    """
    out: list[str] = []
    for raw in _TOKEN.findall(text.lower()):
        parts = re.split(r"[._/-]", raw)
        cands = [raw] if len(parts) > 1 else []
        cands += parts
        for t in cands:
            if not t or t in _STOP:
                continue
            out.append(_norm(t))
            if t.isdigit() and len(t) > 1 and t.startswith("0"):
                out.append(t.lstrip("0") or "0")
    return out


def core_tokens(text: str) -> list[str]:
    """Whole tokens only (compound identifiers are NOT split): used where one entity must count once."""
    return [_norm(t) for t in _TOKEN.findall(text.lower()) if t not in _STOP]


class BM25Index:
    def __init__(self, docs: list[str], k1: float = 1.5, b: float = 0.75) -> None:
        self.k1, self.b = k1, b
        self.tf: list[Counter[str]] = [Counter(tokenize(d)) for d in docs]
        self.len = [sum(c.values()) for c in self.tf]
        self.n = len(docs)
        self.avgdl = (sum(self.len) / self.n) if self.n else 0.0
        df: Counter[str] = Counter()
        for c in self.tf:
            df.update(c.keys())
        self.idf = {t: math.log(1.0 + (self.n - f + 0.5) / (f + 0.5)) for t, f in df.items()}
        self.post: dict[str, list[int]] = {}
        for i, c in enumerate(self.tf):
            for t in c:
                self.post.setdefault(t, []).append(i)

    def scores(self, query: str, allowed: set[int] | None = None) -> dict[int, float]:
        q = Counter(tokenize(query))
        acc: dict[int, float] = {}
        for t in q:
            idf = self.idf.get(t)
            if idf is None:
                continue
            for i in self.post[t]:
                if allowed is not None and i not in allowed:
                    continue
                f = self.tf[i][t]
                denom = f + self.k1 * (1 - self.b + self.b * self.len[i] / (self.avgdl or 1.0))
                acc[i] = acc.get(i, 0.0) + idf * f * (self.k1 + 1) / denom
        return acc
