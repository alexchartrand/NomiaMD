"""Everything RAMQCodesRetriever knew while building a candidate set, not just the set: which
queries it ran, what each one hit, how the hits fused. The pipeline only needs the
CandidateSet; the benchmark stores the rest to explain a missed code (never retrieved? which
query found it? how far down?)."""

from dataclasses import dataclass

from app.lancedb.eligibility import CodeEligibilityFilter
from app.ramq_codes.eligibility import CandidateSet
from app.ramq_codes.models import Code
from app.ramq_codes.query_planner import PlannedQuery


@dataclass(frozen=True)
class QueryHit:
    number: str
    # LanceDB's own vector+FTS relevance for this query; not comparable across queries.
    relevance: float


@dataclass(frozen=True)
class QueryTrace:
    query: PlannedQuery
    hits: list[QueryHit]


@dataclass(frozen=True)
class FusedCandidate:
    code: Code
    rrf_score: float


@dataclass(frozen=True)
class RetrievalTrace:
    candidate_set: CandidateSet
    queries: list[QueryTrace]
    # Same order as candidate_set.candidates.
    fused: list[FusedCandidate]
    eligibility: CodeEligibilityFilter
    embedding_ms: float
    db_ms: float
