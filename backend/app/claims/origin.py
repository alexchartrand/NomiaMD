"""Where a claim and its code lines come from — shared vocabulary between the claim services,
the stored rows (ClaimCode.origin, Claim.source_system) and the API."""

from enum import Enum


class CodeOrigin(str, Enum):
    # Offered by the claim's extraction run.
    SUGGESTED = "suggested"
    # Added by the physician from the code search (app/code_catalog/).
    MANUAL = "manual"


# Claim.source_system of a claim billed without an encounter: there's no note to snapshot the
# source of. Not derivable from a NULL extraction_run_id — the retention purge nulls that too.
MANUAL_SOURCE_SYSTEM = "manual"
