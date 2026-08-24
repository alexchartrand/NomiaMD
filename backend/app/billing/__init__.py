"""Turns a physician-reviewed extraction into a persisted billing record.

Public interface — everything else that needs this imports it from here rather than
reaching into .router/.models/.service/.factory directly."""

from app.billing.router import router as billing_router

__all__ = ["billing_router"]
