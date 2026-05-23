"""Grounding policy inference for UCE prompt synthesis."""
from __future__ import annotations

from enum import Enum

from app.core.xdr_relevance import compute_xdr_relevance


class GroundingPolicy(str, Enum):
    GENERAL = "general"
    DOCUMENT_GROUNDED = "document_grounded"
    XDR_ANALYSIS = "xdr_analysis"
    HYBRID = "hybrid"


def infer_policy(
    *,
    has_xdr_context: bool = False,
    has_dataset_context: bool = False,
    has_retrieval_context: bool = False,
    retrieval_count: int = 0,
    primary_intent: str = "what",
    query_type: str = "what",
    no_context_selected: bool = False,
    query: str = "",
    xdr_schema_hints: list[dict] | None = None,
) -> GroundingPolicy:
    """Context signal + schema hints 기반 GroundingPolicy runtime inference.

    Priority:
    1. no_context_selected AND not xdr_related → GENERAL
    2. has_xdr_context (실제 xDR 결과 있음) → XDR_ANALYSIS (HYBRID when retrieval also present)
    3. has_dataset_context AND schema relevance detected → XDR_ANALYSIS
    4. has_retrieval_context → DOCUMENT_GROUNDED
    5. fallback → GENERAL
    """
    xdr_schema_related = False
    if has_dataset_context and query and xdr_schema_hints:
        xdr_schema_related, _ = compute_xdr_relevance(
            query=query,
            schema_hints=xdr_schema_hints,
        )

    if no_context_selected and not has_xdr_context and not xdr_schema_related:
        return GroundingPolicy.GENERAL

    if has_xdr_context:
        if has_retrieval_context and retrieval_count > 0:
            return GroundingPolicy.HYBRID
        return GroundingPolicy.XDR_ANALYSIS

    if has_dataset_context and xdr_schema_related:
        return GroundingPolicy.XDR_ANALYSIS

    if has_retrieval_context and retrieval_count > 0:
        return GroundingPolicy.DOCUMENT_GROUNDED

    return GroundingPolicy.GENERAL
