"""The consultation_summary task: transcript -> structured RAMQ-relevant facts.

Public interface — everything else that needs this task imports it from here rather than
reaching into .models/.task directly."""

from app.tasks.summary.models import ConsultationSummaryResult
from app.tasks.summary.task import ConsultationSummaryTask, render_for_billing_codes

__all__ = ["ConsultationSummaryResult", "ConsultationSummaryTask", "render_for_billing_codes"]
