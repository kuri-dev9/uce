import re

from app.api.schemas import AnalyzeResponseRequest, AnalyzeResponseResponse, MemoryCandidate
from app.adapters.token_counter import estimate_tokens


DECISION_KEYWORDS = ["결정", "확정", "채택", "선택", "유지하기로", "사용하기로"]
QUESTION_KEYWORDS = ["미정", "필요", "확인", "정해야", "검토"]


def analyze_response(req: AnalyzeResponseRequest) -> AnalyzeResponseResponse:
    text = req.assistant_response.content
    sentences = _split_sentences(text)
    decisions = [sentence for sentence in sentences if any(keyword in sentence for keyword in DECISION_KEYWORDS)]
    unresolved = []
    if req.options.extract_open_questions:
        unresolved = [sentence for sentence in sentences if any(keyword in sentence for keyword in QUESTION_KEYWORDS)][:5]

    memory_candidates: list[MemoryCandidate] = []
    if req.options.extract_memory_candidates:
        for decision in decisions[:5]:
            memory_candidates.append(
                MemoryCandidate(
                    type="decision",
                    content=decision,
                    importance=0.78,
                    stability="session",
                    confidence=0.72,
                )
            )
        for sentence in sentences:
            if "반드시" in sentence or "중요" in sentence or "제약" in sentence:
                memory_candidates.append(
                    MemoryCandidate(
                        type="project_constraint",
                        content=sentence,
                        importance=0.82,
                        stability="long_term",
                        confidence=0.7,
                    )
                )
                break

    next_state_patch = {}
    if req.options.topic_relation or req.options.context_policy:
        next_state_patch["last_topic_transition"] = {
            "topic_relation": req.options.topic_relation,
            "context_policy": req.options.context_policy,
        }
    if decisions:
        merged_decisions = list(req.conversation_state.decisions)
        for decision in decisions:
            if decision not in merged_decisions:
                merged_decisions.append(decision)
        next_state_patch["decisions"] = merged_decisions
    if unresolved:
        next_state_patch["open_questions"] = unresolved

    return AnalyzeResponseResponse(
        next_state_patch=next_state_patch,
        memory_candidates=memory_candidates,
        unresolved_issues=unresolved,
        metadata={
            "semantic_importance": min(1.0, round(estimate_tokens(text) / 1200, 2)),
            "detected_decisions": len(decisions),
            "detected_memory_candidates": len(memory_candidates),
            "topic_relation": req.options.topic_relation,
            "context_policy": req.options.context_policy,
        },
    )


def _split_sentences(text: str) -> list[str]:
    parts = re.split(r"(?<=[.!?。])\s+|\n+", text)
    return [part.strip("- *\t ") for part in parts if part.strip()]
