"""RAMQ LanceDB access — connection wiring (database.py), row models (models.py), and
repositories (repository.py), mirroring app/postgresdb/'s database/models/repository split.

Public interface for connection wiring and repository access; everything else that needs
this imports LanceDB/CodeRepository/ICodeRepository from here rather than reaching into
.database/.repository directly. .converter and .models (CodeRow's shape is purely internal
to the repository/converter pair) are imported directly by their own few callers instead —
importing them here would create a cycle back through app.ramq_codes.models, which
app.lancedb.converter itself depends on."""

from app.lancedb.database import LanceDB
from app.lancedb.repository import CodeRepository, ICodeRepository

__all__ = [
    "LanceDB",
    "CodeRepository",
    "ICodeRepository",
]
