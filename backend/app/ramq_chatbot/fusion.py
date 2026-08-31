"""ReciprocalRankFuser moved to app/lancedb/fusion.py once app/ramq_codes' retriever needed
the same RRF logic keyed on a different identity field (Code.number instead of
DocumentRow.id) — see that module's docstring. Re-exported here for
tests/test_ramq_chatbot_fusion.py's import path; app/ramq_chatbot/retriever.py and
factory.py no longer use RRF fusion at all (single query in, single hybrid_search call
out — see retriever.py's docstring), so they import nothing from this module."""

from app.lancedb.fusion import ReciprocalRankFuser

__all__ = ["ReciprocalRankFuser"]
