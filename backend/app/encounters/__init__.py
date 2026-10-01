"""The physician's inbox of received encounters: one day's list with derived statuses,
an encounter's detail with its latest extraction, the manual patient pick and on-demand
extraction. Built on app/intake (where notes come from) and app/extraction (what's done with
them) — the one place the two meet over HTTP, which is why it isn't part of intake.

Public interface — everything else that needs this imports it from here."""

from app.encounters.router import router as encounters_router

__all__ = ["encounters_router"]
