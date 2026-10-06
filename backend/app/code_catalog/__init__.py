"""Searching and looking up RAMQ codes by hand — by number or by description, no LLM and no
embedding call — for the physician adding a code the extraction didn't suggest, billing
without an encounter, or just reading a code's rules. Also holds the process's handle on the
current codes table (registry.py), which app/claims reads a hand-picked code's fees through.

Public interface — everything else that needs this imports it from here rather than
reaching into .router/.service/.registry directly."""

from app.code_catalog.registry import get_code_catalog_repository, init_code_catalog
from app.code_catalog.router import router as code_catalog_router

__all__ = ["code_catalog_router", "get_code_catalog_repository", "init_code_catalog"]
