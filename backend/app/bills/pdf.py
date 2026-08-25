"""Renders a Bill as a PDF invoice. Pure reportlab, no DB/ORM awareness — BillService
assembles a BillDocument from stored data and hands it here, so this class can be unit
tested (or stubbed in BillService's tests) without a database."""

from dataclasses import dataclass
from datetime import date, datetime
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
    fee_amount: float | None


@dataclass
class BillPatientGroup:
    patient_name: str
    ramq_number: str | None
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
    total_amount: float | None
    record_count: int


def _fmt_date(d: date) -> str:
    return d.strftime("%d/%m/%Y")


def _fmt_amount(amount: float | None) -> str:
    return f"{amount:.2f} $" if amount is not None else "—"


class BillPdfRenderer:
    """Builds the detailed-invoice layout: header, then per-patient tables of code lines
    (date/code/fee), then a grand total footer."""

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
            table.setStyle(
                TableStyle(
                    [
                        ("BACKGROUND", (0, 0), (-1, 0), colors.whitesmoke),
                        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                        ("FONTSIZE", (0, 0), (-1, -1), 9),
                        ("GRID", (0, 0), (-1, -1), 0.5, colors.lightgrey),
                        ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ]
                )
            )
            story.append(table)

        story.append(
            Paragraph(
                f"{document.record_count} facturation(s) — Total : {_fmt_amount(document.total_amount)}",
                footer_style,
            )
        )

        doc.build(story)
        return buffer.getvalue()
