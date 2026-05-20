# UCE Implementation Guide
> Version: 0.3  
> Last Updated: 2026-05-20

이 문서는 현재 UCE 구현을 이해하고 확장하기 위한 개발 가이드다. 초기 스캐폴딩 문서가 아니라, Phase 2 완료 상태의 실제 모듈 경계를 기준으로 설명한다.

---

## 1. Runtime Boundary

UCE core는 다음을 하지 않는다.

- LLM 호출
- conversation/message 저장
- memory DB 소유
- vector DB 운영
- agent planning 또는 tool execution

UCE core는 다음만 수행한다.

```text
request
  -> intent/topic/state 분석
  -> context/document 후보 생성
  -> explainable ranking
  -> semantic compression
  -> prompt synthesis
  -> response metadata 반환
```

외부 application은 `prompt_pack.content`를 기존 LLM entrypoint에 전달한다.

---

## 2. Current Module Structure

```text
app/
  main.py
  server.py
  api/
    routes.py
    schemas.py
  core/
    orchestrator.py
    intent.py
    topic.py
    state_builder.py
    retriever.py
    ranker.py
    structure_splitter.py
    compressor.py
    prompt_synthesizer.py
    response_analyzer.py
  adapters/
    document_loader.py
    provider_profiles.py
    token_counter.py
scripts/
  compare-ollama.py
  try-uce.py
  smoke-api.sh
examples/
  build-context.sample.json
  analyze-response.sample.json
  topic-shift.sample.json
  eval/
```

---

## 3. Build Context Flow

`app/core/orchestrator.py`가 전체 흐름을 조율한다.

```text
BuildContextRequest
  -> normalize current_message
  -> detect query_mode
  -> provider profile 선택
  -> intent analysis
  -> topic shift detection
  -> recent message retrieval
  -> document section retrieval
  -> rank_context_items
  -> build_conversation_state
  -> compress_context
  -> synthesize_prompt_pack
  -> BuildContextResponse
```

`current_message`가 없거나 content가 빈 문자열이면 queryless mode다.

```text
query_mode = False
  -> intent = summarize
  -> topic_policy = fresh_context
  -> recent retrieval 생략
  -> document sections를 중요도 순으로 선택
```

기존 conversational mode는 `current_message`가 있을 때 그대로 유지한다.

---

## 4. Schema Notes

핵심 schema는 `app/api/schemas.py`에 있다.

중요한 현재 상태:

- `Message.content` 기본값은 `""`
- `BuildContextRequest.current_message`는 optional
- `DocumentInput.content_type`은 `markdown`, `text`, `code`, `json`, `yaml`, `log`, `docx`, `xlsx`를 허용
- UCE HTTP API는 file upload가 아니라 already-loaded text content를 받는다

---

## 5. Structure Splitter

`app/core/structure_splitter.py`는 document input을 semantic retrieval unit으로 변환한다.

Markdown:

- heading tree 기반 section 생성
- H1/H2 중심 large section retrieval
- H3 이하 child context는 parent section에 포함 가능

Code:

- module header
- top-level `def`
- top-level `async def`
- top-level `class`

핵심 원칙:

```text
retrieve large
compress locally
```

즉 retrieval 단계에서 너무 작은 paragraph chunk를 만들지 않는다. semantic continuity를 먼저 보존하고, token reduction은 compressor가 수행한다.

---

## 6. Retriever and Ranker

`app/core/retriever.py`는 recent messages와 document sections를 `ContextItem` 후보로 만든다.

`app/core/ranker.py`는 후보를 선택하고 metadata를 정리한다.

문서 scoring의 주요 factor:

- `semantic_score`
- `heading_score`
- `section_path_score`
- `section_priority_score`
- `section_coherence_score`
- `recency_score`
- `intent_alignment_score`
- `constraint_score`
- `decision_score`
- `mismatch_penalty`
- `final_score`

현재 가중치 방향:

```text
final_score =
  0.35 * heading_score
+ 0.20 * section_coherence_score
+ 0.18 * semantic_score
+ 0.12 * intent_alignment_score
+ 0.08 * recency_score
+ 0.07 * constraint_score
+ boosts
- penalties
```

선택/탈락 이유는 `metadata.survived_items`, `metadata.dropped_items`, `metadata.survival_reasons`로 노출한다.

---

## 7. Compressor

`app/core/compressor.py`는 selected context만 압축한다.

보존 우선순위:

- constraints
- decisions
- facts
- open questions
- heading/title context
- intent별 핵심 evidence

코드 입력은 aggressive outline extraction을 피한다. 코드의 indentation과 계산 흐름이 사라지면 retrieval은 성공해도 답변 품질이 떨어지기 때문이다.

Markdown section 압축은 다음을 보존한다.

- heading
- heading 직후 핵심 문장
- bullet/numbered list
- markdown table row
- code fence 내부의 짧고 의미 있는 줄
- Phase N 질문일 때 해당 phase block

---

## 8. Prompt Synthesizer

`app/core/prompt_synthesizer.py`는 provider-neutral structured text를 생성한다.

기본 구조:

```text
[System Role]
[Current Goal]
[Intent]
[Conversation State]
[Relevant Context]
[Important Constraints]
[Key Decisions]
[Open Questions]
[Relevant Facts]
[Output Requirements]
[Current User Question]
```

섹션 헤더는 영어, 내용은 한국어를 허용하는 mixed format이다. EXAONE 계열 local LLM에서 안정적인 편이다.

---

## 9. Document Loader Adapters

`app/adapters/document_loader.py`는 CLI 편의를 위한 adapter다.

`load_docx(path)`:

- paragraph를 읽는다
- `Heading 1/2/3` style을 `#`, `##`, `###`로 변환한다
- table row를 markdown table row로 변환한다

`load_xlsx(path)`:

- workbook의 각 sheet를 읽는다
- 빈 sheet는 제외한다
- 각 sheet를 `## {sheet.title}` heading으로 시작한다
- 값이 있는 row를 markdown table row로 변환한다

HTTP API 자체는 파일 path를 받지 않는다. application 또는 CLI가 loader를 사용해 text로 변환한 뒤 `documents[].content`에 넣는다.

---

## 10. Validation Tools

pytest 중심이 아니라 scenario/manual runner 중심으로 검증한다.

```bash
python3 scripts/try-uce.py \
  --context docs/architecture.md \
  --message "UCE의 Phase 2 목표가 뭐야?" \
  --debug-retrieval \
  --show-prompts
```

```bash
python3 scripts/compare-ollama.py examples/eval/scenario-01-ghost-constraint.json
```

Scenario fixtures:

- `scenario-01-ghost-constraint.json`
- `scenario-02-reasoning-drift.json`
- `scenario-03-context-junk.json`
- `scenario-04-phase2-heading-retrieval.json`

---

## 11. Integration Guidance

Host application integration should be additive and optional.

```text
legacy:
  app -> LLM

UCE:
  app -> UCE /build-context -> app -> LLM
```

Required fallback behavior:

```python
try:
    uce_result = await uce_client.build_context(...)
    messages = convert_prompt_pack(uce_result)
except Exception:
    messages = legacy_messages
```

The host application must keep ownership of:

- conversations
- messages
- storage
- user identity
- LLM orchestration
- RAG/vector search, if any

UCE only owns context assembly for the current request.

---

## 12. Safe Extension Points

Good Phase 3 extension points:

- `document_loader.py` for new file formats
- `structure_splitter.py` for new semantic boundaries
- `retriever.py` scoring factors
- `compressor.py` intent/type-specific compression
- `provider_profiles.py` model profile tuning
- scenario fixtures for regression validation

Avoid:

- adding persistent memory ownership to UCE
- adding LLM calls into core middleware
- adding vector DB as mandatory dependency
- turning UCE into an autonomous agent framework

