from app.adapters.token_counter import estimate_tokens
from app.api.schemas import ConversationState, Message
from app.core.compressor import CompressionResult
from app.core.grounding_policy import GroundingPolicy
from app.core.intent import IntentResult


_BASE_REQUIREMENTS = [
    "- Answer in Korean unless the user asks otherwise.",
    "- Be concrete and implementation-oriented.",
    "- Preserve important constraints and decisions.",
]

_POLICY_RULES: dict[GroundingPolicy, list[str]] = {
    GroundingPolicy.XDR_ANALYSIS: [
        "- 아래 xDR 조사 데이터를 기반으로 markdown 표(| 컬럼 | ... |) 형식으로 답변하세요.",
        "- 데이터에 없는 사실을 추론하거나 가정하지 마세요.",
        "- IMSI 등 식별자는 그대로 표시하되 인덱스 번호를 붙여 구분하세요.",
    ],
    GroundingPolicy.DOCUMENT_RAG: [
        "- 답변은 제공된 컨텍스트에만 근거해야 합니다.",
        "- 약어(acronym)를 임의로 해석하거나 확장하지 마세요.",
        "- 정의가 문서에 없으면 '문서에 명시되지 않음'이라고 답하세요.",
        "- 컨텍스트 외의 일반 지식으로 정의를 보완하지 마세요.",
    ],
    GroundingPolicy.HYBRID: [
        "- xDR 데이터를 우선 근거로 사용하고, 문서 컨텍스트를 보조로 활용하세요.",
        "- 데이터에 없는 사실을 추론하거나 가정하지 마세요.",
        "- 답변은 제공된 컨텍스트에만 근거해야 합니다.",
    ],
}

_QUERY_TYPE_RULES: dict[str, list[str]] = {
    "what": [
        "- 답변은 제공된 컨텍스트에만 근거해야 합니다.",
        "- 약어(acronym)를 임의로 해석하거나 확장하지 마세요.",
        "- 정의가 문서에 없으면 '문서에 명시되지 않음'이라고 답하세요.",
        "- 컨텍스트 외의 일반 지식으로 정의를 보완하지 마세요.",
    ],
    "entity": [
        "- 답변은 제공된 컨텍스트에만 근거해야 합니다.",
        "- 약어(acronym)를 임의로 해석하거나 확장하지 마세요.",
        "- 정의가 문서에 없으면 '문서에 명시되지 않음'이라고 답하세요.",
        "- 컨텍스트 외의 일반 지식으로 정의를 보완하지 마세요.",
    ],
    "where": [
        "- 실행 위치, 배포 환경, 인프라 정보가 명시되지 않은 경우 '문서에 명시되지 않음'이라고 답하세요.",
        "- 클라우드, 서버, 인프라 환경을 임의로 추정하지 마세요.",
    ],
    "config": [
        "- 설정값과 환경변수는 컨텍스트에 명시된 것만 안내하세요.",
        "- 기본값을 임의로 추정하지 마세요.",
    ],
}

_DEFAULT_QUERY_RULES = [
    "- 컨텍스트에 없는 사실을 추론하거나 가정하지 마세요.",
    "- 정보가 부족한 경우 '해당 내용은 제공된 문서에 없습니다'라고 답하세요.",
]


def build_output_requirements(policy: GroundingPolicy, query_type: str = "what") -> str:
    rules = list(_BASE_REQUIREMENTS)
    if policy in _POLICY_RULES:
        rules.extend(_POLICY_RULES[policy])
    else:
        rules.extend(_QUERY_TYPE_RULES.get(query_type, _DEFAULT_QUERY_RULES))
    return "\n".join(rules)


PROMPT_TEMPLATE = """\
[System Role]
You are an assistant operating with a structured context pack.
Use the context below to answer the current user question.
Do not assume that unrelated omitted conversation exists.

[Current Goal]
{current_goal}

[Intent]
Primary intent: {primary_intent}
Secondary intents: {secondary_intents}
Reasoning mode: {reasoning_mode}

[Conversation State]
Active project: {active_project}
Current focus: {current_focus}

[Relevant Context]
{context_summary}

[Important Constraints]
{constraints}

[Key Decisions]
{decisions}

[Open Questions]
{open_questions}

[Relevant Facts]
{facts}

[Output Requirements]
{output_requirements}

[Current User Question]
{current_message}
"""


def synthesize(
    current_message: Message,
    state: ConversationState,
    compressed: CompressionResult,
    intent: IntentResult,
    max_tokens: int,
    query_type: str = "what",
    policy: GroundingPolicy | None = None,
) -> str:
    resolved_query_type = query_type
    if query_type == "what":
        resolved_query_type = getattr(intent, "query_type", query_type)
    resolved_policy = policy if policy is not None else GroundingPolicy.GENERAL
    prompt = _render_prompt(
        current_message,
        state,
        compressed,
        intent,
        compressed.summary,
        resolved_query_type,
        resolved_policy,
    )
    if estimate_tokens(prompt) <= max_tokens:
        return prompt

    fixed_prompt = _render_prompt(
        current_message, state, compressed, intent, "", resolved_query_type, resolved_policy
    )
    fixed_tokens = estimate_tokens(fixed_prompt)
    remaining_tokens = max(100, max_tokens - fixed_tokens)
    trimmed_summary = _trim_by_estimated_tokens(compressed.summary, remaining_tokens)
    return _render_prompt(
        current_message,
        state,
        compressed,
        intent,
        trimmed_summary + "\n- (context truncated by token budget)",
        resolved_query_type,
        resolved_policy,
    )


def _render_prompt(
    current_message: Message,
    state: ConversationState,
    compressed: CompressionResult,
    intent: IntentResult,
    context_summary: str,
    query_type: str,
    policy: GroundingPolicy,
) -> str:
    return PROMPT_TEMPLATE.format(
        current_goal=state.user_goal or state.current_focus or "현재 사용자 요청을 해결한다.",
        primary_intent=intent.primary_intent,
        secondary_intents=", ".join(intent.secondary_intents) or "none",
        reasoning_mode=intent.reasoning_mode,
        active_project=state.active_project or "unknown",
        current_focus=state.current_focus or "unknown",
        context_summary=context_summary or "- No prior relevant context.",
        constraints=_as_bullets(compressed.constraints),
        decisions=_as_bullets(compressed.decisions),
        open_questions=_as_bullets(compressed.open_questions),
        facts=_as_bullets(compressed.facts),
        output_requirements=build_output_requirements(policy, query_type),
        current_message=current_message.content,
    )


def _as_bullets(items: list[str]) -> str:
    return "\n".join(f"- {item}" for item in items) if items else "- none"


def _trim_by_estimated_tokens(text: str, token_budget: int) -> str:
    char_budget = max(120, token_budget * 2)
    if len(text) <= char_budget:
        return text
    kept_lines: list[str] = []
    used_chars = 0
    for line in text.splitlines():
        line_cost = len(line) + 1
        if used_chars + line_cost > char_budget:
            continue
        kept_lines.append(line)
        used_chars += line_cost
    if not kept_lines:
        return "- (context omitted by token budget)"
    kept_lines.append("- (lower-ranked context omitted by token budget)")
    return "\n".join(kept_lines)
