import os

import numpy as np
import pytest

from app.rag.bm25 import BM25Index, tokenize
from app.rag.dense import HashingEncoder
from app.rag.fusion import rrf, weighted
from app.rag.retriever import HybridRetriever
from app.rag.schemas import DocType, SearchFilter, SearchRequest


def ids(res):
    return [h.chunk.chunk_key for h in res.hits]


def test_tokenizer_keeps_identifiers_and_numbers():
    toks = tokenize("FLEX-070, identifier 193F001 at 0.15 mole fraction; K in mm^2/s")
    assert {"flex-070", "flex", "070", "70", "193f001", "0.15"} <= set(toks)
    assert "the" not in tokenize("the droplet")


def test_bm25_ranks_exact_identifier_first():
    idx = BM25Index(["alpha droplet burns", "FLEX-070 heptane run", "beta flame"])
    sc = idx.scores("what about flex-070")
    assert max(sc, key=sc.get) == 1
    assert idx.scores("zzzunknown") == {}


def test_bm25_finds_named_experiment(retriever: HybridRetriever):
    res = retriever.search(
        SearchRequest(query="What happened to the droplet in FLEX-001?", mode="bm25", top_k=3)
    )
    # the NASA/TP caption for FLEX-001 is UNREGISTERED, so the PSI-69 row is the top usable hit
    assert res.hits[0].chunk.chunk_key == "PSI-69:row:001"
    assert all(h.chunk.source_id != "NASA-TP-2015-216046" for h in res.hits)


def test_metadata_filters(retriever: HybridRetriever):
    f = SearchFilter(regimes=["flex_droplet"], doc_types=[DocType.TABLE_ROW], fuels=["Heptane"])
    res = retriever.search(SearchRequest(query="burning rate constant", mode="bm25", top_k=10, filters=f))
    assert res.hits and all(
        h.chunk.regime == "flex_droplet"
        and h.chunk.doc_type is DocType.TABLE_ROW
        and h.chunk.fuel_or_material == "Heptane"
        for h in res.hits
    )
    res = retriever.search(
        SearchRequest(
            query="identifier 193F001",
            mode="bm25",
            filters=SearchFilter(experiment_ids=["193f001"]),
            top_k=10,
        )
    )
    assert {"PSI-69:row:070", "PSI-69:row:073"} <= set(ids(res))
    res = retriever.search(SearchRequest(query="x", mode="bm25", filters=SearchFilter(source_ids=["PSI-25"])))
    assert res.hits == []  # PSI-25 is ACQUIRED_BUT_EXCLUDED: a filter cannot bring it back


def test_ineligible_chunks_are_excluded_unless_the_admin_path_asks(retriever: HybridRetriever):
    q = "SIBAL fabric sample flow direction concurrent"
    res = retriever.search(SearchRequest(query=q, mode="bm25", top_k=10))
    assert all(h.chunk.usable_as_evidence for h in res.hits)
    assert not {h.chunk.source_id for h in res.hits} & {"PSI-25", "PSI-98", "NASA-TP-2015-216046"}
    res = retriever.search(SearchRequest(query=q, mode="bm25", top_k=3), include_ineligible=True)
    assert res.hits[0].chunk.source_id == "PSI-98" and not res.hits[0].chunk.usable_as_evidence
    assert res.hits[0].chunk.eligibility == "QUARANTINED" and res.hits[0].chunk.exclusion_reason


def test_hashing_encoder_is_deterministic_and_normalised():
    e = HashingEncoder()
    a, b = e.encode(["droplet burning rate"]), e.encode(["droplet burning rate"])
    assert np.allclose(a, b) and abs(float(np.linalg.norm(a[0])) - 1.0) < 1e-5
    s_same = float(e.encode(["heptane droplet"])[0] @ e.encode(["heptane droplets"])[0])
    s_diff = float(e.encode(["heptane droplet"])[0] @ e.encode(["glovebox wind tunnel"])[0])
    assert s_same > s_diff


def test_fusion_rrf_and_weighted_are_deterministic():
    a, b = {1: 3.0, 2: 2.0, 3: 1.0}, {3: 9.0, 2: 5.0}
    f = rrf([a, b], k=60)
    assert f[2] > f[1] and f[3] > f[1]  # items ranked by both lists beat an item in one list
    assert rrf([a, b], k=60) == f
    w = weighted([a, b], [1.0, 0.0])
    assert max(w, key=w.get) == 1


def test_hybrid_and_dense_modes_return_component_scores(retriever: HybridRetriever):
    res = retriever.search(SearchRequest(query="Which hardware housed BASS-II", mode="hybrid", top_k=5))
    assert res.mode == "hybrid" and res.dense_backend.startswith("hashing")
    assert set(res.hits[0].component_scores) == {"bm25", "dense"}
    assert [h.rank for h in res.hits] == [1, 2, 3, 4, 5]


def test_dense_disabled_falls_back_with_warning(rag_chunks, rag_cfg):
    r = HybridRetriever(rag_chunks, rag_cfg, None)
    res = r.search(SearchRequest(query="BASS-II hardware", mode="hybrid", top_k=3))
    assert res.mode == "bm25" and any("dense backend is disabled" in w for w in res.warnings)
    res = r.search(SearchRequest(query="BASS-II hardware", mode="bm25", rerank=True, top_k=3))
    assert not res.reranked and any("no reranker" in w for w in res.warnings)


def test_reranker_interface_reorders_candidates(rag_chunks, rag_cfg):
    class Reverse:
        name = "reverse-test"

        def score(self, query, texts):
            return [float(i) for i in range(len(texts))]  # prefers the LAST candidate

    r = HybridRetriever(rag_chunks, rag_cfg, HashingEncoder(), Reverse())
    plain = r.search(SearchRequest(query="BASS-II hardware", mode="bm25", top_k=3))
    rer = r.search(SearchRequest(query="BASS-II hardware", mode="bm25", top_k=3, rerank=True))
    assert rer.reranked and ids(rer) != ids(plain)


@pytest.mark.skipif(
    os.environ.get("FLAMESCOPE_TEST_BGE") != "1",
    reason="set FLAMESCOPE_TEST_BGE=1 with BGE-M3 weights available",
)
def test_bge_m3_encoder_when_weights_are_available():
    from app.rag.dense import BGEM3Encoder

    m = BGEM3Encoder("BAAI/bge-m3", "cpu").encode(["droplet flame extinction", "glovebox wind tunnel"])
    assert m.shape == (2, 1024) and abs(float(np.linalg.norm(m[0])) - 1.0) < 1e-4
