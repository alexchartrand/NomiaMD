"""What saving or voiding a shift claim can refuse."""


class ShiftNotFoundError(Exception):
    pass


class ShiftClaimNotFoundError(Exception):
    pass


class ShiftClaimOnBillError(Exception):
    """The shift's claim is on a bill: frozen until that bill is voided."""


class ShiftClaimConflictError(Exception):
    """Another save of the same shift's claim won the race."""


class EmptyShiftClaimError(Exception):
    pass


class UnknownShiftCodeError(Exception):
    """Not a catalog shift code, or not one the shift's care setting allows."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class HoursExceedShiftError(Exception):
    def __init__(self, code: str, hours: int, shift_hours: int) -> None:
        super().__init__(code)
        self.code = code
        self.hours = hours
        self.shift_hours = shift_hours
