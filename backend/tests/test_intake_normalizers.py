"""app/intake/normalizers — pure text in, text out; no DB."""

from app.extraction.encounter_date import DateOrder
from app.intake import default_normalizers
from app.intake.normalizers import HtmlNormalizer, NormalizerRegistry, PlainTextNormalizer


def test_plain_text_tidies_whitespace_only():
    raw = "\r\n  Motif : toux.  \r\n\r\n\r\n\r\nExamen :\tnormal.\t\r\n\n"
    assert PlainTextNormalizer().normalize(raw) == "Motif : toux.\n\nExamen :\tnormal."


def test_plain_text_keeps_the_text_itself():
    raw = "Patient <vu> à 9 h & reparti."
    assert PlainTextNormalizer().normalize(raw) == raw


def test_equal_notes_normalize_equal_whatever_their_line_endings():
    normalizer = PlainTextNormalizer()
    assert normalizer.normalize("a\r\nb\n") == normalizer.normalize("a\nb")


def test_html_strips_tags_and_keeps_paragraph_breaks():
    raw = "<div><p>Motif : <b>toux</b> depuis\n   3 jours.</p><p>Examen normal.</p></div>"
    assert HtmlNormalizer().normalize(raw) == "Motif : toux depuis 3 jours.\n\nExamen normal."


def test_html_line_breaks_and_list_items_become_lines():
    raw = "Plan :<br>repos<br/>hydratation<ul><li>Tylenol</li><li>Suivi 1 sem.</li></ul>"
    assert HtmlNormalizer().normalize(raw) == "Plan :\nrepos\nhydratation\n\nTylenol\nSuivi 1 sem."


def test_html_decodes_entities_and_drops_scripts_and_styles():
    raw = "<style>p{color:red}</style><p>T&deg; 38,2&nbsp;°C &amp; frissons</p><script>alert(1)</script>"
    assert HtmlNormalizer().normalize(raw) == "T° 38,2 °C & frissons"


def test_html_table_cells_stay_on_their_row():
    raw = "<table><tr><td>TA</td><td>138/86</td></tr><tr><td>FC</td><td>72</td></tr></table>"
    assert HtmlNormalizer().normalize(raw) == "TA 138/86\nFC 72"


def test_normalizers_are_day_first_unless_told_otherwise():
    assert PlainTextNormalizer().date_order == DateOrder.DMY
    assert HtmlNormalizer().date_order == DateOrder.DMY
    assert PlainTextNormalizer(DateOrder.MDY).date_order == DateOrder.MDY


def test_registry_falls_back_to_day_first_plain_text():
    registry = NormalizerRegistry()
    registry.register("omnimed", HtmlNormalizer())
    assert isinstance(registry.for_source("omnimed"), HtmlNormalizer)
    fallback = registry.for_source("inconnu")
    assert isinstance(fallback, PlainTextNormalizer)
    assert fallback.date_order == DateOrder.DMY


def test_default_registry_reads_epic_month_first():
    registry = default_normalizers()
    assert registry.for_source("epic").date_order == DateOrder.MDY
    assert registry.for_source("manual").date_order == DateOrder.DMY
    assert isinstance(registry.for_source("omnimed"), HtmlNormalizer)
