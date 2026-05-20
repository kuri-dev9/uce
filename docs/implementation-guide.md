# UCE Implementation Guide
> Version: 0.1  
> Last Updated: 2026-05-19

이 문서는 UCE를 직접 구현하기 위한 컴포넌트별 가이드와 코드 예시를 제공한다.

---

## 1. 프로젝트 구조 만들기

```bash
mkdir -p uce/app/{api,core,adapters,templates}
mkdir -p uce/tests/golden
touch uce/app/main.py
touch uce/app/api/{routes.py,schemas.py}
touch uce/app/core/{orchestrator.py,intent.py,state_builder.py,retriever.py,ranker.py,compressor.py,prompt_synthesizer.py,response_analyzer.py}
touch uce/app/adapters/{memory.py,token_counter.py,provider_profiles.py}
```

---

## 2. 스키마 정의 (schemas.py)

Pydantic v2 기반. API request/response의 전체 타입을 여기서 정의한다.

```python
# app/api/schemas.py
from pydantic import BaseModel, Field
from typing import Optional, Literal
from datetime import datetime


class Message(BaseModel):
    id: Optional[str] = None
    role: Literal["user", "assistant"]
    content: str
    created_at: Optional[datetime] = None


class Memory(BaseModel):
    id: Optional[str] = None
    type: Literal["user_preference", "project_constraint", "decision", "fact", "unresolved_issue"]
    content: str
    importance: float = Field(default=0.5, ge=0.0, le=1.0)
    created_at: Optional[datetime] = None


class ConversationState(BaseModel):
    active_project: Optional[str] = None
    current_focus: Optional[str] = None
    user_goal: Optional[str] = None
    important_constraints: list[str] = []
    open_questions: list[str] = []
    decisions: list[str] = []
    reasoning_mode: Optional[str] = None


class BuildContextOptions(BaseModel):
    max_prompt_tokens: int = 4000
    target_model: str = "generic"
    compression_level: Literal["light", "medium", "aggressive"] = "medium"
    include_trace: bool = True


class BuildContextRequest(BaseModel):
    session_id: str
    current_message: Message
    recent_messages: list[Message] = []
    previous_state: Optional[ConversationState] = None
    optional_memories: list[Memory] = []
    options: BuildContextOptions = BuildContextOptions()


class CompressedContext(BaseModel):
    summary: str
    facts: list[str] = []
    constraints: list[str] = []
    decisions: list[str] = []
    open_questions: list[str] = []
    token_estimate: int = 0


class PromptPack(BaseModel):
    format: str = "structured_text"
    content: str
    estimated_tokens: int
    original_tokens: int


class BuildContextMetadata(BaseModel):
    trace_id: str
    primary_intent: str
    intent_confidence: float
    selected_context_count: int
    dropped_context_count: int
    compression_ratio: float
    prompt_build_latency_ms: int


class BuildContextResponse(BaseModel):
    session_id: str
    conversation_state: ConversationState
    compressed_context: CompressedContext
    prompt_pack: PromptPack
    metadata: BuildContextMetadata


class AnalyzeResponseOptions(BaseModel):
    extract_memory_candidates: bool = True
    extract_open_questions: bool = True


class AnalyzeResponseRequest(BaseModel):
    session_id: str
    current_message: Message
    assistant_response: Message
    conversation_state: ConversationState
    options: AnalyzeResponseOptions = AnalyzeResponseOptions()


class MemoryCandidate(BaseModel):
    type: str
    content: str
    importance: float
    stability: Literal["session", "long_term"] = "session"
    source: str = "assistant_response"
    confidence: float = 0.8


class AnalyzeResponseResponse(BaseModel):
    next_state_patch: dict
    memory_candidates: list[MemoryCandidate] = []
    unresolved_issues: list[str] = []
    metadata: dict
```

---

## 3. Intent Analyzer (intent.py)

MVP: rule-based keyword classifier. confidence가 낮으면 `continue_discussion`으로 fallback.

```python
# app/core/intent.py
import re
from dataclasses import dataclass


INTENT_KEYWORDS: dict[str, list[str]] = {
    "summarize": ["요약", "정리", "summary", "summarize", "요약해", "정리해"],
    "analyze": ["분석", "왜", "원인", "이유", "analyze", "analysis", "어떻게 된"],
    "design": ["설계", "아키텍처", "구조", "design", "architecture", "어떻게 만들"],
    "coding": ["코드", "구현", "함수", "클래스", "버그", "오류", "code", "implement", "fix", "debug"],
    "compare": ["비교", "차이", "vs", "compare", "어떤게 나아"],
    "explain": ["설명", "뭐야", "뭔지", "explain", "what is", "어떤 거야"],
    "decide": ["선택", "결정", "어느 게", "추천", "decide", "recommend"],
    "extract": ["추출", "뽑아", "찾아", "extract", "find"],
    "predict": ["예측", "전망", "가능성", "predict", "forecast"],
}

REASONING_MODE_MAP: dict[str, str] = {
    "summarize": "summary",
    "analyze": "analysis",
    "design": "architecture_design",
    "coding": "code_implementation",
    "compare": "comparative_analysis",
    "explain": "explanation",
    "decide": "decision_making",
    "extract": "extraction",
    "predict": "prediction",
    "continue_discussion": "general",
}


@dataclass
class IntentResult:
    primary_intent: str
    secondary_intents: list[str]
    confidence: float
    reasoning_mode: str
    requires_recent_context: bool
    requires_memory: bool
    requires_structured_output: bool


def analyze_intent(message: str) -> IntentResult:
    message_lower = message.lower()
    scores: dict[str, int] = {}

    for intent, keywords in INTENT_KEYWORDS.items():
        score = sum(1 for kw in keywords if kw in message_lower)
        if score > 0:
            scores[intent] = score

    if not scores:
        return IntentResult(
            primary_intent="continue_discussion",
            secondary_intents=[],
            confidence=0.4,
            reasoning_mode="general",
            requires_recent_context=True,
            requires_memory=False,
            requires_structured_output=False,
        )

    sorted_intents = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    primary = sorted_intents[0][0]
    secondary = [i for i, _ in sorted_intents[1:3]]

    total_score = sum(scores.values())
    primary_score = scores[primary]
    confidence = min(0.95, 0.5 + (primary_score / total_score) * 0.5) if total_score > 0 else 0.5

    # confidence가 낮으면 generic으로
    if confidence < 0.55:
        primary = "continue_discussion"

    return IntentResult(
        primary_intent=primary,
        secondary_intents=secondary,
        confidence=round(confidence, 2),
        reasoning_mode=REASONING_MODE_MAP.get(primary, "general"),
        requires_recent_context=True,
        requires_memory=primary in {"design", "coding", "analyze"},
        requires_structured_output=primary in {"design", "summarize", "compare"},
    )
```

---

## 4. Conversation State Builder (state_builder.py)

previous_state가 있으면 최근 대화 내용으로 patch한다.

```python
# app/core/state_builder.py
from app.api.schemas import ConversationState, Message, Memory
from app.core.intent import IntentResult


def build_state(
    recent_messages: list[Message],
    intent: IntentResult,
    previous_state: ConversationState | None,
    optional_memories: list[Memory],
) -> ConversationState:

    # previous_state 기반으로 시작
    if previous_state:
        state = previous_state.model_copy(deep=True)
    else:
        state = ConversationState()

    # reasoning_mode 업데이트
    state.reasoning_mode = intent.reasoning_mode

    # memory에서 constraints/decisions 보강
    for mem in optional_memories:
        if mem.type == "project_constraint" and mem.content not in state.important_constraints:
            state.important_constraints.append(mem.content)
        elif mem.type == "decision" and mem.content not in state.decisions:
            state.decisions.append(mem.content)

    # 최근 메시지에서 project/focus 추정 (간단한 heuristic)
    if recent_messages:
        last_user_msgs = [m for m in recent_messages[-5:] if m.role == "user"]
        if last_user_msgs and not state.active_project:
            # 프로젝트명 추정: 대문자 단어 또는 명사 클러스터 (MVP는 단순화)
            content = last_user_msgs[-1].content
            if len(content) > 10:
                state.current_focus = content[:60] + "..." if len(content) > 60 else content

    return state
```

---

## 5. Context Retriever (retriever.py)

MVP: 최근 N개 + keyword overlap scoring.

```python
# app/core/retriever.py
from app.api.schemas import Message
from dataclasses import dataclass


@dataclass
class ContextItem:
    id: str
    source: str
    role: str
    content: str
    score: float
    reason: str


def retrieve_context(
    current_message: Message,
    recent_messages: list[Message],
    max_items: int = 15,
) -> list[ContextItem]:

    if not recent_messages:
        return []

    query_words = set(_tokenize(current_message.content))
    results: list[ContextItem] = []

    for i, msg in enumerate(recent_messages):
        msg_words = set(_tokenize(msg.content))
        overlap = len(query_words & msg_words)
        total = len(query_words | msg_words)
        keyword_score = overlap / total if total > 0 else 0.0

        # recency score: 최근일수록 높음
        recency_score = (i + 1) / len(recent_messages)

        score = 0.6 * keyword_score + 0.4 * recency_score

        results.append(ContextItem(
            id=msg.id or f"msg_{i}",
            source="recent_message",
            role=msg.role,
            content=msg.content,
            score=round(score, 3),
            reason=f"keyword_overlap={overlap}, recency={round(recency_score, 2)}",
        ))

    # score 기준 정렬 후 상위 max_items 반환
    results.sort(key=lambda x: x.score, reverse=True)
    return results[:max_items]


def _tokenize(text: str) -> list[str]:
    """간단한 공백/특수문자 기반 토크나이저."""
    import re
    return re.findall(r"[가-힣a-zA-Z0-9]+", text.lower())
```

---

## 6. Semantic Compressor (compressor.py)

MVP: heuristic 기반. 긴 메시지 잘라내기 + 중복 제거 + 구조화 요약.

```python
# app/core/compressor.py
from app.api.schemas import ConversationState, Memory
from app.core.retriever import ContextItem
from app.core.intent import IntentResult
from dataclasses import dataclass


@dataclass
class CompressedContext:
    summary: str
    facts: list[str]
    constraints: list[str]
    decisions: list[str]
    open_questions: list[str]
    token_estimate: int


def compress(
    context_items: list[ContextItem],
    state: ConversationState,
    intent: IntentResult,
    memories: list[Memory],
    level: str = "medium",
) -> CompressedContext:

    max_content_len = {"light": 300, "medium": 150, "aggressive": 80}.get(level, 150)

    # context 요약 생성
    summary_parts = []
    for item in context_items[:8]:  # 상위 8개만
        truncated = item.content[:max_content_len]
        if len(item.content) > max_content_len:
            truncated += "..."
        role_label = "User" if item.role == "user" else "Assistant"
        summary_parts.append(f"{role_label}: {truncated}")

    summary = "\n".join(summary_parts) if summary_parts else "No prior context."

    # constraints: state + memories에서 수집
    constraints = list(state.important_constraints)
    for mem in memories:
        if mem.type == "project_constraint" and mem.content not in constraints:
            constraints.append(mem.content)

    # decisions: state + memories에서 수집
    decisions = list(state.decisions)
    for mem in memories:
        if mem.type == "decision" and mem.content not in decisions:
            decisions.append(mem.content)

    # facts: memories에서 수집
    facts = [m.content for m in memories if m.type == "fact"]

    # token 추정 (한국어 고려: 글자수 / 2 근사)
    total_text = summary + " ".join(constraints + decisions + facts)
    token_estimate = max(1, len(total_text) // 2)

    return CompressedContext(
        summary=summary,
        facts=facts,
        constraints=constraints,
        decisions=decisions,
        open_questions=list(state.open_questions),
        token_estimate=token_estimate,
    )
```

---

## 7. Prompt Synthesizer (prompt_synthesizer.py)

provider-neutral structured text를 생성한다.

```python
# app/core/prompt_synthesizer.py
from app.core.compressor import CompressedContext
from app.core.state_builder import ConversationState
from app.core.intent import IntentResult
from app.api.schemas import Message


PROMPT_TEMPLATE = """\
[System Role]
You are a helpful assistant. Answer the user's question based on the structured context below.

[Current Goal]
{current_goal}

[Intent]
Primary intent: {primary_intent}
Reasoning mode: {reasoning_mode}

[Conversation State]
Project: {active_project}
Focus: {current_focus}

[Relevant Context]
{context_summary}

[Important Constraints]
{constraints}

[Key Decisions]
{decisions}

[Current User Question]
{current_message}
"""


def synthesize(
    current_message: Message,
    state: ConversationState,
    compressed: CompressedContext,
    intent: IntentResult,
    max_tokens: int = 4000,
) -> str:

    constraints_text = "\n".join(f"- {c}" for c in compressed.constraints) or "없음"
    decisions_text = "\n".join(f"- {d}" for d in compressed.decisions) or "없음"

    prompt = PROMPT_TEMPLATE.format(
        current_goal=state.user_goal or state.current_focus or "현재 대화 지속",
        primary_intent=intent.primary_intent,
        reasoning_mode=intent.reasoning_mode,
        active_project=state.active_project or "미지정",
        current_focus=state.current_focus or "미지정",
        context_summary=compressed.summary,
        constraints=constraints_text,
        decisions=decisions_text,
        current_message=current_message.content,
    )

    # token budget 초과 시 context_summary 잘라내기
    estimated = len(prompt) // 2
    if estimated > max_tokens:
        budget_for_context = max(100, max_tokens - (len(prompt) - len(compressed.summary)) // 2)
        trimmed_summary = compressed.summary[: budget_for_context * 2]
        prompt = PROMPT_TEMPLATE.format(
            current_goal=state.user_goal or state.current_focus or "현재 대화 지속",
            primary_intent=intent.primary_intent,
            reasoning_mode=intent.reasoning_mode,
            active_project=state.active_project or "미지정",
            current_focus=state.current_focus or "미지정",
            context_summary=trimmed_summary + "\n(이하 생략)",
            constraints=constraints_text,
            decisions=decisions_text,
            current_message=current_message.content,
        )

    return prompt
```

---

## 8. Orchestrator (orchestrator.py)

모든 컴포넌트를 연결하는 중심 로직.

```python
# app/core/orchestrator.py
import time
import uuid
from app.api.schemas import (
    BuildContextRequest, BuildContextResponse,
    BuildContextMetadata, PromptPack,
    CompressedContext as SchemaCompressedContext,
    AnalyzeResponseRequest, AnalyzeResponseResponse,
    MemoryCandidate,
)
from app.core import intent, state_builder, retriever, ranker, compressor, prompt_synthesizer


def build_context(req: BuildContextRequest) -> BuildContextResponse:
    start = time.time()
    trace_id = str(uuid.uuid4())[:8]

    # 1. Intent 분석
    intent_result = intent.analyze_intent(req.current_message.content)

    # 2. Context 후보 선택
    context_items = retriever.retrieve_context(
        current_message=req.current_message,
        recent_messages=req.recent_messages,
    )

    original_token_estimate = sum(len(m.content) // 2 for m in req.recent_messages)

    # 3. Context 정렬 (MVP: retriever score 그대로 사용)
    selected = context_items[:10]
    dropped_count = max(0, len(context_items) - len(selected))

    # 4. State 구성
    state = state_builder.build_state(
        recent_messages=req.recent_messages,
        intent=intent_result,
        previous_state=req.previous_state,
        optional_memories=req.optional_memories,
    )

    # 5. Semantic 압축
    compressed = compressor.compress(
        context_items=selected,
        state=state,
        intent=intent_result,
        memories=req.optional_memories,
        level=req.options.compression_level,
    )

    # 6. Prompt 합성
    prompt_content = prompt_synthesizer.synthesize(
        current_message=req.current_message,
        state=state,
        compressed=compressed,
        intent=intent_result,
        max_tokens=req.options.max_prompt_tokens,
    )

    estimated_tokens = len(prompt_content) // 2
    compression_ratio = round(estimated_tokens / original_token_estimate, 2) if original_token_estimate > 0 else 1.0
    latency_ms = int((time.time() - start) * 1000)

    return BuildContextResponse(
        session_id=req.session_id,
        conversation_state=state,
        compressed_context=SchemaCompressedContext(
            summary=compressed.summary,
            facts=compressed.facts,
            constraints=compressed.constraints,
            decisions=compressed.decisions,
            open_questions=compressed.open_questions,
            token_estimate=compressed.token_estimate,
        ),
        prompt_pack=PromptPack(
            format="structured_text",
            content=prompt_content,
            estimated_tokens=estimated_tokens,
            original_tokens=original_token_estimate,
        ),
        metadata=BuildContextMetadata(
            trace_id=trace_id,
            primary_intent=intent_result.primary_intent,
            intent_confidence=intent_result.confidence,
            selected_context_count=len(selected),
            dropped_context_count=dropped_count,
            compression_ratio=compression_ratio,
            prompt_build_latency_ms=latency_ms,
        ),
    )


def analyze_response(req: AnalyzeResponseRequest) -> AnalyzeResponseResponse:
    # MVP: 간단한 heuristic 기반 추출
    response_text = req.assistant_response.content

    # 결정사항 추출 (간단한 패턴)
    import re
    decision_patterns = [r"결정[했됩]", r"확정[됩했]", r"채택", r"선택[됩했]"]
    found_decisions = []
    for pattern in decision_patterns:
        if re.search(pattern, response_text):
            # 해당 문장 추출
            sentences = response_text.split(".")
            for s in sentences:
                if re.search(pattern, s) and s.strip():
                    found_decisions.append(s.strip())

    memory_candidates = []
    if req.options.extract_memory_candidates:
        # 중요도 높은 constraint 후보
        if any(kw in response_text for kw in ["중요", "필수", "반드시", "절대"]):
            memory_candidates.append(MemoryCandidate(
                type="project_constraint",
                content=response_text[:100],
                importance=0.75,
                stability="long_term",
                source="assistant_response",
                confidence=0.7,
            ))

    semantic_importance = min(1.0, len(response_text) / 1000)

    return AnalyzeResponseResponse(
        next_state_patch={"decisions": found_decisions} if found_decisions else {},
        memory_candidates=memory_candidates,
        unresolved_issues=[],
        metadata={"semantic_importance": round(semantic_importance, 2)},
    )
```

---

## 9. API Routes (routes.py)

```python
# app/api/routes.py
from fastapi import APIRouter
from app.api.schemas import (
    BuildContextRequest, BuildContextResponse,
    AnalyzeResponseRequest, AnalyzeResponseResponse,
)
from app.core.orchestrator import build_context, analyze_response

router = APIRouter()


@router.post("/build-context", response_model=BuildContextResponse)
def route_build_context(req: BuildContextRequest) -> BuildContextResponse:
    return build_context(req)


@router.post("/analyze-response", response_model=AnalyzeResponseResponse)
def route_analyze_response(req: AnalyzeResponseRequest) -> AnalyzeResponseResponse:
    return analyze_response(req)


@router.get("/health")
def health():
    return {
        "status": "ok",
        "version": "0.1.0",
        "components": {
            "intent_analyzer": "ok",
            "compressor": "ok",
            "prompt_synthesizer": "ok",
        },
    }


@router.get("/status")
def status():
    return {
        "compression_level": "medium",
        "intent_mode": "rule_based",
        "active_provider_profiles": ["ollama_exaone", "generic"],
    }
```

---

## 10. main.py

```python
# app/main.py
from fastapi import FastAPI
from app.api.routes import router

app = FastAPI(title="UCE - Universal Context Engine", version="0.1.0")
app.include_router(router)
```

---

## 11. 테스트 작성

### 기본 단위 테스트

```python
# tests/test_intent.py
from app.core.intent import analyze_intent


def test_coding_intent():
    result = analyze_intent("이 코드 버그 고쳐줘")
    assert result.primary_intent == "coding"
    assert result.confidence > 0.5


def test_summarize_intent():
    result = analyze_intent("지금까지 대화 요약해줘")
    assert result.primary_intent == "summarize"


def test_low_confidence_fallback():
    result = analyze_intent("그래서")
    assert result.primary_intent == "continue_discussion"
```

### 골든 테스트 (prompt 구조 안정성)

```python
# tests/test_golden.py
import json
from pathlib import Path
from app.core.orchestrator import build_context
from app.api.schemas import BuildContextRequest


def test_golden_prompt_structure():
    fixture = json.loads(Path("tests/golden/sample_input.json").read_text())
    req = BuildContextRequest(**fixture)
    response = build_context(req)

    prompt = response.prompt_pack.content
    assert "[System Role]" in prompt
    assert "[Current Goal]" in prompt
    assert "[Current User Question]" in prompt
    assert "[Important Constraints]" in prompt
```

### sample_input.json

```json
{
  "session_id": "test_001",
  "current_message": {
    "role": "user",
    "content": "UCE 아키텍처 설계 도와줘"
  },
  "recent_messages": [
    {
      "role": "user",
      "content": "UCE는 LLM 앞단 미들웨어야",
      "created_at": "2026-05-19T09:00:00+09:00"
    },
    {
      "role": "assistant",
      "content": "네, UCE는 Context Pack을 생성하는 역할이군요.",
      "created_at": "2026-05-19T09:01:00+09:00"
    }
  ],
  "previous_state": {
    "active_project": "UCE",
    "current_focus": "architecture",
    "important_constraints": ["UCE는 stateless middleware"],
    "decisions": [],
    "open_questions": []
  },
  "optional_memories": [],
  "options": {
    "max_prompt_tokens": 4000,
    "target_model": "ollama:exaone3.5:7.8b",
    "compression_level": "medium",
    "include_trace": true
  }
}
```

---

## 12. chat backend 연동 예시 (Python)

UCE를 기존 chat backend에 붙이는 최소 예시.

```python
import httpx
import json

UCE_URL = "http://localhost:8100"
OLLAMA_URL = "http://localhost:11434"

# 세션별 state 저장소 (실제로는 DB 또는 Redis)
session_store: dict[str, dict] = {}


def chat(session_id: str, user_message: str, recent_messages: list[dict]) -> str:
    previous_state = session_store.get(session_id)

    # 1. UCE에서 prompt_pack 받기
    uce_req = {
        "session_id": session_id,
        "current_message": {"role": "user", "content": user_message},
        "recent_messages": recent_messages,
        "previous_state": previous_state,
        "optional_memories": [],
        "options": {
            "max_prompt_tokens": 4000,
            "target_model": "ollama:exaone3.5:7.8b",
            "compression_level": "medium",
            "include_trace": True,
        },
    }

    uce_resp = httpx.post(f"{UCE_URL}/build-context", json=uce_req, timeout=10)
    uce_data = uce_resp.json()

    prompt_pack = uce_data["prompt_pack"]["content"]
    new_state = uce_data["conversation_state"]

    # 2. Ollama에 prompt_pack 전달
    ollama_resp = httpx.post(
        f"{OLLAMA_URL}/api/generate",
        json={"model": "exaone3.5:7.8b", "prompt": prompt_pack, "stream": False},
        timeout=60,
    )
    llm_answer = ollama_resp.json()["response"]

    # 3. UCE로 응답 분석
    analyze_req = {
        "session_id": session_id,
        "current_message": {"role": "user", "content": user_message},
        "assistant_response": {"role": "assistant", "content": llm_answer},
        "conversation_state": new_state,
        "options": {"extract_memory_candidates": True, "extract_open_questions": True},
    }

    analyze_resp = httpx.post(f"{UCE_URL}/analyze-response", json=analyze_req, timeout=10)
    analyze_data = analyze_resp.json()

    # 4. state patch 적용 후 저장
    state_patch = analyze_data.get("next_state_patch", {})
    new_state.update(state_patch)
    session_store[session_id] = new_state

    return llm_answer
```

---

## 13. 구현 순서 권장

1. `schemas.py` — 타입 정의 먼저
2. `intent.py` — 가장 단순하고 독립적
3. `state_builder.py` — intent 결과 활용
4. `retriever.py` — 메시지 scoring
5. `compressor.py` — context 압축
6. `prompt_synthesizer.py` — 최종 prompt 생성
7. `orchestrator.py` — 전체 연결
8. `routes.py` + `main.py` — API 노출
9. 테스트 작성
10. chat backend 연동 테스트
