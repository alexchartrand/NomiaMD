"""Turns a set of physician-confirmed billing records into a generated, downloadable
invoice (a Bill). The PDF is rendered on demand from each record's own already-snapshotted
code rows — nothing is stored as bytes.

Public interface — everything else that needs this imports it from here rather than
reaching into .router/.models/.service/.factory/.pdf directly."""

from app.bills.router import router as bills_router

__all__ = ["bills_router"]
