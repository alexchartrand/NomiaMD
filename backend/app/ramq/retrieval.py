"""Generic BM25 retrieval, used to narrow large reference tables (RAMQ codes, and later
rule-text chunks) down to a small candidate list that fits in an LLM prompt.

Wrapped behind a small Protocol so the matching engine (lexical/BM25 today) can be swapped
for semantic/embedding-based retrieval later without touching callers — see reference.py's
docstring and the README for the documented scaling path.
"""

import re
import unicodedata
from typing import Callable, Generic, Protocol, Sequence, TypeVar

import snowballstemmer
from rank_bm25 import BM25Okapi

T = TypeVar("T")

_stemmer = snowballstemmer.stemmer("french")

# The manual cites its own section numbers constantly — "(P.C. 13)", "(P.G. 2.2.9 A)",
# "(P.A.D.T. 1.4)" — which tokenize into single letters and bare digits ("c", "g", "p",
# "13", "2") that then look like spurious overlap with any other entry sharing the same
# cross-reference. Other parenthetical content ("(voir ophtalmologie)", "(biopsies
# comprises)") is real indexable text and must survive, so this only strips the citation
# shape specifically rather than all parens.
_CITATION_RE = re.compile(r"\(P\.[^)]*\d[^)]*\)|\(\d+\)")

# Small hand-curated French stopword list — a generic English stopword list is useless for
# Québec French clinical/regulatory text.
_FRENCH_STOPWORDS = frozenset(
    {
        "le", "la", "les", "un", "une", "des", "de", "du", "et", "ou", "a", "au", "aux",
        "en", "dans", "pour", "par", "sur", "avec", "sans", "ce", "cette", "ces", "son",
        "sa", "ses", "que", "qui", "est", "sont", "il", "elle", "ils", "elles", "ne",
        "pas", "non", "plus", "moins", "tout", "tous", "toute", "toutes", "se", "leur",
        "leurs", "d", "l", "qu", "n",
    }
)

_TOKEN_RE = re.compile(r"[a-z0-9]+")


def _fold_accents(text: str) -> str:
    normalized = unicodedata.normalize("NFKD", text)
    return "".join(ch for ch in normalized if not unicodedata.combining(ch))


def tokenize(text: str) -> list[str]:
    """Strip citation boilerplate, lowercase, accent-fold (é→e), drop French stopwords,
    and stem.

    Accent-folding matters here specifically: transcripts and the manual are both Québec
    French, and inconsistent accent usage (copy-paste artifacts, typing shortcuts) shouldn't
    cause a real match to score zero.

    Stemming matters just as much: the manual's terse fragment descriptions are often
    singular/differently-inflected from how a transcript phrases the same thing (a code's
    own text says "plaies", a transcript says "plaie") — without stemming those never
    overlap at all, so a candidate can silently never be retrievable no matter the query.
    """
    text = _CITATION_RE.sub(" ", text)
    folded = _fold_accents(text.lower())
    tokens = [tok for tok in _TOKEN_RE.findall(folded) if tok not in _FRENCH_STOPWORDS]
    return _stemmer.stemWords(tokens)


class Retriever(Protocol[T]):
    def candidates_for(self, query: str, limit: int) -> list[T]: ...


class BM25Retriever(Generic[T]):
    """BM25 index over an arbitrary list of items, given a function to extract each item's
    indexable text. Generic so it can index RamqCode descriptions today and RamqRuleChunk
    text later without a second implementation."""

    def __init__(self, items: Sequence[T], text_for: Callable[[T], str]):
        self._items = list(items)
        corpus = [tokenize(text_for(item)) for item in self._items]
        self._bm25 = BM25Okapi(corpus) if corpus else None

    def candidates_for(self, query: str, limit: int) -> list[T]:
        if self._bm25 is None:
            return []
        scores = self._bm25.get_scores(tokenize(query))
        ranked = sorted(zip(scores, self._items), key=lambda pair: pair[0], reverse=True)
        return [item for score, item in ranked[:limit] if score > 0]
