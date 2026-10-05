"""The physician's landing page after login: to-do counts, RAMQ deadline warnings, billing
figures, weekly activity and the latest encounters — one read-only GET /dashboard.

Public interface — everything else that needs this imports it from here rather than
reaching into .router/.models/.service/.factory directly."""

from app.dashboard.router import router as dashboard_router

__all__ = ["dashboard_router"]
