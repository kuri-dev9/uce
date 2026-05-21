# UCE Architecture Document
> Project: Universal Context Engine  
> Version: 0.5
> Last Updated: 2026-05-20

---

## 1. Project Overview

UCE(Universal Context Engine)는 LLM 앞단에서 동작하는 범용 Context Engineering Middleware이다.

UCE의 목적은 AI 모델을 직접 대체하거나, RAG 시스템 전체를 구현하거나, Vector DB 플랫폼을 제공하는 것이 아니다. UCE는 사용자의 현재 입력, 최근 대화 흐름, 일부 외부 메모리, 세션 상태를 조합하여 LLM이 추론하기 좋은 형태의 `Context Pack`을 생성한다.

핵심 정의:

```text
UCE = LLM이 사고하기 좋은 입력 상태를 생성하는 Context Orchestrator
```

기존 AI 시스템 흐름:

```text
User Input -> LLM -> Response
```

UCE 기반 시스템 흐름:

```text
User Input
  -> Intent Analysis
  -> Context Retrieval
  -> Conversation State Construction
  -> Semantic Compression
  -> Prompt Synthesis
  -> LLM
  -> Response
  -> Response Analysis
```

UCE의 중심 가치는 모델 성능 자체를 올리는 것이 아니라, 모델이 더 적은 토큰으로 더 일관된 reasoning을 수행할 수 있도록 입력 상태를 정돈하는 데 있다.

현재 구현 상태:

- Phase 1 Context Pack MVP 완료
- Phase 2 Practical Context Engineering 완료
- markdown/text/code/docx/xlsx 입력 처리 지원
- section-level retrieval + explainable scoring 구현
- queryless document compression mode 지원
- reasondock optional middleware 통합 검증 완료

---

## 2. 핵심 원칙

### 2.1 UCE는 텍스트를 줄이는 것이 아니라 정돈하는 것이다

UCE의 Semantic Compressor는 단순히 텍스트를 요약하지 않는다. 관련 없는 대화는 버리고, 관련 있는 대화는 핵심만 압축하여 유지하며, 목표/제약/결정사항은 압축 없이 그대로 보존한다. 결과적으로 토큰은 줄어들지만 LLM 입장에서는 더 많은 정보를 더 짧게 받는다.

### 2.2 UCE는 완전한 Stateless Middleware이다

UCE는 아무것도 저장하지 않는다. 대화 흐름, 세션 상태, 메모리 — 모두 호출하는 application이 들고 있어야 한다. UCE는 매 요청마다 state를 받아서 처리하고 업데이트된 state를 돌려줄 뿐이다.

```text
UCE interprets state. Application owns state.
```

```text
1턴: backend → (state=없음) → UCE → state 생성 반환 → backend 저장
2턴: backend → (state=1턴것) → UCE → state 업데이트 반환 → backend 저장
```

이 설계로 UCE는 DB 없이 수평 확장이 가능하고, 기존 시스템에 add-on으로 붙이기 쉽다.

### 2.3 UCE는 RAG가 아니다

UCE는 외부 지식을 검색하는 시스템이 아니다. UCE는 현재 대화에서 필요한 정보를 조립하는 시스템이다. RAG 결과가 있다면 UCE의 context source 중 하나로 사용할 수 있다.

```text
RAG retrieves evidence.
UCE maintains reasoning state.
```

### 2.4 Own the assembly. Do not own the world.

UCE는 모든 데이터를 소유하지 않는다. 현재 reasoning에 필요한 정보를 작고 명확하고 구조적인 입력 상태로 만드는 역할에만 집중한다.

---

## 3. 문제 정의

Local LLM 및 일반 LLM 기반 애플리케이션은 대화가 길어질수록 다음 문제가 발생한다.

| 문제 | 설명 |
|------|------|
| Conversation Continuity Loss | 모델이 이전 대화 전체를 안정적으로 기억하지 못함. Local LLM은 context window 제약이 더 심각함 |
| Repeated Explanation | 사용자가 프로젝트 배경, 제약, 결정사항을 반복 설명해야 함 |
| Token Waste | 긴 대화를 그대로 넣으면 token budget이 빠르게 소모됨 |
| Weak Intent Understanding | "이거 정리해줘" 같은 문장이 상황에 따라 의미가 달라짐 |
| Prompt Engineering Burden | 사용자가 매번 좋은 prompt를 직접 작성해야 함 |

---

## 4. 시스템 범위

### 4.1 UCE가 하는 것

- current user message 분석
- intent classification
- 최근 대화 기반 context retrieval
- conversation state 구성
- semantic compression
- context ranking
- prompt pack 생성
- response analysis
- memory write candidate 추출
- metadata 및 trace 생성

### 4.2 UCE가 하지 않는 것

- LLM 학습 또는 fine-tuning
- LLM provider 구현 또는 직접 호출 (기본값)
- full RAG pipeline 구현
- 대규모 Vector DB 운영
- 장기 기억 DB 소유
- agent planning 및 tool execution
- application session ownership
- user identity system

### 4.3 경계

UCE는 context를 만들고, application이 LLM을 호출한다.

```text
어떤 backend든
    ↓ POST /build-context
   UCE
    ↓ prompt_pack 반환
어떤 backend든
    ↓
   LLM (Ollama, OpenAI, Claude 등)
    ↓ response
어떤 backend든
    ↓ POST /analyze-response
   UCE
    ↓ state_patch, memory_candidates 반환
어떤 backend든 (state 저장 여부 결정)
```

---

## 5. 고수준 아키텍처

```text
                         ┌──────────────────────┐
                         │      Application      │
                         │   (어떤 backend든)    │
                         └──────────┬───────────┘
                                    │
                                    ▼
                         ┌──────────────────────┐
                         │       UCE API         │
                         │ /build-context        │
                         │ /analyze-response     │
                         │ /health               │
                         └──────────┬───────────┘
                                    │
            ┌───────────────────────┼───────────────────────┐
            ▼                       ▼                       ▼
 ┌──────────────────┐    ┌──────────────────────┐  ┌──────────────────┐
 │ Intent Analyzer  │    │ Recent Context        │  │ External Memory  │
 │                  │    │ Retriever             │  │ Adapter          │
 └────────┬─────────┘    └──────────┬───────────┘  └────────┬─────────┘
          │                         │                       │
          └──────────────┬──────────┴──────────────┬────────┘
                         ▼                         ▼
              ┌──────────────────────┐  ┌──────────────────┐
              │ Conversation State    │  │ Context Ranker   │
              │ Builder               │  │                  │
              └──────────┬───────────┘  └────────┬─────────┘
                         │                       │
                         └───────────┬───────────┘
                                     ▼
                          ┌─────────────────────┐
                          │ Semantic Compressor │
                          └──────────┬──────────┘
                                     ▼
                          ┌─────────────────────┐
                          │ Prompt Synthesizer  │
                          └──────────┬──────────┘
                                     ▼
                          ┌─────────────────────┐
                          │ Context Pack Output │
                          └─────────────────────┘
```

---

## 6. 컴포넌트 설계

### 6.1 UCE API Layer

application과 UCE 사이의 stable contract를 제공한다.

- request validation
- schema normalization
- component orchestration
- response metadata 구성
- error handling
- trace id 생성

MVP: FastAPI 기반 HTTP API

### 6.2 Intent Analyzer

현재 사용자 입력의 목적을 분류하고, prompt assembly 전략 결정에 필요한 힌트를 생성한다.

| Intent | Description |
|--------|-------------|
| `continue_discussion` | 이전 흐름을 이어서 논의 |
| `summarize` | 대화, 문서, 결정 사항 요약 |
| `analyze` | 원인, 구조, 의미 분석 |
| `design` | 시스템, 기능, 아키텍처 설계 |
| `coding` | 코드 작성, 수정, 디버깅 |
| `compare` | 대안 비교 |
| `predict` | 가능성, 방향성, 영향 예측 |
| `decide` | 선택지 판단 및 권고 |
| `extract` | 핵심 정보 추출 |
| `explain` | 개념 설명 |

Output:

```json
{
  "primary_intent": "design",
  "secondary_intents": ["analyze", "decide"],
  "confidence": 0.82,
  "reasoning_mode": "architecture_design",
  "requires_recent_context": true,
  "requires_memory": true,
  "requires_structured_output": true
}
```

MVP: rule-based keyword classifier. confidence가 낮으면 generic mode 사용.

### 6.3 Conversation State Builder

현재 세션의 압축 상태를 구성한다. 전체 대화 기록이 아니라 현재 reasoning에 필요한 working memory이다.

```json
{
  "active_project": "UCE",
  "current_focus": "architecture document design",
  "user_goal": "Local LLM 앞에 UCE를 붙여 문맥 이음 개선",
  "important_constraints": [
    "UCE는 stateless middleware",
    "UCE는 memory를 직접 소유하지 않음",
    "provider-agnostic 설계 유지"
  ],
  "open_questions": [],
  "decisions": [
    "Python + FastAPI로 구현",
    "EXAONE 3.5 7.8b가 1차 타겟"
  ],
  "reasoning_mode": "technical_design"
}
```

UCE는 state를 저장하지 않는다. 생성된 state는 response로 반환되며, 저장 여부는 application이 결정한다.

### 6.4 Recent Context Retriever

현재 질문과 관련 있는 최근 대화 조각을 선택한다.

Retriever 앞에는 Topic Shift Detector가 위치한다. 현재 질문이 이전 흐름을 이어가는지 먼저 판단하고, 그 결과에 따라 recent messages와 previous state를 얼마나 사용할지 결정한다.

Topic relation:
- `continue_topic`: 이전 state와 recent context 적극 사용
- `related_topic`: 이전 state는 유지하되 retriever 결과 중심으로 사용
- `ambiguous`: 최근 일부 context와 stripped state만 사용
- `new_topic`: recent context를 사용하지 않고 active project/focus/goal만 제거한 state 사용

Threshold는 고정 정책이 아니라 `BuildContextOptions`에서 조정 가능하다.

현재 retrieval:
- 최근 N개 메시지
- keyword/token overlap scoring
- topic policy 기반 recent context 사용량 조절
- previous conversation state 참조
- document section-level retrieval

UCE는 embedding-first retrieval을 사용하지 않는다. Vector DB는 필수 dependency가 아니며, Phase 2는 deterministic heuristic scoring으로 동작한다.

### 6.5 Context Ranker

후보 context를 heading relevance, semantic continuity, intent alignment, recency, constraint relevance 기준으로 정렬한다.

```text
final_score =
  0.35 * heading_score
+ 0.20 * section_coherence_score
+ 0.18 * semantic_score
+ 0.12 * intent_alignment_score
+ 0.08 * recency_score
+ 0.07 * constraint_score
```

여기에 `decision_score`, `section_priority_score`, exact heading match, mismatch penalty를 작은 boost/penalty로 더한다.

Ranker는 선택/탈락 이유를 `survived_items`, `dropped_items`, `score_breakdown`으로 노출한다.

### 6.6 Semantic Compressor

선택된 context를 LLM이 읽기 쉬운 compressed block으로 변환한다.

나쁜 압축:
```text
사용자는 UCE에 대해 설명했다.
```

좋은 압축:
```text
User is building UCE, a stateless provider-agnostic middleware that assembles compact Context Packs before LLM calls. Target: EXAONE 3.5 7.8b via Ollama. UCE must not own memory, must not become RAG, and should improve Korean conversation continuity for local LLMs.
```

압축 레벨:

| Level | 사용 시점 | 동작 |
|-------|-----------|------|
| `light` | 충분한 context window | 중복 제거 중심 |
| `medium` | 일반 MVP 기본값 | 핵심 사실, 제약, 결정 중심 |
| `aggressive` | Local LLM, 작은 context window | 최소 정보만 유지 |

코드 파일은 aggressive outline compression 대상이 아니다. 코드 입력은 function/class/module header 단위로 분리하고, 선택된 code section은 계산 흐름과 indentation을 보존하는 방향으로 compact한다.

### 6.7 Prompt Synthesizer

최종 Prompt Pack을 생성한다. provider-neutral structured text가 기본 출력이다.

```text
[System Role]
You are an assistant operating with a structured context pack.

[Current Goal]
{current_goal}

[Intent]
Primary intent: {primary_intent}
Reasoning mode: {reasoning_mode}

[Conversation State]
{conversation_state}

[Relevant Context]
{compressed_context}

[Important Constraints]
{constraints}

[Output Requirements]
{output_requirements}

[Current User Question]
{current_message}
```

한국어 타겟 시: 섹션 헤더는 영어, 내용은 한국어로 유지하는 것이 EXAONE 계열에서 안정적이다.

### 6.8 Response Analyzer

LLM 응답에서 후속 context 관리에 필요한 정보를 추출한다.

UCE interprets state. Application owns state. Response Analyzer는 다음을 제안만 하고, 최종 결정은 application이 한다.

- mutation candidate
- conflict candidate
- deprecation suggestion

```json
{
  "decisions": ["결정된 내용"],
  "memory_candidates": [
    {
      "type": "project_constraint",
      "content": "...",
      "importance": 0.86
    }
  ],
  "unresolved_issues": ["미결 사항"],
  "next_state_patch": {
    "current_focus": "MVP implementation"
  }
}
```

memory에 직접 write하지 않는다. 저장 후보만 반환한다.

---

## 7. API 설계

### 7.1 POST /build-context

Request:

```json
{
  "session_id": "session_123",
  "current_message": {
    "role": "user",
    "content": "UCE 설계 문서를 작성해줘.",
    "created_at": "2026-05-20T10:00:00+09:00"
  },
  "recent_messages": [...],
  "previous_state": {
    "active_project": "UCE",
    "current_focus": "architecture design"
  },
  "optional_memories": [...],
  "documents": [
    {
      "id": "doc_1",
      "title": "UCE Architecture",
      "content": "...",
      "content_type": "markdown",
      "source": "docs/architecture.md"
    }
  ],
  "options": {
    "max_prompt_tokens": 6000,
    "target_model": "ollama:exaone3.5:7.8b",
    "compression_level": "medium",
    "structure_chunking_enabled": true,
    "chunk_max_chars": 1400,
    "include_trace": true
  }
}
```

`current_message`는 optional이다. 없거나 `content`가 빈 문자열이면 UCE는 queryless document compression mode로 동작한다.

```text
current_message 있음:
  기존 conversational pipeline

current_message 없음:
  summarize intent
  fresh_context policy
  recent retrieval 생략
  document sections를 중요도 순으로 압축
```

Response:

```json
{
  "session_id": "session_123",
  "conversation_state": {...},
  "compressed_context": {
    "summary": "...",
    "facts": [],
    "constraints": [],
    "decisions": []
  },
  "prompt_pack": {
    "format": "structured_text",
    "content": "[Current Goal]\n...",
    "estimated_tokens": 3200,
    "original_tokens": 9800
  },
  "metadata": {
    "trace_id": "trace_abc",
    "primary_intent": "design",
    "selected_context_count": 8,
    "dropped_context_count": 14,
    "compression_ratio": 0.33,
    "prompt_build_latency_ms": 42,
    "survived_items": ["constraint:UCE는 stateless", "decision:FastAPI 사용"],
    "dropped_items": ["msg_3", "msg_7"],
    "survival_reasons": {
      "constraint:UCE는 stateless": "Priority 0 constraint",
      "msg_3": "low relevance score (0.12)"
    }
  }
}
```

### 7.2 POST /analyze-response

Request:

```json
{
  "session_id": "session_123",
  "current_message": {"role": "user", "content": "..."},
  "assistant_response": {"role": "assistant", "content": "..."},
  "conversation_state": {...},
  "options": {
    "extract_memory_candidates": true,
    "extract_open_questions": true
  }
}
```

Response:

```json
{
  "next_state_patch": {
    "current_focus": "MVP implementation planning"
  },
  "memory_candidates": [],
  "unresolved_issues": [],
  "metadata": {
    "semantic_importance": 0.78
  }
}
```

### 7.3 GET /health

```json
{
  "status": "ok",
  "version": "0.1.0",
  "components": {
    "intent_analyzer": "ok",
    "retriever": "ok",
    "compressor": "ok",
    "prompt_synthesizer": "ok"
  }
}
```

### 7.4 GET /status

```json
{
  "compression_level": "medium",
  "intent_mode": "rule_based",
  "target_model_note": "EXAONE 3.5 7.8b is the first target profile, not a model limit.",
  "active_provider_profiles": ["generic", "ollama_exaone_7b", "ollama_qwen", "ollama_gemma", "cloud_large"],
  "uptime_seconds": 3842
}
```

---

## 8. 데이터 흐름

### 8.1 Build Context Flow

```text
1. Application이 current_message, recent_messages, optional_memories 전송
2. UCE가 request schema 검증
3. Intent Analyzer가 user intent 분류
4. Recent Context Retriever가 candidate messages 선택
5. External Memory Adapter가 optional memories 정규화
6. Context Ranker가 candidate context 점수화 및 정렬
7. Conversation State Builder가 current state 구성
8. Semantic Compressor가 relevant context 압축
9. Prompt Synthesizer가 최종 Prompt Pack 생성
10. UCE가 prompt_pack, state, compressed_context, metadata 반환
11. Application이 선택한 LLM provider 호출
```

### 8.2 Response Analysis Flow

```text
1. Application이 LLM response 수신
2. Application이 UCE /analyze-response로 response 전송
3. Response Analyzer가 decisions, new topics, unresolved issues 추출
4. UCE가 next_state_patch와 memory_candidates 생성 및 반환
5. Application이 state 또는 memory 저장 여부 결정
```

---

## 9. 메모리 아키텍처

UCE는 메모리를 소유하지 않는다.

```text
Application이 session state 소유
Application이 state를 UCE로 전송
UCE가 updated state 계산
UCE가 state patch 반환
Application이 저장 또는 폐기
```

Memory candidate 모델:

```json
{
  "type": "user_preference | project_constraint | decision | fact | unresolved_issue",
  "content": "...",
  "importance": 0.0,
  "stability": "session | long_term",
  "source": "assistant_response",
  "confidence": 0.0
}
```

---

## 10. 한국어 타겟 전략

UCE의 1차 타겟 언어는 한국어이며, 1차 모델은 EXAONE 3.5 7.8b (Ollama)이다.

### 10.1 Prompt 언어 전략

EXAONE 계열 모델은 영어 instruction + 한국어 content 조합이 안정적이다.

```text
[Current Goal]          ← 영어 헤더
사용자가 UCE 설계 문서를 작성하려 한다.  ← 한국어 내용

[Important Constraints] ← 영어 헤더
- UCE는 stateless middleware이다.    ← 한국어 내용
```

### 10.2 한국어 압축 고려사항

한국어는 조사, 존댓말/반말, 반복 표현으로 인해 동일 의미가 더 많은 토큰을 소비할 수 있다. 압축 시 다음을 우선 제거한다.

- 반복되는 배경 설명
- 동일 내용의 존댓말/반말 혼용
- 불필요한 연결어 및 부연 설명

### 10.3 EXAONE 3.5 7.8b 프로파일

```json
{
  "profile": "ollama_exaone_7b",
  "max_prompt_tokens": 4000,
  "compression_level": "medium",
  "max_recent_messages": 15,
  "prefer_bulleted_context": true,
  "prompt_language": "mixed_ko_en",
  "include_trace": true
}
```

---

## 11. Token Budget 전략

```text
max_prompt_tokens = 4000 (EXAONE 7.8b 기준)

Current user question      10%   400 tokens
Conversation state         15%   600 tokens
Relevant context           35%  1400 tokens
Constraints/decisions      15%   600 tokens
Output requirements        10%   400 tokens
Safety margin              15%   600 tokens
```

주요 메트릭:

| Metric | Description |
|--------|-------------|
| `input_token_reduction_ratio` | 원본 대비 prompt token 감소율 |
| `compression_ratio` | compressed/original token 비율 |
| `selected_context_count` | 선택된 context 개수 |
| `dropped_context_count` | 제외된 context 개수 |
| `intent_confidence` | intent 분류 신뢰도 |
| `prompt_build_latency_ms` | Context Pack 생성 latency |

---

## 12. Phase 계획

### Phase 1: Context Pack MVP (✅ 완료)

포함:
- `POST /build-context`
- `POST /analyze-response`
- `GET /health`, `GET /status`
- rule-based Intent Analyzer
- Topic Shift Detector
- recent N messages retrieval + keyword overlap scoring
- Conversation State Builder
- heuristic Semantic Compressor
- structured Prompt Synthesizer
- EXAONE 3.5 7.8b provider profile
- 한국어 prompt 전략

제외:
- Vector DB
- graph memory
- agent workflow
- tool execution
- long-term memory 소유

### Phase 2: Practical Context Engineering (✅ 완료)

핵심 목표: **다양한 입력 타입을 실전 환경에서 안정적으로 처리하고, UCE를 외부 프로젝트에 내장 가능한 수준으로 완성한다.**

완료:
- Content-Type Aware Processing (markdown / code / docx / xlsx / text)
- Structure-Preserving Chunking (heading / function / table 단위)
- document_loader — python-docx / openpyxl 기반 문서 추출
- current_message optional — query 없이 전체 중요도 순 압축 모드
- Explainable Retrieval debug (score breakdown / survived / dropped)
- Adaptive Compression (intent별 보존 항목 분기)
- Context Importance Scoring (multi-factor)
- xlsx 전체 전달 모드 (Phase 2 한계 인정, Phase 3에서 해결)
- Scenario fixtures 및 EXAONE comparison runner
- reasondock optional middleware 통합
- fallback 및 prompt/debug metrics 검증

### Phase 2.5: Semantic Preservation (🔄 진행 중)

핵심 목표: **정의형/설명형 질문에서 발생하는 hallucination을 줄이고, 소형 로컬 LLM이 의미를 안정적으로 이해할 수 있는 semantic block을 유지한다.**

배경:
- 압축률 극대화 중심 설계가 소형 모델에서 acronym hallucination, 잘못된 정의 생성 유발
- `compressor._compact()` medium 레벨(180자/섹션 520자)이 semantic unit 파괴
- 정의형 질문에서 recent_message가 document보다 높은 score로 노이즈 우선 선택
- `_document_min_score()` 공격적 필터링이 deployment/runtime 관련 청크 drop

구현 대상:
- `compression_level = "semantic"` 추가 — 섹션 1500자, heading+설명+예시 전체 유지
- `explain/what` intent 시 orchestrator에서 semantic mode 자동 분기
- 정의형 질문에서 document role_score 상향 (0.65 → 0.85), recent_message 하향 (0.8 → 0.4)
- `_document_min_score()` 임계값 완화 (0.65 → 0.50)
- adaptive fallback: retrieval confidence < 0.35이면 min_score 제거
- `taxonomy.py` 신규 — query_type 분류 + section taxonomy + boosting
- `prompt_synthesizer.py` — query_type별 grounding 지시 (hallucination suppression)

상세 설계: `docs/semantic-preservation.md` 참조

다음 단계:
- NewSpeed 내장 통합
- scenario 결과 리포트 포맷 정리
- SpreadsheetAdapter 설계 구체화

#### xlsx 처리 방침 (Phase 2)

Phase 2에서 xlsx/csv는 전체 시트를 context로 전달하는 방식을 사용한다.

```text
xlsx 파일 입력
    ↓
document_loader → sheet별 markdown 테이블 변환
    ↓
structure_splitter → sheet 단위 섹션 분할
    ↓
전체 내용 → UCE context → LLM 전달
    ↓
LLM이 집계 / 필터 / 카운트 직접 수행
```

**한계**: 행 수가 많을 경우 token limit 초과 가능. LLM 수치 연산 정확도 보장 불가.
이 한계는 Phase 3의 SpreadsheetAdapter로 해결한다.

아직 포함하지 않는 것:
- SpreadsheetAdapter (deterministic query execution)
- SAU extraction / lifecycle
- semantic survival runtime
- policy-aware retrieval
- semantic mutation engine
- autonomous memory graph

### Phase 3: Type-Aware Preprocessing Runtime (비전)

"Practical Context Engineering"에서 "Type-Aware Preprocessing Runtime"으로 확장하는 단계이다.

포함 예정:
- SpreadsheetAdapter (자연어 → QueryPlan → pandas → facts)
- LogAdapter (timestamp / trace / error chain)
- CodeAdapter 고도화 (AST-lite symbol indexing)
- SAU extraction / semantic classification
- lifecycle state management
- semantic survival / policy-aware retrieval
- narrative state tracking
- relation-aware memory selection

Phase 3의 개념 설계는 섹션 18(SpreadsheetAdapter)과 섹션 19(Future Architecture Vision)에 별도로 기술한다.

---

## 13. 기술 스택

```text
Python 3.11+
FastAPI
Pydantic v2
uvicorn[standard]
python-docx
openpyxl
```

검증은 pytest 중심이 아니라 scenario runner 중심으로 수행한다.

```text
scripts/compare-ollama.py  → raw prompt vs UCE prompt 비교
scripts/try-uce.py         → 임의 사용자 입력에 대한 normal/UCE 출력 비교
examples/eval/*.json       → 고정 stress scenario fixture
```

---

## 14. 모듈 구조

```text
uce/
  app/
    main.py
    api/
      routes.py
      schemas.py
    core/
      orchestrator.py
      intent.py
      state_builder.py
      topic.py
      retriever.py
      ranker.py
      compressor.py
      prompt_synthesizer.py
      response_analyzer.py
      structure_splitter.py
    adapters/
      document_loader.py
      token_counter.py
      provider_profiles.py
      __init__.py
  scripts/
    compare-ollama.py
    try-uce.py
    smoke-api.sh
  examples/
    eval/
      scenario-01-ghost-constraint.json
      scenario-02-reasoning-drift.json
      scenario-03-context-junk.json
      scenario-04-phase2-heading-retrieval.json
  docs/
    architecture.md
    getting-started.md
    api-reference.md
    implementation-guide.md
    roadmap.md
    phase2-validation.md
```

---

## 15. 위험 요소 및 대응

| Risk | Description | Mitigation |
|------|-------------|------------|
| Over-compression | 중요한 정보가 압축 중 소실 | constraints/decisions/open questions를 별도 field로 보존 |
| Wrong intent | 잘못된 intent로 prompt 구성 | confidence 낮을 때 generic mode fallback |
| Context drift | state가 실제 대화와 달라짐 | previous_state와 recent messages 함께 검증 |
| Hidden coupling | 특정 provider나 DB에 묶임 | adapter boundary 유지 |
| Prompt bloat | 구조화 prompt 자체가 길어짐 | template budget 및 metadata 분리 |
| Scope creep | RAG/Agent/Memory platform으로 확장 | component boundary와 excluded scope 문서화 |
| 한국어 토큰 비효율 | 한국어 특성으로 token 낭비 | 한국어 특화 압축 규칙 및 반복 표현 제거 |

---

## 16. MVP 성공 기준

- 기존 chat flow에 UCE를 add-on으로 붙일 수 있다
- `/build-context` 응답만으로 LLM 호출 prompt를 만들 수 있다
- 최근 대화가 길어져도 핵심 목표와 제약이 prompt에 유지된다
- EXAONE 3.5 7.8b에서 반복 설명 필요성이 줄어든다
- token 사용량이 원본 최근 대화 대비 의미 있게 감소한다
- application은 UCE 없이도 계속 동작할 수 있다
- UCE는 memory DB를 강제하지 않는다
- 한국어 대화에서 문맥이 자연스럽게 이어진다

현재까지의 validation 기준에서 Phase 1/2 성공 기준은 충족했다. reasondock 통합에서는 UCE 사용 시 prompt token이 911에서 377로 줄고, first token latency와 total latency가 감소하는 practical validation 결과가 확인되었다. 이 수치는 benchmark가 아니라 실제 통합 smoke result로 취급한다.

---

## 17. Practical Chunking Strategy (Phase 2)

Phase 2의 목표는 SAU 없이도 다음을 달성하는 현실적인 전략이다.

```text
- token reduction
- context preservation
- local LLM attention quality 향상
- reasoning drift 감소
```

모든 구현은 rule-based, heuristic-based, deterministic, explainable하게 동작한다. LLM 호출 없이 완전히 동작 가능해야 한다.

### 17.1 UCE Core Input Boundary

UCE core는 text normalization 이후의 content를 처리한다. HTTP API는 파일 upload API가 아니며, application은 문서 내용을 text로 읽어서 `documents[].content`에 전달한다.

```text
UCE Core가 처리하는 입력:
- normalized text
- markdown
- code
- chat history
- structured text (json/yaml)
- plain log

Adapter가 담당하는 입력 변환:
- docx parsing
- xlsx extraction
- pdf OCR
- attachment loading
- binary format 변환
```

UCE repo는 개발 편의를 위해 `app/adapters/document_loader.py`의 `load_docx`, `load_xlsx`를 제공한다. 이 adapter는 docx/xlsx를 markdown으로 변환한 뒤 기존 pipeline에 넘긴다. PDF/OCR 및 대용량 binary attachment 처리는 아직 application responsibility이다.

### 17.2 Practical Retrieval Pipeline

```text
Raw Document
  → Structural Parsing
  → Section-level Retrieval
  → In-section Compression
  → Prompt Pack Assembly
```

Phase 2의 retrieval 원칙은 **retrieve large, compress small**이다. Retrieval은 semantic continuity를 보존하기 위해 H1/H2 중심의 큰 section을 먼저 선택하고, token reduction은 선택된 section 내부 compression 단계에서 수행한다.

### 17.3 Structure-Aware Splitting

구조가 명시된 텍스트는 구조 경계를 semantic boundary로 우선 활용한다.

```text
변환 우선순위:
- markdown heading (#, ##, ###)
- section boundary
- bullet structure
- code fence (``` 시작/종료)
- table boundary (| --- |)
- log timestamp 변화
- section separator (---, ===)
```

참고 아키텍처 예시 (LangChain 패턴 기반, UCE core의 실제 dependency는 아님):

```text
MarkdownHeaderTextSplitter
  → heading 단위 1차 분할

RecursiveCharacterTextSplitter
  → 각 섹션 내부에서 추가 분할
```

UCE core는 LangChain dependency를 강제하지 않는다. 동일한 로직을 자체 구현하거나, adapter 계층에서 라이브러리를 선택적으로 연동할 수 있다.

1차 retrieval 단위는 paragraph나 recursive chunk가 아니라 다음 semantic block이다.

```text
- H1/H2 section with children
- logical section
- code block group
- table group
- traceback group
```

### 17.4 Recursive Chunk Splitting

구조 정보가 없는 경우 또는 세분 분할이 필요한 경우, 다음 우선순위로 점진적 fallback한다.

```text
\n\n  →  \n  →  sentence  →  whitespace  →  character
```

목표는 가능한 semantic continuity를 유지하면서 context window 초과 시 점진적으로 분할하는 것이다. 문단 단위에서 먼저 시도하고, 그래도 초과하면 문장, 단어 순서로 마저 분할한다.

### 17.5 Metadata Enrichment

단순 metadata field 저장이 아니라, section content 내부에 context 정보를 짧게 prepend하는 전략을 사용한다.

```text
[Section]
UCE Architecture Document > 12. Phase 계획

[Content]
...
```

이유: 작은 local LLM은 별도 metadata field보다 본문 내 명시적 context를 더 잘 활용할 수 있다. prompt 안에 구조적 맥락이 있으면 attention이 응집된다.

### 17.6 Special Content Preservation

다음 항목은 atomic block으로 유지한다. 내부 split을 최소화하거나 금지한다.

```text
- traceback / stacktrace  → 중간 split 금지. 전체를 하나의 block으로 유지
- code block             → code fence 내부 split 최소화
- yaml / json            → 구조 단위로 유지
- table                  → header를 매 chunk에 반복 유지
```

traceback은 중간에서 잘리면 원인 파악이 불가능해진다. LLM에게 완전한 traceback을 주는 것이 토큰을 잘라 주는 것보다 더 유용하다.

### 17.7 Context Importance Scoring (Phase 2 고도화)

현재 단순 keyword overlap + recency 기반 scoring을 section-level multi-factor로 고도화한다.

```json
{
  "semantic_score": 0.82,
  "heading_score": 0.91,
  "section_path_score": 0.91,
  "section_priority_score": 1.0,
  "section_coherence_score": 0.95,
  "recency_score": 0.61,
  "intent_alignment_score": 0.75,
  "constraint_score": 0.95,
  "decision_score": 0.88,
  "final_score": 0.84
}
```

| Factor | 설명 |
|--------|------|
| `semantic_score` | 현재 질문과 keyword overlap |
| `heading_score` | section title / heading path와 현재 질문의 overlap |
| `section_path_score` | heading path 기반 relevance debug signal |
| `section_priority_score` | Overview, Summary, Goals, Phase 계획, Architecture, Constraints 등 overview 섹션 우선순위 |
| `section_coherence_score` | 작은 fragment보다 semantic continuity가 유지되는 큰 section 선호 |
| `recency_score` | 최근 대화에서는 최신성, 문서 chunk에서는 neutral score |
| `intent_alignment_score` | 현재 intent와 일치 여부 |
| `constraint_score` | constraint 포함 여부 |
| `decision_score` | decision 포함 여부 |

추정 가중치 공식:

```text
final_score =
  0.35 * heading_score
+ 0.20 * section_coherence_score
+ 0.18 * semantic_score
+ 0.12 * intent_alignment_score
+ 0.08 * recency_score
+ 0.07 * constraint_score
```

여기에 `decision_score`, `section_priority_score`, exact overview heading match를 작은 boost로 더한다. high-confidence document section match가 있으면 low relevance section은 prompt에 들어가지 않도록 threshold를 적용한다. Phase 2에서는 모든 값을 ML score로 만들 필요는 없다. keyword score + heading heuristic + application-provided importance 조합으로 근사한다.

### 17.8 Adaptive Compression (Phase 2)

Phase 2에서 intent별로 압축 전략을 분기한다. constraints와 decisions는 모든 mode에서 항상 보존된다.

| Intent | 보존 대상 |
|--------|---------|
| `coding` | 에러 메시지, 파일 경로, expected behavior, 구현 제약 |
| `design` | constraints, tradeoffs, architectural goals, decisions |
| `summarize` | 시간 순, 결정사항, unresolved questions |
| `analyze` | evidence, causal chain, ambiguity |
| `compare` | alternatives, criteria, pros/cons |
| `continue_discussion` | previous state, last topic, open questions |

---

## 18. SpreadsheetAdapter 상세 설계 (Phase 3)

> 이 섹션은 Phase 3 구현 대상이다. Phase 2에서는 xlsx 전체 전달 방식을 사용한다.

### 18.1 설계 배경

xlsx/csv는 semantic document가 아니라 임시 데이터베이스에 가깝다.
사용자 질문의 대부분은 count / filter / aggregation / grouping이며,
raw 행을 LLM에게 통째로 넘기는 것은 비효율적이고 정확도도 낮다.

```text
잘못된 방식 (Phase 2 한계):
  xlsx 전체 행 → LLM → "고장대응은 47건입니다" (불확실)

올바른 방식 (Phase 3):
  xlsx → pandas count(고장대응) = 47 → facts["고장대응: 47건"] → LLM → 설명만
```

### 18.2 처리 흐름

```text
자연어 질문
    ↓
RuleBasedPlanner  — intent 분류 + 컬럼 매핑 (confidence >= 0.7)
    ↓ confidence < 0.7이면
LLM Planner  — QueryPlan JSON만 생성 (코드 실행 안 함)
    ↓
DataFrameExecutor  — deterministic pandas 실행
    ↓
facts[] 주입  — LLM은 설명만 담당
```

LLM은 절대 pandas 코드를 직접 생성하거나 실행하지 않는다.
QueryPlan이라는 구조화된 중간 표현만 생성하고,
실제 실행은 DataFrameExecutor가 허용된 연산자 집합으로만 수행한다.

### 18.3 Query Intent 분류

| Intent | 키워드 예시 |
|--------|------------|
| COUNT | "몇 건", "몇 개", "how many" |
| FILTER | "~인 것만", "~에서", "show only" |
| AGGREGATE | "합계", "평균", "최대/최소" |
| GROUP | "~별로", "~기준으로" |
| SORT | "많은 순", "최신순", "top N" |
| TIMESERIES | "월별", "주별", "추이" |
| MIXED | 위 조합 |

### 18.4 Schema Profiling

파일 로딩 시 1회 수행, 결과를 캐시한다.

| 항목 | 내용 |
|------|------|
| 컬럼명 | 원본 그대로 보존 |
| dtype 추론 | str / int / float / datetime |
| null_ratio | 결측치 비율 |
| is_categorical | unique_count < 30 and unique_count/total < 0.1 |
| categorical_values | is_categorical이면 전체 고유값 목록 |
| sample_values | 상위 10개 샘플값 |

### 18.5 컬럼 매핑 전략

"고장대응"이 어느 컬럼의 값인지 추론하는 4단계:

```text
1단계: 컬럼명 직접 매칭
2단계: categorical 컬럼의 categorical_values에서 검색  ← 주요 경로
3단계: 부분 문자열 매칭 (confidence 하락)
4단계: LLM fallback — schema_profile + query → column/value 추론만
```

### 18.6 QueryPlan Schema

```json
{
  "intent": "COUNT | FILTER | AGGREGATE | GROUP | SORT | TIMESERIES | MIXED",
  "target_sheet": "Sheet1",
  "filters": [
    {"column": "운영업무 세부구분", "operator": "eq", "value": "고장대응"}
  ],
  "group_by": [],
  "aggregate": {"*": "count"},
  "sort_by": [],
  "limit": null,
  "time_column": null,
  "time_granularity": null,
  "confidence": 0.95,
  "planner": "rule_based"
}
```

### 18.7 Query Complexity 허용 범위

| 허용 | 비허용 |
|------|--------|
| filter + count / aggregate | JOIN across sheets (complex) |
| GROUP BY + aggregate | 중첩 subquery |
| multi-filter (AND 조건) | 통계 모델링 (regression 등) |
| TIMESERIES 월별/주별 집계 | LLM이 pandas 코드 직접 생성 |
| TOP N + sort | eval() 실행 |

complexity 초과 시 facts에 "처리 범위 초과" 메시지를 넣고 종료한다.

### 18.8 Orchestrator 분기

```text
content_type == "xlsx" or "csv"
    → SpreadsheetAdapter 경로
    → structure_splitter / retriever / compressor 생략
    → facts[] 직접 주입

content_type == 그 외
    → 기존 semantic retrieval 경로
```

### 18.9 Adapter Interface

```python
class SpreadsheetAdapter:
    def load(self, path: Path) -> None
    def profile(self) -> dict[str, list[ColumnProfile]]
    def plan(self, query: str) -> QueryPlan
    def execute(self, plan: QueryPlan) -> QueryResult
    def to_facts(self, result: QueryResult) -> list[str]
```

---

## 19. Future Architecture Vision (Phase 3)

> 이 섹션은 현재 구현 범위가 아니다. Phase 3 이후의 장기 방향성을 기술한다.

UCE는 "contextual chunking + heuristic scoring"에서 시작하여, 장기적으로 "Semantic Reasoning Runtime"으로 진화하는 방향을 대상으로 한다.

### 19.1 Semantic Atomic Unit (SAU)

Phase 3에서 retrieval 단위는 token chunk가 아니라 **Semantic Atomic Unit(SAU)**으로 재정의된다.

SAU는 독립적으로 reasoning 의미를 유지할 수 있는 최소 semantic block이다.

```text
SAU 조건:
- 단독으로 읽었을 때 하나의 완결된 의미를 가진다
- 다른 SAU와 독립적으로 reasoning context에 기여할 수 있다
- 잘라낼 수 없는 semantic boundary를 가진다
```

SAU는 다음 runtime flow를 거쳐 동적으로 생성된다.

```text
raw sentences
  → initial segmentation
  → heuristic merge
  → semantic boundary validation
  → SAU generation
```

### 19.2 Semantic Classification

추출된 SAU는 reasoning에서의 역할에 따라 분류된다.

| Class | 설명 |
|-------|------|
| `constraint` | 위반 불가한 설계/요구 제약 |
| `decision` | 내려진 결정 사항 |
| `fact` | 객관적 사실, 수치, 상태 |
| `reasoning` | 추론 과정, 판단 근거 |
| `implementation_note` | 구현 세부사항 |
| `error_cause` | 오류 원인 및 맥락 |
| `example` | 예시, 샘플 코드 |
| `deprecated` | 번복된 결정, 무효화된 정보 |
| `noise` | reasoning에 기여하지 않는 단위 |

### 19.3 SAU Lifecycle

각 SAU는 lifecycle state를 가진다. 저장은 application이 담당한다.

```text
proposed   → 생성 직후
active     → 현재 유효
deprecated → 번복 또는 무효화
replaced   → 다른 SAU로 대체
conflicted → active decision과 충돌
archived   → 이력 보존 목적으로 유지
```

```json
{
  "sau_id": "decision_104",
  "type": "decision",
  "state": "deprecated",
  "replaced_by": "decision_141",
  "deprecated_reason": "Redis 제거 결정",
  "created_at": "2026-05-20T09:00:00+09:00",
  "updated_at": "2026-05-20T11:30:00+09:00"
}
```

### 19.4 Semantic Survival

```text
무엇을 검색할 것인가보다
무엇을 살아남게 할 것인가를 우선한다.
```

```text
Priority 0 (항상 생존): constraint, active_goal, pinned_decision
Priority 1 (token 허용 시 생존): decision, unresolved_question
Priority 2 (score 기반 경쟁): fact, reasoning, implementation_note
Priority 3 (공간 남을 때): example
제외 대상: deprecated, replaced, conflicted, noise
```

### 19.5 Policy-Aware Retrieval

Phase 3에서 retrieval은 semantic similarity만으로 동작하지 않는다. reasoning safety를 semantic relevance보다 우선할 수 있다.

```text
우선 기준:
- reasoning continuity: 현재 대화 흐름과 일관성 있는 context
- architectural consistency: 설계 원칙에 반하는 방향 차단
- constraint preservation: active constraint 위반 방향의 context 제외
- decision stability: 번복된 결정이 재등장하지 않도록 필터링

필터링 기준:
- lifecycle state가 deprecated / replaced / conflicted인 SAU → 제외
- 현재 active decision과 충돌하는 SAU → score 감점 또는 제외
- 현재 constraints를 위반하는 방향의 reasoning SAU → 제외
- topic_relation이 new_topic일 때 project-specific SAU → 제외
```

### 19.6 Reasoning Runtime 철학

RAG는 증거를 검색한다. UCE는 reasoning state를 유지한다.

```text
RAG retrieves evidence.
UCE maintains reasoning state.
```

UCE가 제어하는 것은 "LLM이 무엇을 기억해야 하는가"가 아니다.

UCE가 제어하는 것은 **"LLM이 무엇을 foreground attention에 유지해야 하는가"**이다.

token chunking 기반 RAG가 "관련 있는 것을 찾는" 시스템이라면, UCE는 "지금 reasoning에 살아있어야 하는 것을 유지하는" 시스템이다.

### 19.7 현실적 구현 우선순위

지금 가장 중요한 목표:

```text
- token reduction
- context continuity
- local LLM stability
- reasoning drift reduction
- deterministic behavior
- explainable scoring
- low latency
```

의도적으로 나중으로 미루는 것:

```text
- full semantic runtime
- autonomous memory graph
- fully adaptive retrieval
- semantic mutation engine
- autonomous policy evolution
```
