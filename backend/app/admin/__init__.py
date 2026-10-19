"""The admin console's backend (`/admin/*`, admins only): account management, the audit
trail, LLM usage and cost, system status, contact requests and login lockouts. Reads
metadata and counts only — never note text or other patient data.

Public interface — everything else that needs this imports it from here."""

from app.admin.router import router as admin_router

__all__ = ["admin_router"]
