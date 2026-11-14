"""Metadata-filtered BM25 / dense / hybrid retrieval with optional reranking."""

from __future__ import annotations

from app.rag.bm25 import BM25Index
from app.rag.config import RagConfig
from app.rag.dense import DenseIndex, Encoder
from app.rag.fusion import rrf, weighted
from app.rag.rerank import Reranker
from app.rag.schemas import Chunk, SearchFilter, SearchHit, SearchRequest, SearchResponse

POOL = 50  # candidates taken from each retriever before fusion


class HybridRetriever:
    def __init__(
        self,
        chunks: list[Chunk],
        cfg: RagConfig,
        encoder: Encoder | None = None,
        reranker: Reranker | None = None,
    ) -> None:
        self.chunks = chunks
        self.cfg = cfg
        self.by_id = {c.chunk_id: i for i, c in enumerate(chunks)}
        self.by_id.update({c.chunk_key: i for i, c in enumerate(chunks)})  # readable key also resolves
        self.bm25 = BM25Index([c.text + " " + " ".join(c.experiment_ids) for c in chunks])
        self.dense = DenseIndex(chunks, encoder, cfg.cache_dir) if encoder else None
        self.reranker = reranker

    @property
    def dense_backend(self) -> str:
        return self.dense.encoder.name if self.dense else "none"

    def get(self, chunk_ref: str) -> Chunk | None:
        """Look up by chunk_id (UUID) or chunk_key. Returns ineligible chunks too: callers must check."""
        i = self.by_id.get(chunk_ref)
        return self.chunks[i] if i is not None else None

    def allowed(self, f: SearchFilter, include_ineligible: bool = False) -> set[int]:
        """include_ineligible is reachable only from the admin routes, never from a public request."""
        ok: set[int] = set()
        for i, c in enumerate(self.chunks):
            if not c.usable_as_evidence and not include_ineligible:
                continue
            if f.source_ids and c.source_id not in f.source_ids:
                continue
            if f.regimes and c.regime not in f.regimes:
                continue
            if f.doc_types and c.doc_type not in f.doc_types:
                continue
            if f.fuels and (c.fuel_or_material or "").lower() not in {x.lower() for x in f.fuels}:
                continue
            if f.experiment_ids and not (
                {e.lower() for e in f.experiment_ids} & {e.lower() for e in c.experiment_ids}
            ):
                continue
            ok.add(i)
        return ok

    @staticmethod
    def _top(scores: dict[int, float], n: int) -> dict[int, float]:
        return dict(sorted(scores.items(), key=lambda kv: (-kv[1], kv[0]))[:n])

    def search(self, req: SearchRequest, include_ineligible: bool = False) -> SearchResponse:
        warnings: list[str] = []
        allowed = self.allowed(req.filters, include_ineligible)
        mode = req.mode
        if mode in ("dense", "hybrid") and self.dense is None:
            warnings.append(f"dense backend is disabled; falling back from '{mode}' to bm25")
            mode = "bm25"
        comps: dict[str, dict[int, float]] = {}
        if mode in ("bm25", "hybrid"):
            comps["bm25"] = self._top(self.bm25.scores(req.query, allowed), POOL)
        if mode in ("dense", "hybrid") and self.dense:
            comps["dense"] = self._top(self.dense.scores(req.query, allowed), POOL)
        if mode == "hybrid":
            maps = [comps["bm25"], comps["dense"]]
            w = [self.cfg.bm25_weight, self.cfg.dense_weight]
            fused = rrf(maps, self.cfg.rrf_k, w) if self.cfg.hybrid_fusion == "rrf" else weighted(maps, w)
        else:
            fused = next(iter(comps.values()), {})
        order = [i for i, _ in sorted(fused.items(), key=lambda kv: (-kv[1], kv[0]))]
        reranked = False
        if req.rerank:
            if self.reranker is None:
                warnings.append("rerank requested but no reranker is configured (FLAMESCOPE_RERANK_BACKEND)")
            else:
                head = order[: max(req.top_k * 4, 20)]
                rs = self.reranker.score(req.query, [self.chunks[i].text for i in head])
                head = [i for i, _ in sorted(zip(head, rs, strict=True), key=lambda p: -p[1])]
                fused = {i: s for i, s in zip(head, sorted(rs, reverse=True), strict=True)}
                order = head + order[len(head) :]
                reranked = True
        hits = [
            SearchHit(
                rank=r,
                score=float(fused.get(i, 0.0)),
                chunk=self.chunks[i],
                component_scores={k: float(v.get(i, 0.0)) for k, v in comps.items()},
            )
            for r, i in enumerate(order[: req.top_k], 1)
        ]
        return SearchResponse(
            query=req.query,
            mode=mode,
            dense_backend=self.dense_backend,
            reranked=reranked,
            hits=hits,
            warnings=warnings,
        )
