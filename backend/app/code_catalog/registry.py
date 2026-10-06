"""The process's handle on the current RAMQ codes table, for request-time code search and
lookup. Set once by app/bootstrap.py's application_services() — not at import time, since it
needs an already-open LanceDB connection — and by tests' small_reference_table fixture with a
stub."""

from app.lancedb import ICodeCatalogRepository

_codes: ICodeCatalogRepository | None = None


def init_code_catalog(codes: ICodeCatalogRepository) -> None:
    global _codes
    _codes = codes


def get_code_catalog_repository() -> ICodeCatalogRepository:
    if _codes is None:
        raise RuntimeError(
            "Code catalog not initialized — app/bootstrap.py's application_services() must run first"
        )
    return _codes
