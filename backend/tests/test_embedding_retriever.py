"""Unit tests for EmbeddingRetriever against a deterministic fake embed_fn (an exact
text->vector lookup) — no network dependency, no real embeddings API involved."""

from app.ramq.retrieval import EmbeddingRetriever


def _lookup_embed_fn(vectors: dict[str, list[float]]):
    def embed_fn(texts: list[str]) -> list[list[float]]:
        return [vectors[t] for t in texts]

    return embed_fn


def test_candidates_ranked_by_cosine_similarity():
    vectors = {
        "chat": [1.0, 0.0],
        "chien": [0.9, 0.1],
        "avion": [0.0, 1.0],
        "query": [1.0, 0.0],
    }
    retriever = EmbeddingRetriever(
        ["chat", "chien", "avion"], text_for=lambda x: x, embed_fn=_lookup_embed_fn(vectors)
    )
    results = retriever.candidates_for("query", limit=3)
    assert results[0] == "chat"
    assert results[1] == "chien"
    assert "avion" not in results  # cosine similarity 0 against an orthogonal vector


def test_candidates_for_respects_limit():
    vectors = {"a": [1.0, 0.0], "b": [0.9, 0.1], "c": [0.8, 0.2], "q": [1.0, 0.0]}
    retriever = EmbeddingRetriever(
        ["a", "b", "c"], text_for=lambda x: x, embed_fn=_lookup_embed_fn(vectors)
    )
    assert len(retriever.candidates_for("q", limit=2)) == 2


def test_empty_items_returns_empty_without_calling_embed_fn():
    calls = []

    def embed_fn(texts):
        calls.append(texts)
        return []

    retriever = EmbeddingRetriever([], text_for=lambda x: x, embed_fn=embed_fn)
    assert retriever.candidates_for("anything", limit=5) == []
    assert calls == []  # nothing to embed at construction time, and candidates_for short-circuits


def test_precomputed_vectors_skip_embedding_the_corpus():
    # embed_fn must be called only for the query, never for "chat"/"chien"/"avion" — the
    # whole point of passing precomputed vectors is to avoid re-embedding a shipped corpus.
    calls = []

    def embed_fn(texts):
        calls.append(texts)
        return [[1.0, 0.0]]

    retriever = EmbeddingRetriever(
        ["chat", "chien", "avion"],
        embed_fn=embed_fn,
        vectors=[[1.0, 0.0], [0.9, 0.1], [0.0, 1.0]],
    )
    results = retriever.candidates_for("query", limit=3)
    assert results[0] == "chat"
    assert results[1] == "chien"
    assert calls == [["query"]]


def test_neither_text_for_nor_vectors_raises():
    try:
        EmbeddingRetriever(["chat"], embed_fn=lambda texts: [[1.0]])
    except ValueError:
        return
    raise AssertionError("expected ValueError when neither text_for nor vectors is given")
