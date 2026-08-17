"""Free-form Q&A over the RAMQ omnipraticien manual (RAMQManualQueryEngine, backed by
RAMQManualRetriever's BM25+vector fusion search over the `manuel-omnipraticiens` LanceDB
table) — distinct from the transcript -> structured-output extraction pipeline in
app/ramq_codes and app/summary. Answers a physician's direct billing question, sourced
from the manual text itself, rather than proposing codes for a specific encounter.

Public interface — everything else that needs this imports it from here rather than
reaching into .engine/.retriever/.factory/.models directly."""

from app.ramq_chatbot.factory import get_ramq_query_engine
from app.ramq_chatbot.models import RAMQChatMessage, RAMQQueryRequest, RAMQQueryResult

__all__ = ["get_ramq_query_engine", "RAMQChatMessage", "RAMQQueryRequest", "RAMQQueryResult"]
