"""Turns a physician-reviewed extraction into a persisted claim.

Public interface — everything else that needs this imports it from here rather than
reaching into .router/.models/.service/.factory directly."""

from app.claims.router import router as claims_router

__all__ = ["claims_router"]
