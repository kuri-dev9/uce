# UCE Semantic Preservation — 설계 문서

> 관련 이슈: 정의형 질문에서 할루시네이션 반복 발생
> 작성일: 2026-05-21
> 상태: Codex 구현 대상

---

## 배경 및 문제 정의

UCE는 압축률(token reduction) 중심으로 설계되어 있으나,
소형 로컬 LLM(EXAONE 7.8b, Gemma 등)에서 다음 문제가 반복 발생하고 있다.

### 실패 패턴

| 질문 유형 | 증상 |
|-----------|------|
| "UCE가 뭐야?" | acronym 임의 해석, 잘못된 정의 생성 |
| "RCA란?" | 관련 없는 의미로 hallucination |
| "이 시스템의 역할은?" | operational text만 남고 identity 손실 |
| "UCE는 어디서 실행돼?" | 클라우드 서버라고 임의 추정 |

### 근본 원인

```
compressor._compact()
  → medium 레벨: 일반 텍스트 180자, 섹션 520자로 절단
  → "UCE는 optional middleware입니다." 한 줄만 남음
  → 역할/흐름/예시/fallback 설명 전부 손실
```

```
retriever.score_text()
  → role_score: user=0.8, document=0.65
  → 정의형 질문에서 recent_message가 README보다 높은 점수
  → 노이즈 context가 primary evidence로 사용됨
```

```
orchestrator._document_min_score()
  → top_score >= 0.8이면 min_score = 0.65
  → deployment/runtime 관련 청크가 threshold 미달로 drop
  → "UCE 실행 위치" 관련 근거 없이 LLM이 추정
```

```
prompt_synthesizer.PROMPT_TEMPLATE
  → [Output Requirements]가 일반적 지시만 포함
  → 소형 모델은 "모르면 말해" 수준으로 hallucination 억제 불가
```

---

## 핵심 방향 전환

| 항목 | 현재 | 변경 |
|------|------|------|
| 압축 KPI | 압축률 극대화 | semantic preservation 우선 |
| 압축 단위 | sentence/180자 | semantic section 유지 |
| document 우선순위 | recent_message보다 낮음 | 정의형 질문에서 document 우선 |
| grounding 지시 | 일반적 | query_type별 동적 |
| min_score | 공격적 필터링 | low confidence 시 완화 |

---

## 구현 항목 (5개)

### 1. `compression_level = "semantic"` 추가

**파일:** `app/core/compressor.py`

```python
MAX_CONTENT_LENGTH = {
    "light":      320,
    "medium":     180,
    "aggressive": 100,
    "semantic":   600,   # ← 신규: 정의형 질문용
}

SECTION_CONTENT_LENGTH = {
    "light":      900,
    "medium":     520,
    "aggressive": 320,
    "semantic":  1500,   # ← 신규: section 전체 유지
}
```

`explain/what` intent에서 `"semantic"` 레벨 사용 시:
- heading + 설명 + 예시 + 흐름 + fallback 설명까지 함께 전달
- section 절단 없이 semantic unit 전체 유지

---

### 2. `explain/what` intent 시 orchestrator 분기

**파일:** `app/core/orchestrator.py`

```python
# intent가 explain이면 semantic preservation 모드
SEMANTIC_INTENTS = {"explain", "continue_discussion"}

if intent_result.primary_intent in SEMANTIC_INTENTS:
    compression_level = "semantic"
    selected_limit = min(len(document_candidates), 9) if document_candidates else 10
else:
    selected_limit = 6 if document_candidates else 10

# adaptive fallback: confidence 낮으면 min_score 제거
document_min_score = None if not query_mode else _document_min_score(document_candidates)
if document_min_score is not None:
    tentative = [c for c in document_candidates if c.score >= document_min_score]
    if _retrieval_confidence(tentative) < 0.35:
        document_min_score = None  # grounding 보존 우선

# _document_min_score 임계값 완화
def _document_min_score(document_candidates) -> float | None:
    top_score = max(item.score for item in document_candidates)
    if top_score >= 0.8:
        return max(0.50, round(top_score - 0.25, 4))  # 0.65 → 0.50
    if top_score >= 0.7:
        return max(0.40, round(top_score - 0.25, 4))  # 0.55 → 0.40
    return None
```

---

### 3. 정의형 질문에서 document 우선순위 상향

**파일:** `app/core/retriever.py`의 `score_text()`

```python
# 현재
role_score = 0.8 if role == "user" else 0.55 if role == "assistant" else 0.65

# 변경: intent_name 파라미터 추가 후
if intent_name in {"explain", "continue_discussion"} and role == "document":
    role_score = 0.85   # document 우선
elif intent_name in {"explain", "continue_discussion"} and role == "user":
    role_score = 0.40   # recent_message 보조로만
else:
    role_score = 0.8 if role == "user" else 0.55 if role == "assistant" else 0.65
```

`retrieve_context()`, `retrieve_document_chunks()` 모두 `intent_name` 전달 경로 확인 필요.

---

### 4. query_type 분류 + taxonomy boosting

**파일:** `app/core/intent.py` + 신규 `app/core/taxonomy.py`

**`taxonomy.py` 신규 생성:**

```python
QUERY_TYPE_RULES = {
    "where":   ["어디", "어디서", "where", "위치", "실행", "수행", "동작"],
    "how":     ["어떻게", "방법", "how", "절차", "과정"],
    "what":    ["뭐야", "무엇", "what", "정의", "설명", "소개", "역할", "란"],
    "config":  ["설정", "환경변수", "config", ".env", "options"],
    "api":     ["api", "endpoint", "curl", "호출", "요청"],
    "troubleshooting": ["오류", "에러", "error", "문제", "실패"],
}

SECTION_TAXONOMY = {
    "deployment": ["docker", "compose", "container", "배포", "실행", "service", "port"],
    "architecture": ["구조", "아키텍처", "architecture", "설계", "backend", "middleware"],
    "config": ["설정", "환경변수", "config", ".env", "options"],
    "api": ["api", "endpoint", "http", "rest", "curl"],
    "runtime": ["런타임", "runtime", "동작", "프로세스"],
    "overview": ["개요", "overview", "소개", "목표", "introduction", "주요", "기능", "역할"],
    "flow": ["흐름", "flow", "과정", "절차", "단계", "pipeline", "→"],
    "feature": ["기능", "feature", "지원", "특징"],
    "troubleshooting": ["오류", "에러", "error", "문제", "실패", "해결"],
}

QUERY_TAXONOMY_BOOST = {
    "where":  {"deployment": 0.15, "runtime": 0.10, "architecture": 0.08},
    "what":   {"overview": 0.20, "architecture": 0.10, "feature": 0.08},
    "how":    {"flow": 0.12, "architecture": 0.08, "feature": 0.06},
    "config": {"config": 0.20, "deployment": 0.08},
    "api":    {"api": 0.20, "flow": 0.08},
    "troubleshooting": {"troubleshooting": 0.18, "config": 0.08},
}

def classify_query_type(message: str) -> str: ...
def classify_chunk_taxonomy(content: str, header_path: str) -> list[str]: ...
def apply_taxonomy_boost(score: float, taxonomy: list[str], query_type: str) -> float: ...
```

**`intent.py` 수정:**
- `IntentResult`에 `query_type: str = "what"` 추가
- `analyze_intent()`에서 `classify_query_type()` 호출

**`retriever.py` 수정:**
- `ContextItem`에 `taxonomy: list[str]` 추가 (`frozen=True` → field 추가 주의)
- `retrieve_document_chunks()`에서 taxonomy 분류 + boosting 적용

---

### 5. Hallucination suppression — query_type별 grounding 지시

**파일:** `app/core/prompt_synthesizer.py`

```python
GROUNDING_INSTRUCTIONS = {
    "what": (
        "답변은 제공된 컨텍스트에만 근거해야 합니다.\n"
        "약어(acronym)를 임의로 해석하지 마세요.\n"
        "정의가 문서에 없으면 '문서에 명시되지 않음'이라고 답하세요."
    ),
    "where": (
        "실행 위치, 배포 환경, 인프라 정보가 명시되지 않은 경우 "
        "'문서에 명시되지 않음'이라고 답하세요.\n"
        "클라우드, 서버, 인프라를 임의로 추정하지 마세요."
    ),
    "config": (
        "설정값은 컨텍스트에 명시된 것만 안내하세요. "
        "기본값을 추정하지 마세요."
    ),
    "default": (
        "컨텍스트에 없는 사실을 추론하거나 가정하지 마세요.\n"
        "정보가 부족한 경우 '해당 내용은 제공된 문서에 없습니다'라고 답하세요."
    ),
}
```

`synthesize()`에 `query_type: str = "what"` 파라미터 추가.
`PROMPT_TEMPLATE`의 `[Output Requirements]` 섹션을 동적으로 교체.

---

## 변경 금지

- `/build-context` 응답 스키마 (reasondock 호환성)
- `app/adapters/` 내부
- `app/api/schemas.py` 최소 변경 원칙

## 기대 효과

| 케이스 | 현재 | 목표 |
|--------|------|------|
| "UCE가 뭐야?" | acronym hallucination | 문서 정의 기반 정확 답변 |
| "UCE는 어디서 실행돼?" | 클라우드 추정 | Docker Compose 서비스 정답 |
| "RCA란?" | 잘못된 정의 | 문서에 없으면 "명시 안 됨" |
| 압축률 | 18% (과압축) | 30~50% (semantic 유지) |
| 첫 토큰 지연 | 6.5s | 8~12s (허용 범위) |
