"""RAMQ LanceDB access — connection wiring (database.py), row models (models.py), and
repositories (repository.py), mirroring app/postgresdb/'s database/models/repository split.

Public interface for connection wiring and repository access; everything else that needs
this imports LanceDB/CodeRepository/ICodeRepository/DocumentRepository/IDocumentRepository
from here rather than reaching into .database/.repository directly. .models (the validated
CodeRow/DocumentRow shapes) and .converter (the IConverter interface; implementations live in
app/ramq_codes and app/ramq_chatbot) are imported directly by their few callers. Nothing in
this package imports a domain package built on top of it."""

from app.lancedb.code_versions import CurrentCodeTableProvider, ICodeTableProvider, NoCurrentCodesTableError
from app.lancedb.database import LanceDB
from app.lancedb.eligibility import CodeEligibilityFilter, CodeEligibilityWhereBuilder
from app.lancedb.repository import (
    CodeRepository,
    CodeRowLookupError,
    DocumentRepository,
    ICodeCatalogRepository,
    ICodeRepository,
    IDocumentRepository,
)

__all__ = [
    "LanceDB",
    "CurrentCodeTableProvider",
    "ICodeTableProvider",
    "NoCurrentCodesTableError",
    "CodeEligibilityFilter",
    "CodeEligibilityWhereBuilder",
    "CodeRepository",
    "CodeRowLookupError",
    "ICodeCatalogRepository",
    "ICodeRepository",
    "DocumentRepository",
    "IDocumentRepository",
]
