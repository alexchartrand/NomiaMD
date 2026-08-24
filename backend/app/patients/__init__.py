"""CRUD for a physician's own patient roster.

Public interface — everything else that needs this imports it from here rather than
reaching into .router/.models directly."""

from app.patients.router import router as patients_router

__all__ = ["patients_router"]
