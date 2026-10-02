"""The public site's contact form: POST /contact saves a prospect's request and notifies
the team by email (best effort). No login — this is the only write route open to anyone,
hence its tight rate limit and honeypot field.

Public interface — everything else that needs this imports it from here rather than
reaching into .router/.models/.service/.factory/.notifier directly."""

from app.contact.router import router as contact_router

__all__ = ["contact_router"]
