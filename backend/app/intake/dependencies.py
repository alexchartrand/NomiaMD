"""FastAPI glue for the intake routes. The IntakeService itself is built once, at startup, by
app/main.py's lifespan: its queue runs the billing pipeline, which the intake context never
imports (see app/intake/queue.py)."""

from fastapi import Request

from app.intake.connectors import ManualConnector
from app.intake.service import IntakeService


def get_intake_service(request: Request) -> IntakeService:
    return request.app.state.intake_service


def get_manual_connector() -> ManualConnector:
    return ManualConnector()
