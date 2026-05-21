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

    if query_mode:
        context_candidates = retriever.retrieve_context(
            current_message=current_message,
            recent_messages=policy_recent_messages,
            intent_name=intent_result.primary_intent,
            query_type=intent_result.query_type,
            max_items=req.options.max_recent_messages,
        )
        document_query_message = current_message
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
    all_candidates = context_candidates + document_candidates
    if not query_mode:
        selected_limit = len(document_candidates)
    elif document_candidates and intent_result.primary_intent in SEMANTIC_INTENTS:
        selected_limit = min(len(document_candidates), 9)
    elif document_candidates:
        selected_limit = 6
    else:
        selected_limit = 10
    document_min_score = None if not query_mode else _document_min_score(document_candidates)
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

    prompt_content = prompt_synthesizer.synthesize(
        current_message=current_message,
        state=prompt_state,
        compressed=compressed,
        intent=intent_result,
        max_tokens=max_prompt_tokens,
        query_type=intent_result.query_type,
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


def _document_min_score(document_candidates) -> float | None:
    if not document_candidates:
        return None
    top_score = max(item.score for item in document_candidates)
    if top_score >= 0.8:
        return max(0.50, round(top_score - 0.25, 4))
    if top_score >= 0.7:
        return max(0.40, round(top_score - 0.25, 4))
    return None
