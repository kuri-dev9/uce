from dataclasses import replace
import time
import uuid

from app.adapters.provider_profiles import resolve_profile
from app.adapters.token_counter import estimate_tokens
from app.api.schemas import (
    BuildContextMetadata,
    BuildContextRequest,
    BuildContextResponse,
    CompressedContext,
    Message,
    PromptPack,
)
from app.core import compressor, intent, prompt_synthesizer, ranker, retriever, state_builder, structure_splitter, topic
from app.core.grounding_policy import infer_policy
from app.core.query_rewriter import rewrite_query


SEMANTIC_INTENTS = {"explain", "continue_discussion"}


def build_context(req: BuildContextRequest) -> BuildContextResponse:
    start = time.time()
    trace_id = str(uuid.uuid4())[:8]
    profile = resolve_profile(req.options.target_model)
    max_prompt_tokens = min(req.options.max_prompt_tokens, profile.max_prompt_tokens)
    compression_level = req.options.compression_level or profile.compression_level
    current_message = req.current_message or Message(role="user", content="")
    query_mode = bool(current_message.content.strip())

    if query_mode:
        intent_result = intent.analyze_intent(current_message.content)
        topic_result = topic.detect_topic_relation(
            current_message=current_message,
            recent_messages=req.recent_messages,
            previous_state=req.previous_state,
            options=req.options,
        )
    else:
        intent_result = intent.IntentResult(
            primary_intent="summarize",
            secondary_intents=[],
            confidence=1.0,
            reasoning_mode="summary",
            requires_recent_context=False,
            requires_memory=False,
            requires_structured_output=True,
        )
        topic_result = topic.TopicResult(
            topic_relation="new_topic",
            context_policy="fresh_context",
            confidence=1.0,
            reason="empty current_message; summarizing documents by importance",
            state_overlap=0.0,
            recent_overlap=0.0,
            shift_marker_detected=False,
        )
    policy_recent_messages, policy_previous_state = topic.prepare_inputs_for_policy(
        topic=topic_result,
        recent_messages=req.recent_messages,
        previous_state=req.previous_state,
    )
    policy_memories = topic.filter_memories_for_policy(topic_result, req.optional_memories)
    if intent_result.primary_intent in SEMANTIC_INTENTS:
        compression_level = "semantic"

    rewrite_result = rewrite_query(
        current_message=current_message,
        recent_messages=req.recent_messages,
        previous_state=req.previous_state,
        topic_confidence=topic_result.confidence,
    )
    retrieval_message = (
        Message(role=current_message.role, content=rewrite_result.rewritten_query)
        if rewrite_result.applied
        else current_message
    )
    if rewrite_result.applied:
        intent_result = replace(intent_result, query_type=rewrite_result.query_type)
        if len(policy_recent_messages) < min(6, len(req.recent_messages)):
            policy_recent_messages = req.recent_messages[-6:]
        if req.previous_state:
            policy_previous_state = req.previous_state

    if query_mode:
        context_candidates = retriever.retrieve_context(
            current_message=retrieval_message,
            recent_messages=policy_recent_messages,
            intent_name=intent_result.primary_intent,
            query_type=intent_result.query_type,
            max_items=req.options.max_recent_messages,
        )
        document_query_message = retrieval_message
    else:
        context_candidates = []
        document_query_message = Message(role="user", content="summarize all sections by importance")
    document_chunks = structure_splitter.split_documents(
        documents=req.documents,
        max_chars=req.options.chunk_max_chars,
        overlap_chars=req.options.chunk_overlap_chars,
        enabled=req.options.structure_chunking_enabled,
    )
    document_candidates = retriever.retrieve_document_chunks(
        current_message=document_query_message,
        chunks=document_chunks,
        intent_name=intent_result.primary_intent,
        query_type=intent_result.query_type,
    )
    document_candidates = _apply_continuity_boost(
        document_candidates=document_candidates,
        previous_state=req.previous_state,
        enabled=rewrite_result.applied,
    )
    all_candidates = context_candidates + document_candidates
    if not query_mode:
        selected_limit = len(document_candidates)
    elif document_candidates and intent_result.primary_intent in SEMANTIC_INTENTS:
        selected_limit = min(len(document_candidates), 9)
    elif document_candidates:
        selected_limit = 6
    else:
        selected_limit = 10
    document_min_score = None if not query_mode else _document_min_score(
        document_candidates,
        query_type=intent_result.query_type,
    )
    if document_min_score is not None:
        tentative = [
            candidate
            for candidate in document_candidates
            if candidate.score >= document_min_score
        ]
        if _retrieval_confidence(tentative) < 0.35:
            document_min_score = None
    selected_context, dropped_context = ranker.rank_context_items(
        all_candidates,
        limit=selected_limit,
        min_score=document_min_score,
    )
    if query_mode and document_candidates:
        selected_context, dropped_context = _ensure_document_context(
            selected=selected_context,
            dropped=dropped_context,
            document_candidates=document_candidates,
            limit=selected_limit,
            threshold=document_min_score,
        )
    if not selected_context and intent_result.query_type == "entity":
        selected_context = _entity_fallback_context(document_candidates, selected_limit)
        selected_ids = {item.id for item in selected_context}
        dropped_context = [
            item
            for item in dropped_context + document_candidates
            if item.id not in selected_ids
        ]
    policy_dropped_count = max(0, len(req.recent_messages) - len(policy_recent_messages))
    survived_items, dropped_items, survival_reasons = ranker.survival_metadata(
        selected=selected_context,
        dropped=dropped_context,
        limit=req.options.survival_metadata_limit,
    )
    selected_memories = ranker.rank_memories(policy_memories, limit=8)
    retrieval_confidence = _retrieval_confidence(selected_context)
    retrieval_warning = _retrieval_warning(selected_context, retrieval_confidence)

    state = state_builder.build_state(
        recent_messages=policy_recent_messages,
        current_message=current_message,
        intent=intent_result,
        previous_state=policy_previous_state,
        optional_memories=selected_memories,
    )
    if not query_mode:
        state.current_focus = "전체 문서를 중요도 순으로 압축한다."
        state.user_goal = "질문 없이 입력 문서 전체를 중요도 순으로 정리한다."
    prompt_state = _state_for_prompt_policy(state, topic_result.context_policy)

    compressed = compressor.compress(
        context_items=selected_context,
        state=prompt_state,
        intent=intent_result,
        memories=selected_memories,
        level=compression_level,
    )

    active_policy = infer_policy(
        has_xdr_context=req.has_xdr_context,
        has_dataset_context=req.has_dataset_context,
        has_retrieval_context=req.has_retrieval_context,
        retrieval_count=req.retrieval_count,
        primary_intent=intent_result.primary_intent,
        query_type=intent_result.query_type,
        no_context_selected=len(selected_context) == 0,
        query=current_message.content,
        xdr_schema_hints=req.xdr_schema_hints or None,
    )
    prompt_content = prompt_synthesizer.synthesize(
        current_message=current_message,
        state=prompt_state,
        compressed=compressed,
        intent=intent_result,
        max_tokens=max_prompt_tokens,
        query_type=intent_result.query_type,
        policy=active_policy,
    )

    memory_text = "\n".join(memory.content for memory in req.optional_memories)
    document_text = "\n".join(document.content for document in req.documents)
    state_text = req.previous_state.model_dump_json() if req.previous_state else ""
    original_text = "\n".join(
        [
            current_message.content,
            "\n".join(message.content for message in req.recent_messages),
            memory_text,
            document_text,
            state_text,
        ]
    )
    original_tokens = estimate_tokens(original_text)
    estimated_tokens = estimate_tokens(prompt_content)
    compression_ratio = round(compressed.token_estimate / original_tokens, 2) if original_tokens else 1.0
    latency_ms = int((time.time() - start) * 1000)

    return BuildContextResponse(
        session_id=req.session_id,
        conversation_state=state,
        compressed_context=CompressedContext(
            summary=compressed.summary,
            facts=compressed.facts,
            constraints=compressed.constraints,
            decisions=compressed.decisions,
            open_questions=compressed.open_questions,
            token_estimate=compressed.token_estimate,
        ),
        prompt_pack=PromptPack(
            content=prompt_content,
            estimated_tokens=estimated_tokens,
            original_tokens=original_tokens,
        ),
        metadata=BuildContextMetadata(
            trace_id=trace_id if req.options.include_trace else "",
            primary_intent=intent_result.primary_intent,
            secondary_intents=intent_result.secondary_intents,
            intent_confidence=intent_result.confidence,
            query_type=intent_result.query_type,
            original_query=rewrite_result.original_query,
            rewritten_query=rewrite_result.rewritten_query,
            query_rewrite_applied=rewrite_result.applied,
            query_rewrite_reason=rewrite_result.reason,
            compression_level=compression_level,
            topic_relation=topic_result.topic_relation,
            context_policy=topic_result.context_policy,
            topic_confidence=topic_result.confidence,
            topic_reason=topic_result.reason,
            selected_context_count=len(selected_context),
            dropped_context_count=len(dropped_context) + policy_dropped_count,
            retrieval_confidence=retrieval_confidence,
            retrieval_warning=retrieval_warning,
            compression_ratio=compression_ratio,
            prompt_build_latency_ms=latency_ms,
            provider_profile=profile.name,
            survived_items=survived_items,
            dropped_items=dropped_items,
            survival_reasons=survival_reasons,
            grounding_policy=active_policy.value,
        ),
    )


def _state_for_prompt_policy(state, context_policy: str):
    if context_policy != "fresh_context":
        return state
    prompt_state = state.model_copy(deep=True)
    prompt_state.important_constraints = []
    prompt_state.decisions = []
    prompt_state.open_questions = []
    return prompt_state


def _retrieval_confidence(selected_context) -> float:
    if not selected_context:
        return 0.0
    top_scores = [item.score for item in selected_context[:3]]
    return round(sum(top_scores) / len(top_scores), 4)


def _retrieval_warning(selected_context, retrieval_confidence: float) -> str | None:
    if not selected_context:
        return "no_context_selected"
    if retrieval_confidence < 0.35:
        return "low_relevance_context"
    return None


def _document_min_score(document_candidates, query_type: str = "what") -> float | None:
    if not document_candidates:
        return None
    if query_type == "entity":
        return 0.25
    top_score = max(item.score for item in document_candidates)
    if top_score >= 0.8:
        return max(0.50, round(top_score - 0.25, 4))
    if top_score >= 0.7:
        return max(0.40, round(top_score - 0.25, 4))
    return None


def _ensure_document_context(
    *,
    selected,
    dropped,
    document_candidates,
    limit: int,
    threshold: float | None,
):
    if any(item.item_type == "document_section" for item in selected):
        return selected, dropped
    if not document_candidates:
        return selected, dropped

    best_document = max(document_candidates, key=lambda item: item.score)
    promoted = replace(
        best_document,
        drop_reason=None,
        score_breakdown={
            **best_document.score_breakdown,
            "threshold": threshold,
            "drop_reason": None,
            "forced_document_context": 1.0,
        },
        reason=f"{best_document.reason}, forced document context",
    )
    dropped = [item for item in dropped if item.id != promoted.id]

    if len(selected) < limit:
        return selected + [promoted], dropped

    non_document_indexes = [
        index
        for index, item in enumerate(selected)
        if item.item_type != "document_section"
    ]
    if not non_document_indexes:
        return selected, dropped

    replace_index = non_document_indexes[-1]
    replaced = replace(
        selected[replace_index],
        drop_reason="replaced_by_document_context",
        score_breakdown={
            **selected[replace_index].score_breakdown,
            "drop_reason": "replaced_by_document_context",
        },
    )
    next_selected = list(selected)
    next_selected[replace_index] = promoted
    return next_selected, dropped + [replaced]


def _apply_continuity_boost(document_candidates, previous_state, enabled: bool):
    if not enabled or not previous_state or not document_candidates:
        return document_candidates

    continuity_terms = _continuity_terms(previous_state)
    if not continuity_terms:
        return document_candidates

    boosted = []
    for item in document_candidates:
        searchable = " ".join(
            [
                item.content or "",
                str((item.metadata or {}).get("header_path") or ""),
                str((item.metadata or {}).get("title") or ""),
                item.source or "",
            ]
        ).lower()
        matched_terms = [term for term in continuity_terms if term.lower() in searchable]
        if not matched_terms:
            boosted.append(item)
            continue
        boost = min(0.22, 0.10 + (0.04 * len(matched_terms)))
        boosted.append(
            replace(
                item,
                score=round(min(1.0, item.score + boost), 4),
                reason=f"{item.reason}, conversation continuity boost",
                score_breakdown={
                    **item.score_breakdown,
                    "continuity_boost": round(boost, 4),
                    "continuity_terms": matched_terms,
                    "final_score": round(min(1.0, item.score + boost), 4),
                },
            )
        )
    return sorted(boosted, key=lambda item: item.score, reverse=True)


def _continuity_terms(previous_state) -> list[str]:
    terms = []
    if previous_state.active_topic:
        terms.append(previous_state.active_topic)
        terms.extend(retriever.normalize_text_tokens(previous_state.active_topic))
    terms.extend(previous_state.active_entities or [])
    deduped = []
    seen = set()
    for term in terms:
        normalized = str(term).strip()
        if len(normalized) < 2:
            continue
        key = normalized.lower()
        if key in seen:
            continue
        seen.add(key)
        deduped.append(normalized)
    return deduped[:10]


def _entity_fallback_context(document_candidates, limit: int):
    if not document_candidates:
        return []
    matched = [
        item
        for item in document_candidates
        if item.score_breakdown.get("heading_overlap", 0) > 0
        or item.score_breakdown.get("exact_match_score", 0.0) > 0
    ]
    fallback_items = matched or document_candidates
    selected = sorted(
        fallback_items,
        key=lambda item: (
            item.score_breakdown.get("heading_overlap", 0),
            item.score_breakdown.get("exact_match_score", 0.0),
            item.score,
        ),
        reverse=True,
    )[:limit]
    return [
        replace(
            item,
            score=max(item.score, 0.25),
            reason=f"{item.reason}, entity fallback exact/heading search",
            score_breakdown={
                **item.score_breakdown,
                "entity_fallback": True,
                "threshold": 0.25,
                "drop_reason": None,
            },
        )
        for item in selected
    ]
