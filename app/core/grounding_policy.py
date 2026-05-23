"""Grounding policy inference for UCE prompt synthesis."""
from __future__ import annotations

from enum import Enum


class GroundingPolicy(str, Enum):
    XDR_ANALYSIS = "xdr_analysis"
    DOCUMENT_RAG = "document_rag"
    HYBRID = "hybrid"
    GENERAL = "general"


def infer_policy(
    *,
    has_xdr_context: bool = False,
    has_dataset_context: bool = False,
    has_retrieval_context: bool = False,
    retrieval_count: int = 0,
    primary_intent: str = "what",
    query_type: str = "what",
) -> GroundingPolicy:
    """Determine the grounding policy from context signal flags.

    Priority: xDR > document RAG > general.
    If both xDR and retrieval context are present, use HYBRID.
    """
    if has_xdr_context:
        if has_retrieval_context and retrieval_count > 0:
            return GroundingPolicy.HYBRID
        return GroundingPolicy.XDR_ANALYSIS
    if has_retrieval_context and retrieval_count > 0:
        return GroundingPolicy.DOCUMENT_RAG
    return GroundingPolicy.GENERAL
