"""The JSON shapes a benchmark run stores. Records hold what a stage *produced* (outputs,
calls, errors), never a score: scoring is derived at report time (scoring.py), so a run can be
re-scored after the fixture's labels change without calling a model again."""

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

from app.llm import LLMCallRecord
from app.ramq_codes import BillingCodesResult
from app.summary import ConsultationSummaryResult

StageName = Literal["summary", "retrieval", "selection"]
QuerySourceName = Literal["summary", "transcript", "summary+transcript"]


class StageError(BaseModel):
    type: str
    message: str
    # What the model actually returned, for an unusable-output error.
    raw_content: str | None = None


class StageTotals(BaseModel):
    calls: int
    input_tokens: int
    output_tokens: int
    # Sum of the calls' own latencies (provider time, or cache time for cached calls).
    llm_latency_ms: float
    # The stage's wall-clock time, everything included.
    wall_ms: float

    @classmethod
    def from_calls(cls, calls: list[LLMCallRecord], wall_ms: float) -> "StageTotals":
        return cls(
            calls=len(calls),
            input_tokens=sum(c.input_tokens or 0 for c in calls),
            output_tokens=sum(c.output_tokens or 0 for c in calls),
            llm_latency_ms=sum(c.latency_ms for c in calls),
            wall_ms=wall_ms,
        )


class StageRecord(BaseModel):
    patient_id: str
    calls: list[LLMCallRecord] = Field(default_factory=list)
    totals: StageTotals
    error: StageError | None = None


class SummaryCheck(BaseModel):
    name: str
    # None when the check doesn't apply (e.g. the note header has no time).
    passed: bool | None
    expected: Any = None
    actual: Any = None


class SummaryRecord(StageRecord):
    model: str | None = None
    result: ConsultationSummaryResult | None = None
    checks: list[SummaryCheck] = Field(default_factory=list)
    stats: dict[str, int | bool] = Field(default_factory=dict)


class QueryHitRecord(BaseModel):
    number: str
    relevance: float


class QueryRecord(BaseModel):
    source: str
    text: str
    # The `header_path` prefixes the search was limited to; None = the whole table.
    sections: list[str] | None = None
    hits: list[QueryHitRecord]


class CandidateRecord(BaseModel):
    rank: int  # 1-based
    number: str
    rrf_score: float
    header_path: str
    description: str
    # Set when the code was added as a sibling of a retrieved one (that one's number).
    expanded_from: str | None = None


class RetrievalRecord(StageRecord):
    query_source: QuerySourceName
    # The run the summary was read from, when the query source needs one.
    summary_run: str | None = None
    queries: list[QueryRecord] = Field(default_factory=list)
    candidates: list[CandidateRecord] = Field(default_factory=list)
    unresolved_axes: list[str] = Field(default_factory=list)
    eligibility: dict[str, Any] = Field(default_factory=dict)
    embedding_ms: float = 0.0
    db_ms: float = 0.0


class SelectionRecord(StageRecord):
    # The runs the candidates (retrieval.json) and the summary were read from.
    candidates_run: str
    summary_run: str
    model: str | None = None
    # The candidate numbers offered to the model, in rank order.
    offered: list[str] = Field(default_factory=list)
    # System prompt + user message, in characters (the tokens are on the call).
    prompt_chars: int = 0
    # What the model returned before BillingCodesTask.parse dropped anything: its code
    # count, the codes that were never offered (invented), and the entries that weren't
    # even code objects.
    raw_code_count: int = 0
    dropped_not_offered: list[str] = Field(default_factory=list)
    dropped_malformed: int = 0
    result: BillingCodesResult | None = None


class RunConfig(BaseModel):
    """Everything that determines a run's outputs. Re-running into an existing run with a
    different config is refused: its records would mix two configurations."""

    stages: list[StageName]
    query_source: QuerySourceName = "summary"
    summaries_from: str | None = None
    summary_model: str | None = None
    llm_provider: str
    embedding_provider: str
    embedding_model: str | None
    codes_table: str
    similarity_top_k: int
    fused_top_k: int
    rrf_k: float
    # 0 = no family expansion (every run recorded before it existed).
    max_family_size: int = 0
    # Query sources whose every hit is kept past fused_top_k; [] before it existed.
    kept_sources: list[str] = []
    # The run whose retrieval records the selection stage reads; None = this run's own.
    candidates_from: str | None = None
    selection_model: str | None = None


class RunManifest(BaseModel):
    name: str
    config: RunConfig
    manual_rev: str
    git_sha: str | None
    git_dirty: bool
    argv: list[str]
    fixture_path: str
    fixture_sha256: str
    case_ids: list[str]
    created_at: datetime
    updated_at: datetime
