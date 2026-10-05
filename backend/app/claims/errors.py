"""Everything ClaimService (and the helpers it composes) can refuse a request with — mapped
to HTTP statuses in router.py."""


class PatientNotFoundError(Exception):
    pass


class ExtractionRunNotFoundError(Exception):
    pass


class UnknownCodesError(Exception):
    def __init__(self, codes: list[str]):
        self.codes = codes
        super().__init__(f"Unknown codes: {', '.join(codes)}")


class InvalidFeeSelectionError(Exception):
    def __init__(self, code: str, fee_index: int, available: int):
        self.code = code
        self.fee_index = fee_index
        self.available = available
        super().__init__(f"fee_index {fee_index} out of range for code {code} ({available} available)")


class InvalidLieuSelectionError(Exception):
    def __init__(self, code: str, lieu: str):
        self.code = code
        self.lieu = lieu
        super().__init__(f"lieu {lieu!r} is not offered by the chosen fee of code {code}")


class EmptySelectionError(Exception):
    pass


class DuplicateClaimError(Exception):
    def __init__(self, message: str):
        self.message = message
        super().__init__(message)


class DuplicateEncounterClaimError(Exception):
    """The run's encounter was confirmed as another's duplicate (the same visit, received
    twice): only the kept one is billed."""


class ClaimOnBillError(Exception):
    pass


class ClaimNotFoundError(Exception):
    pass


class ClaimEncounterMismatchError(Exception):
    """A claim can only be replaced by one from a run of the same encounter."""
