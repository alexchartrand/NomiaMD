"""RAMQ's billing deadline: a claim must reach the RAMQ within 90 days of the service date,
or it's refused (barring exceptional circumstances). Pure date arithmetic.

TODO: confirm the 90-day limit and the warning window with the clinic."""

from datetime import date


class BillingDeadline:
    def __init__(self, deadline_days: int = 90, warning_days: int = 15) -> None:
        self._deadline_days = deadline_days
        self._warning_days = warning_days

    @property
    def deadline_days(self) -> int:
        return self._deadline_days

    def days_left(self, service_date: date, today: date) -> int:
        """Negative once the deadline has passed; 0 is the last day."""
        return self._deadline_days - (today - service_date).days

    def is_at_risk(self, days_left: int) -> bool:
        return days_left <= self._warning_days
