"""Renders a Bill as a PDF invoice. Pure reportlab, no DB/ORM awareness — BillService
assembles a BillDocument from stored data and hands it here, so this class can be unit
tested (or stubbed in BillService's tests) without a database."""

from dataclasses import dataclass, field
from datetime import date, datetime, time
from decimal import Decimal
from io import BytesIO

from reportlab.lib import colors
from reportlab.lib.enums import TA_RIGHT
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle


@dataclass
class BillLineItem:
    service_date: date
    code: str
    fee_amount: Decimal | None
    # A shift code's hours; None on a patient's code.
    hours: int | None = None


@dataclass
class BillPatientGroup:
    patient_name: str
    ramq_number: str | None
    lines: list[BillLineItem]


@dataclass
class BillShiftGroup:
    """A shift's own codes: billed for the hours worked, no patient and no NAM."""

    work_site_name: str
    service_date: date
    start_time: time
    end_time: time
    lines: list[BillLineItem]


@dataclass
class BillDocument:
    number: str
    start_date: date
    end_date: date
    generated_at: datetime
    physician_name: str
    physician_type: str | None
    patient_groups: list[BillPatientGroup]
    total_amount: Decimal | None
    claim_count: int
    shift_groups: list[BillShiftGroup] = field(default_factory=list)


def _fmt_date(d: date) -> str:
    return d.strftime("%d/%m/%Y")


def _fmt_amount(amount: Decimal | None) -> str:
    return f"{amount:.2f} $" if amount is not None else "—"


def _fmt_time(t: time, *, end: bool = False) -> str:
    """RAMQ's way: "20 h", "20 h 30"; a shift ending at midnight ends at "24 h"."""
    hour = 24 if end and t == time(0) else t.hour
    return f"{hour} h {t.minute:02d}" if t.minute else f"{hour} h"


_TABLE_STYLE = TableStyle(
    [
        ("BACKGROUND", (0, 0), (-1, 0), colors.whitesmoke),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.lightgrey),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ]
)


class BillPdfRenderer:
    """Builds the detailed-invoice layout: header, then per-patient tables of code lines
    (date/code/fee), then per-shift tables (date/code/hours/fee), then a grand total footer."""

    def render(self, document: BillDocument) -> bytes:
        buffer = BytesIO()
        doc = SimpleDocTemplate(
            buffer,
            pagesize=letter,
            leftMargin=2 * cm,
            rightMargin=2 * cm,
            topMargin=2 * cm,
            bottomMargin=2 * cm,
            title=f"Facture {document.number}",
        )
        styles = getSampleStyleSheet()
        title_style = ParagraphStyle("BillTitle", parent=styles["Title"], fontSize=16, spaceAfter=4)
        meta_style = ParagraphStyle("BillMeta", parent=styles["Normal"], fontSize=10, textColor=colors.grey)
        group_style = ParagraphStyle("PatientGroup", parent=styles["Heading3"], spaceBefore=14, spaceAfter=4)
        footer_style = ParagraphStyle(
            "BillFooter", parent=styles["Normal"], fontSize=11, alignment=TA_RIGHT, spaceBefore=10
        )

        physician_line = document.physician_name
        if document.physician_type:
            physician_line += f" — {document.physician_type}"

        story = [
            Paragraph(f"Facture {document.number}", title_style),
            Paragraph(physician_line, meta_style),
            Paragraph(
                f"Période du {_fmt_date(document.start_date)} au {_fmt_date(document.end_date)}", meta_style
            ),
            Paragraph(f"Générée le {_fmt_date(document.generated_at.date())}", meta_style),
            Spacer(1, 0.6 * cm),
        ]

        for group in document.patient_groups:
            header = group.patient_name
            if group.ramq_number:
                header += f" — {group.ramq_number}"
            story.append(Paragraph(header, group_style))

            rows = [["Date", "Code", "Honoraire"]]
            for line in group.lines:
                rows.append([_fmt_date(line.service_date), line.code, _fmt_amount(line.fee_amount)])
            table = Table(rows, colWidths=[3 * cm, 4 * cm, 3 * cm], hAlign="LEFT")
            table.setStyle(_TABLE_STYLE)
            story.append(table)

        for shift in document.shift_groups:
            story.append(
                Paragraph(
                    f"Quart — {shift.work_site_name}, {_fmt_time(shift.start_time)} à {_fmt_time(shift.end_time, end=True)}"
                    " (aucun NAM requis)",
                    group_style,
                )
            )
            rows = [["Date", "Code", "Heures", "Honoraire"]]
            for line in shift.lines:
                rows.append([_fmt_date(line.service_date), line.code, str(line.hours), _fmt_amount(line.fee_amount)])
            table = Table(rows, colWidths=[3 * cm, 4 * cm, 2 * cm, 3 * cm], hAlign="LEFT")
            table.setStyle(_TABLE_STYLE)
            story.append(table)

        story.append(
            Paragraph(
                f"{document.claim_count} facturation(s) — Total : {_fmt_amount(document.total_amount)}",
                footer_style,
            )
        )

        doc.build(story)
        return buffer.getvalue()
