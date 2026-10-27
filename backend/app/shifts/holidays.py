"""The Entente's jours fériés (omnipraticien manual, préambule général, P.G. 2.4.7.6), on their
nominal dates.

Not the whole truth: in an établissement, RAMQ recognizes the dates the établissement grants
its professional staff (sent to RAMQ before April 30), and RAMQ's own published calendar may
move a holiday that falls on a weekend. Neither is available here yet, so a site-specific
calendar is a later addition — until then this is the default every site reads."""

from datetime import date, timedelta
from functools import lru_cache

_MONDAY = 0


def _easter_sunday(year: int) -> date:
    """Gregorian Easter (anonymous Gregorian algorithm)."""
    a = year % 19
    b, c = divmod(year, 100)
    d, e = divmod(b, 4)
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = divmod(c, 4)
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    month, day = divmod(h + l - 7 * m + 114, 31)
    return date(year, month, day + 1)


def _nth_monday(year: int, month: int, n: int) -> date:
    first = date(year, month, 1)
    return first + timedelta(days=(_MONDAY - first.weekday()) % 7 + 7 * (n - 1))


def _monday_before(day: date) -> date:
    """The last Monday strictly before `day` — Fête de Dollard is the Monday before May 25."""
    return day - timedelta(days=(day.weekday() - _MONDAY) % 7 or 7)


class QuebecHolidays:
    """The Entente's 13 jours fériés, per year."""

    def is_holiday(self, day: date) -> bool:
        return day in self.for_year(day.year)

    def name(self, day: date) -> str | None:
        return self.for_year(day.year).get(day)

    @staticmethod
    @lru_cache(maxsize=32)
    def for_year(year: int) -> dict[date, str]:
        easter = _easter_sunday(year)
        return {
            date(year, 1, 1): "Jour de l'An",
            date(year, 1, 2): "Lendemain du Jour de l'An",
            easter - timedelta(days=2): "Vendredi saint",
            easter + timedelta(days=1): "Lundi de Pâques",
            _monday_before(date(year, 5, 25)): "Fête de Dollard",
            date(year, 6, 24): "Fête nationale",
            date(year, 7, 1): "Fête de la Confédération",
            _nth_monday(year, 9, 1): "Fête du Travail",
            _nth_monday(year, 10, 2): "Action de grâces",
            date(year, 12, 24): "Veille de Noël",
            date(year, 12, 25): "Noël",
            date(year, 12, 26): "Lendemain de Noël",
            date(year, 12, 31): "Veille du Jour de l'An",
        }
