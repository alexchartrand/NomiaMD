import logging
from abc import ABC, abstractmethod
from dataclasses import asdict

from app.ramq_codes.candidate_fuser import CandidateFuser
from app.ramq_codes.context import BillingContext
from app.ramq_codes.eligibility import CandidateSet, EligibilityFilterFactory
from app.ramq_codes.family_expander import FamilyExpander
from app.ramq_codes.query_planner import SummaryQueryPlanner
from app.ramq_codes.query_runner import CodeQueryRunner
from app.summary.models import ConsultationSummaryResult

__all__ = ["ICodesRetriever", "RAMQCodesRetriever"]

logger = logging.getLogger(__name__)


class ICodesRetriever(ABC):
    @abstractmethod
    async def aretrieve(self, summary: ConsultationSummaryResult, context: BillingContext) -> CandidateSet:
        pass


class RAMQCodesRetriever(ICodesRetriever):
    """The pipeline's retrieval, composed of its steps: SummaryQueryPlanner fans the summary
    out into structural per-concept queries (one for the visit, one per procedure/add-on —
    see query_planner.py), EligibilityFilterFactory resolves the prefilter from the
    BillingContext (eligibility.py), CodeQueryRunner runs each query as a hybrid search
    (query_runner.py), CandidateFuser fuses them and names the axes left unresolved
    (candidate_fuser.py), and FamilyExpander adds the retrieved codes' eligible variants
    (family_expander.py).

    Only the CandidateSet comes out. The benchmark (app/benchmark/stages.py's
    RetrievalStage) composes the same steps itself to keep what each one produced."""

    def __init__(
        self,
        query_runner: CodeQueryRunner,
        candidate_fuser: CandidateFuser,
        family_expander: FamilyExpander | None = None,
        query_planner: SummaryQueryPlanner | None = None,
        filter_factory: EligibilityFilterFactory | None = None,
    ):
        """`family_expander`: None = no expansion."""
        self._query_runner = query_runner
        self._candidate_fuser = candidate_fuser
        self._family_expander = family_expander
        self._query_planner = query_planner or SummaryQueryPlanner()
        self._filter_factory = filter_factory or EligibilityFilterFactory()

    async def aretrieve(self, summary: ConsultationSummaryResult, context: BillingContext) -> CandidateSet:
        eligibility = self._filter_factory.from_context(context)
        query_run = await self._query_runner.run(self._query_planner.plan_labeled(summary), eligibility)
        fused = self._candidate_fuser.fuse(query_run.results, context)
        if self._family_expander is not None:
            fused = await self._family_expander.expand(fused, eligibility, context)
        candidate_set = fused.candidate_set

        logger.debug(
            "RAMQCodesRetriever.aretrieve result",
            extra={
                "candidates": [{"number": code.number, "description": code.description} for code in candidate_set.candidates],
                "candidate_count": len(candidate_set.candidates),
                "eligibility": asdict(eligibility),
                "unresolved_axes": list(candidate_set.unresolved_axes),
            },
        )
        return candidate_set
