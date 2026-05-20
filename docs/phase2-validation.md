# UCE Phase 2 Validation Strategy
> Version: 0.1  
> Last Updated: 2026-05-19  
> Scope: Practical validation and lightweight evolution

---

## 1. Phase 2 Objective

UCE Phase 2 is not a large architecture expansion.

The immediate goal is to validate whether UCE-generated `prompt_pack` improves real local LLM responses compared with raw conversation input.

Primary validation target:

- EXAONE 3.5 7.8B via Ollama

Important boundary:

- EXAONE is only the first validation target.
- UCE remains provider-agnostic.
- UCE does not call an LLM internally as part of the core middleware.
- Any LLM comparison runner must live outside the core request path.

Phase 2 should answer one practical question:

```text
Does UCE produce better, more stable LLM responses for real conversations?
```

---

## 2. What To Compare

For the same scenario, compare two inputs to the same LLM.

### A. Raw Prompt

Raw recent conversation and current user question are sent directly to the LLM. Reference documents passed to UCE are intentionally not included in the raw baseline, otherwise the comparison no longer measures UCE retrieval/compression.

```text
Recent conversation:
...

Current user question:
...
```

### B. UCE Prompt Pack

The same conversation is first sent to `/build-context`. Then `prompt_pack.content` is sent to the same LLM.

```text
POST /build-context
  -> prompt_pack.content
  -> Ollama / EXAONE
```

The LLM, temperature, max tokens, and user question must remain identical between A and B.

---

## 3. Evaluation Criteria

This is not benchmark science. The goal is practical improvement validation.

Use a small rubric with human review first.

| Criterion | Question |
| --- | --- |
| Response consistency | Does the answer stay aligned with the actual task? |
| Constraint preservation | Does it preserve important constraints from the conversation? |
| Hallucination reduction | Does it avoid inventing project facts or requirements? |
| Topic continuity | Does it continue the right topic and drop unrelated prior topics? |
| Implementation quality | For coding/design tasks, is the output actionable and concrete? |
| Token efficiency | Does UCE reduce irrelevant context while preserving necessary facts? |
| Long conversation stability | Does quality hold after many previous messages? |

Suggested human scoring:

```text
0 = worse than raw
1 = roughly equal
2 = clearly better
```

Do not overfit the system to one model response. Run each scenario at least 3 times if the model is stochastic.

---

## 4. Validation Scenarios

Start with 6 practical scenarios.

| Scenario | Purpose |
| --- | --- |
| `continue_design` | Previous design context should be preserved |
| `continue_coding` | Implementation constraints and expected behavior should be preserved |
| `topic_shift` | Prior context should be dropped when user switches topic |
| `return_to_topic` | Previously preserved state should allow returning to the project |
| `long_conversation` | Repeated and old context should be compressed |
| `constraint_sensitive` | Important constraints should survive compression |

Each scenario should have:

- `current_message`
- `recent_messages`
- `previous_state`
- `optional_memories`
- expected important constraints
- expected dropped context, if any

### 4.1 Stress Scenario Fixtures

The first validation set uses three intentionally difficult scenarios. These are designed to expose when a local model loses attention, forgets constraints, follows misleading context, or over-focuses on irrelevant noise.

Fixture location:

```text
examples/eval/
  scenario-01-ghost-constraint.json
  scenario-02-reasoning-drift.json
  scenario-03-context-junk.json
  scenario-04-phase2-heading-retrieval.json
```

Each fixture includes:

- `scenario_id`
- `title`
- `purpose`
- `target_failure`
- `expected_uce_behavior`
- `raw_prompt_instruction`
- `uce_request`
- `manual_checks`

The `uce_request` object can be sent directly to `/build-context`.

`scenario-04-phase2-heading-retrieval.json` uses `document_context.path` so the validation runner loads `docs/architecture.md` as a full markdown document before calling UCE.

### 4.2 Scenario 1: Ghost Constraint

Purpose:

- Verify whether early hard constraints survive a long distracting technical conversation.

Key setup:

- The user says the forbidden term `Database` must never be used.
- The assistant must use `Storage` instead.
- Every answer must end with `보안 등급: Level 2`.

Trigger:

```text
자, 이제 우리 시스템의 데이터를 어디에 저장하는 게 효율적일까?
```

Raw prompt likely failure:

- The model uses `Database`.
- The model omits `보안 등급: Level 2`.

UCE expected behavior:

- Keep the hard constraint in `Important Constraints`.
- Surface it near the top of `prompt_pack`.
- Preserve it even after long scoring/decay/prompt-design discussion.

### 4.3 Scenario 2: Reasoning Drift

Purpose:

- Verify whether a prior architectural decision survives misleading later discussion.

Key setup:

- The project decided not to use Vector DB.
- The project uses local JSON-based indexing.
- Later conversation discusses Pinecone and Vector DB benefits as a distraction.

Trigger:

```text
그럼 우리 시스템에 대용량 PDF 1,000권을 넣으면 검색 성능이 어떻게 될까?
```

Raw prompt likely failure:

- The model answers as if the current system uses a Vector DB.
- The model claims Vector DB-like performance despite the project decision.

UCE expected behavior:

- Preserve the JSON-indexing decision.
- Treat Pinecone discussion as reference context, not current architecture.
- Explain performance limits under the actual JSON-based design.

### 4.4 Scenario 3: Context Junk

Purpose:

- Verify whether important early facts survive noisy logs and unrelated code blocks.

Key setup:

- Early in the conversation, the project budget is set to `500만 원`.
- Later messages contain unrelated logs and code with misleading numbers.

Trigger:

```text
우리가 지금 설계하는 기능들이 500만 원이라는 예산 범위 내에서 실현 가능한 수준이야?
```

Raw prompt likely failure:

- The model says budget information is missing.
- The model confuses unrelated numeric noise with the budget.
- The model over-focuses on logs/code.

UCE expected behavior:

- Preserve the `500만 원` budget fact.
- Compress or deprioritize unrelated logs and code.
- Answer feasibility using the correct project budget.

---

## 5. EXAONE Validation Workflow

UCE core remains provider-agnostic. A validation script can call both UCE and Ollama externally.

Recommended local flow:

```text
1. Start UCE Docker container.
2. Ensure Ollama is running locally.
3. Pull/run EXAONE 3.5 7.8B.
4. For each scenario:
   a. Build raw prompt.
   b. Send raw prompt to Ollama.
   c. Send scenario to UCE /build-context.
   d. Send prompt_pack.content to Ollama.
   e. Save both responses and UCE metadata.
   f. Manually score using the rubric.
```

Commands:

```bash
docker build -t uce:local .
docker run --rm -p 8100:8100 uce:local
```

```bash
ollama pull exaone3.5:7.8b
ollama run exaone3.5:7.8b "안녕하세요"
```

Validation runner location:

```text
scripts/compare-ollama.py
```

The runner is a development tool, not UCE core.

---

## 6. Prompt Comparison Example

### Raw Prompt Example

```text
You are a helpful assistant.

Recent conversation:
User: UCE is a stateless context middleware.
Assistant: Understood.
User: UCE must not call an LLM internally.
User: It should generate prompt_pack only.

Current user question:
Implement the next MVP step.
```

Potential issue:

- Important constraints are buried in plain conversation.
- The model may treat all prior messages equally.
- Long conversations become noisy.

### UCE Prompt Pack Example

```text
[Current Goal]
Implement the next MVP step.

[Intent]
Primary intent: coding
Reasoning mode: code_implementation

[Conversation State]
Active project: UCE
Current focus: Phase 2 validation

[Relevant Context]
- UCE is a stateless context middleware.
- UCE returns prompt_pack and does not call an LLM internally.

[Important Constraints]
- UCE must remain provider-agnostic.
- UCE must not become a RAG platform.
- UCE core must not call EXAONE directly.

[Current User Question]
Implement the next MVP step.
```

Expected improvement:

- Constraints are explicit.
- Relevant context is compact.
- The LLM sees the current task and boundaries quickly.

---

## 7. Lightweight Component Updates

Only two Phase 2 core improvements should be considered now.

1. Adaptive Compression
2. Context Importance Scoring

Do not add:

- mandatory vector DB
- persistent memory ownership
- agent workflow
- topic graph
- narrative graph
- distributed orchestration

---

## 8. Adaptive Compression

Current compression is generic. Phase 2 should make compression intent-aware while staying heuristic and explainable.

### 8.1 Compression Profiles

Add a small profile map:

```python
COMPRESSION_PROFILES = {
    "coding": {
        "preserve_markers": ["error", "traceback", "file", "expected", "actual", "API", "endpoint"],
        "sections": ["errors", "files", "expected_behavior", "constraints", "recent_steps"],
    },
    "design": {
        "preserve_markers": ["architecture", "constraint", "tradeoff", "decision", "goal"],
        "sections": ["goals", "constraints", "decisions", "tradeoffs", "open_questions"],
    },
    "summarize": {
        "preserve_markers": ["decided", "next", "unresolved", "because"],
        "sections": ["chronology", "decisions", "open_questions"],
    },
    "analyze": {
        "preserve_markers": ["evidence", "cause", "because", "risk", "unclear"],
        "sections": ["evidence", "causal_chain", "ambiguity", "risks"],
    },
}
```

### 8.2 Coding Mode

Preserve:

- file paths
- function/class names
- API endpoints
- error messages
- expected behavior
- actual behavior
- implementation constraints

Drop first:

- repeated planning text
- polite filler
- old resolved discussion

### 8.3 Design Mode

Preserve:

- goals
- constraints
- decisions
- tradeoffs
- component boundaries
- excluded scope

Drop first:

- repeated philosophy text
- historical wording if decisions already captured
- low-specificity background

### 8.4 Summarize Mode

Preserve:

- chronology
- decisions
- unresolved questions
- next actions

Drop first:

- duplicated explanations
- low-importance examples

### 8.5 Analyze Mode

Preserve:

- evidence
- causal chain
- uncertainty
- assumptions
- risks

Drop first:

- unsupported conclusions
- repeated surface descriptions

### 8.6 Implementation Strategy

Minimal implementation:

```text
Intent Analyzer
  -> primary_intent
  -> compression profile

Compressor
  -> classify lines/messages by marker rules
  -> preserve high-priority snippets
  -> compress remaining context by current length rule
  -> return profile_used and preserved_categories in metadata
```

No ML required.

Recommended output metadata:

```json
{
  "compression_profile": "coding",
  "preserved_categories": ["constraints", "api_endpoints", "expected_behavior"]
}
```

---

## 9. Context Importance Scoring

Current retrieval scoring is too simple. Phase 2 should add a lightweight multi-factor score.

For documents, retrieval follows `retrieve large -> compress locally`. UCE first retrieves coherent sections, then compresses only inside selected sections. This avoids tiny unrelated chunks competing with semantic overview sections.

### 9.1 Scoring Factors

Recommended factors:

| Factor | Meaning |
| --- | --- |
| `semantic_score` | keyword/token overlap with current message |
| `heading_score` | query tokens matched in heading/section path |
| `section_path_score` | same signal as heading score, exposed for debug visibility |
| `section_priority_score` | overview/summary/goals/phase/architecture sections score higher |
| `section_coherence_score` | coherent sections score higher than fragmented chunks |
| `recency_score` | newer messages score higher; document chunks use neutral recency |
| `intent_alignment_score` | message or section matches current intent profile |
| `constraint_score` | contains constraint/decision/requirement markers |
| `decision_score` | contains decision markers |

### 9.2 Formula

Keep the formula simple and configurable.

```text
final_score =
  0.35 * heading_score
+ 0.20 * section_coherence_score
+ 0.18 * semantic_score
+ 0.12 * intent_alignment_score
+ 0.08 * recency_score
+ 0.07 * constraint_score
```

Then add small explainable boosts for `decision_score`, `section_priority_score`, and exact overview headings such as `12. Phase 계획 > Phase 2: Practical Context Engineering`.

For topic shift:

```text
fresh_context:
  skip recent retrieval

minimal_context:
  require final_score >= 0.60

focused_context:
  require final_score >= 0.35

full_context:
  require final_score >= 0.15
```

### 9.3 Explainable Score Output

Each selected context item should be able to expose a score breakdown.

Example:

```json
{
  "id": "msg_12",
  "semantic_score": 0.82,
  "heading_score": 0.91,
  "section_path_score": 0.91,
  "section_priority_score": 1.0,
  "recency_score": 0.61,
  "intent_alignment_score": 0.73,
  "constraint_score": 0.91,
  "decision_score": 0.0,
  "final_score": 0.79,
  "reason": "heading direct match: phase, section priority boost"
}
```

MVP can include this in internal trace or metadata later. It does not need to be part of the main prompt.

### 9.4 Implementation Strategy

Minimal implementation:

```text
retriever.py
  -> generate candidate items
  -> compute score breakdown
  -> attach reason

ranker.py
  -> sort by final_score
  -> apply policy threshold
  -> return selected and dropped counts
```

No vector DB required.

---

## 10. Updated Retrieval Flow

```text
Input request
  -> Intent Analyzer
  -> Topic Shift Detector
  -> Context Policy
  -> Candidate Retrieval
  -> Multi-factor Importance Scoring
  -> Policy Threshold Filtering
  -> Adaptive Compression
  -> Prompt Synthesis
  -> Context Pack Output
```

This keeps UCE small while improving the two observed weak spots:

- generic compression
- overly simple context selection

---

## 11. Minimal Architecture Changes

Add or update only:

```text
app/core/compression_profiles.py   optional
app/core/compressor.py             update
app/core/retriever.py              update score breakdown
app/core/ranker.py                 apply policy threshold
scripts/compare-ollama.py          external validation runner
examples/eval/*.json               scenario fixtures
```

Do not change:

- UCE statelessness
- provider-agnostic core
- API-first middleware boundary
- no internal LLM call rule

---

## 12. Validation Output Format

The comparison runner should save JSONL records.

```json
{
  "scenario": "constraint_sensitive",
  "model": "exaone3.5:7.8b",
  "raw_response": "...",
  "uce_response": "...",
  "uce_metadata": {
    "intent_confidence": 0.95,
    "topic_relation": "continue_topic",
    "compression_ratio": 0.42,
    "selected_context_count": 8
  },
  "manual_scores": {
    "response_consistency": null,
    "constraint_preservation": null,
    "hallucination_reduction": null,
    "topic_continuity": null,
    "implementation_quality": null,
    "token_efficiency": null,
    "long_conversation_stability": null
  }
}
```

Human review fills `manual_scores`.

---

## 13. Success Criteria

Phase 2 should be considered useful only if validation shows practical gains.

Minimum useful signals:

- UCE response preserves constraints better than raw prompt in most constraint-sensitive cases.
- UCE response handles topic shift better than raw prompt.
- Long conversation scenarios show lower irrelevant-context leakage.
- UCE does not significantly degrade simple fresh-topic questions.
- Prompt build latency remains small enough for local use.

If EXAONE validation does not show improvement, do not add more architecture. First inspect failures and adjust:

- compression profile rules
- scoring weights
- topic thresholds
- prompt template wording

---

## 14. Backlog Only

These ideas are intentionally not Phase 2 work:

- Topic Graph
- Constraint Pinning
- Context Decay
- Narrative Graph
- State Stability Systems
- Vector DB integration
- memory ownership
- autonomous planning

They may become relevant only after repeated validation failures justify them.

---

## 15. Recommended Next Step

Implement the external EXAONE comparison runner first.

Then run it against:

1. existing `build-context.sample.json`
2. existing `topic-shift.sample.json`
3. one long conversation fixture
4. one constraint-sensitive coding fixture

Only after reviewing responses should adaptive compression and scoring changes be implemented.
