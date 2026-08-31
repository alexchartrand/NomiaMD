"""ReciprocalRankFuser moved to app/lancedb/fusion.py once app/ramq_codes' retriever needed
the same RRF logic keyed on a different identity field (Code.number instead of
DocumentRow.id) — see that module's docstring. Re-exported here so existing imports
(app/ramq_chatbot/retriever.py, factory.py, and this package's own tests) don't need to
change their import path."""

from app.lancedb.fusion import ReciprocalRankFuser

__all__ = ["ReciprocalRankFuser"]
