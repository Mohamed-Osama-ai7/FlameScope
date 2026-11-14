"""Dense retrieval behind a replaceable encoder interface.

* ``bge-m3``  - BAAI/bge-m3 through sentence-transformers (optional dependency + model weights that are
  downloaded by the library on first use; never committed). Selected with FLAMESCOPE_DENSE_BACKEND=bge-m3.
* ``hashing`` - deterministic character/word n-gram hashing embedding. It is an OFFLINE STAND-IN for tests
  and for machines without the weights. It is NOT a neural model and every result produced with it is
  labelled with its backend name; do not report it as BGE-M3 performance.
"""

from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Protocol

import numpy as np

from app.rag.bm25 import tokenize
from app.rag.config import RagConfig
from app.rag.schemas import Chunk


class DenseUnavailableError(RuntimeError):
    pass


class Encoder(Protocol):
    name: str

    def encode(self, texts: list[str]) -> np.ndarray: ...


def _l2(m: np.ndarray) -> np.ndarray:
    n = np.linalg.norm(m, axis=1, keepdims=True)
    n[n == 0] = 1.0
    return (m / n).astype(np.float32)


class HashingEncoder:
    name = "hashing-ngram-1024 (offline stand-in, not neural)"

    def __init__(self, dim: int = 1024) -> None:
        self.dim = dim

    def _feats(self, text: str) -> list[str]:
        words = tokenize(text)
        feats = list(words)
        for w in words:
            padded = f"<{w}>"
            for n in (3, 4):
                feats += [padded[i : i + n] for i in range(max(1, len(padded) - n + 1))]
        feats += [f"{a}_{b}" for a, b in zip(words, words[1:], strict=False)]
        return feats

    def encode(self, texts: list[str]) -> np.ndarray:
        m = np.zeros((len(texts), self.dim), dtype=np.float32)
        for r, t in enumerate(texts):
            for f in self._feats(t):
                h = int.from_bytes(hashlib.blake2b(f.encode(), digest_size=8).digest(), "little")
                m[r, h % self.dim] += 1.0 if (h >> 63) & 1 else -1.0
        return _l2(np.sign(m) * np.sqrt(np.abs(m)))


class BGEM3Encoder:
    def __init__(self, model: str, device: str) -> None:
        try:
            from sentence_transformers import SentenceTransformer  # optional: pip install '.[rag]'
        except ImportError as exc:
            raise DenseUnavailableError(
                "BGE-M3 needs 'sentence-transformers' (pip install .[rag]) and the model weights"
            ) from exc
        self.name = f"{model} (sentence-transformers)"
        self._m = SentenceTransformer(model, device=device)

    def encode(self, texts: list[str]) -> np.ndarray:
        return _l2(np.asarray(self._m.encode(texts, batch_size=16, normalize_embeddings=True)))


def make_encoder(cfg: RagConfig) -> Encoder | None:
    if cfg.dense_backend == "none":
        return None
    if cfg.dense_backend == "hashing":
        return HashingEncoder()
    if cfg.dense_backend in ("bge-m3", "bge"):
        return BGEM3Encoder(cfg.dense_model, cfg.device)
    raise DenseUnavailableError(f"unknown FLAMESCOPE_DENSE_BACKEND '{cfg.dense_backend}'")


class DenseIndex:
    """Embeds chunk text; embeddings are cached on disk keyed by (encoder, content_hash)."""

    def __init__(self, chunks: list[Chunk], encoder: Encoder, cache_dir: Path | None = None) -> None:
        self.encoder = encoder
        key = hashlib.sha256((encoder.name + "".join(c.content_hash for c in chunks)).encode()).hexdigest()[
            :20
        ]
        path = (
            (cache_dir / f"dense_{re.sub(r'[^a-z0-9]+', '_', encoder.name.lower())[:40]}_{key}.npy")
            if cache_dir
            else None
        )
        if path and path.exists():
            self.matrix = np.load(path)
        else:
            self.matrix = encoder.encode([c.text for c in chunks])
            if path:
                path.parent.mkdir(parents=True, exist_ok=True)
                np.save(path, self.matrix)

    def scores(self, query: str, allowed: set[int] | None = None) -> dict[int, float]:
        q = self.encoder.encode([query])[0]
        sims = self.matrix @ q
        idx = range(len(sims)) if allowed is None else allowed
        return {int(i): float(sims[i]) for i in idx}
