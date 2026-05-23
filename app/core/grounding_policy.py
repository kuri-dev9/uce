"""Grounding policy inference for UCE prompt synthesis."""
from __future__ import annotations

from enum import Enum


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
) -> GroundingPolicy:
    """Determine the grounding policy from context signal flags.

    Priority:
    1. no_context_selected → GENERAL (strict grounding would be vacuous)
    2. xDR context present → XDR_ANALYSIS (HYBRID when retrieval also present)
    3. retrieval context present → DOCUMENT_GROUNDED
    4. fallback → GENERAL
    """
    if no_context_selected or (retrieval_count == 0 and not has_xdr_context):
        return GroundingPolicy.GENERAL

    if has_xdr_context:
        if has_retrieval_context and retrieval_count > 0:
            return GroundingPolicy.HYBRID
        return GroundingPolicy.XDR_ANALYSIS

    if has_retrieval_context and retrieval_count > 0:
        return GroundingPolicy.DOCUMENT_GROUNDED

    return GroundingPolicy.GENERAL
