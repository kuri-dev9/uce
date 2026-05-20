# UCE - Universal Context Engine

UCE is a provider-agnostic Context Pack middleware for LLM applications.

It does not call an LLM internally. It accepts the current user message, recent conversation, previous state, and optional externally owned memories, then returns a structured prompt pack.

Current status:

- Phase 1 Context Pack MVP: complete
- Phase 2 Practical Context Engineering: complete
- Optional middleware integration validated in reasondock
- First validation target: EXAONE 3.5 7.8B via Ollama

## Run With Docker

```bash
docker build -t uce:local .
docker run --rm -p 8100:8100 uce:local
```

## Manual API Check

In another shell:

```bash
./scripts/smoke-api.sh
```

Or inspect the generated prompt directly:

```bash
curl -sS -X POST http://localhost:8100/build-context \
  -H "Content-Type: application/json" \
  --data-binary @examples/build-context.sample.json
```

## Compare Raw vs UCE With Ollama

Start UCE, make sure Ollama is running, then:

```bash
ollama pull exaone3.5:7.8b
python3 scripts/compare-ollama.py examples/eval/scenario-01-ghost-constraint.json
```

Results are saved under `runs/eval/`.

## Try One Message

Use an existing context fixture, override only the current message, and compare normal output vs UCE output:

```bash
python3 scripts/try-uce.py \
  --context examples/eval/scenario-03-context-junk.json \
  --message "이 예산으로 Phase 2 기능을 구현할 수 있어?"
```

Add `--show-prompts` to inspect the raw prompt and UCE prompt.
By default, this command does not save outputs. Add `--save` to write a report under `runs/try/`.

Markdown/text files can be used as a base document context:

```bash
python3 scripts/try-uce.py \
  --context docs/architecture.md \
  --message "UCE의 Phase 2 목표가 뭐야?" \
  --debug-retrieval
```

In this mode, the normal/raw prompt does not receive the document. Only UCE receives the document, retrieves relevant sections, compresses them, and sends the resulting `prompt_pack` to the LLM.

The retrieval target for that question should be section-level context such as:

```text
12. Phase 계획
17. Practical Chunking Strategy (Phase 2)
```

## docx / xlsx Context

The CLI can load `.docx` and `.xlsx` files, convert them to markdown, and pass them into the existing UCE pipeline:

```bash
python3 scripts/try-uce.py \
  --context path/to/spec.docx \
  --message "이 문서의 핵심 목표가 뭐야?" \
  --debug-retrieval
```

```bash
python3 scripts/try-uce.py \
  --context path/to/data.xlsx \
  --message "각 시트의 핵심 내용을 요약해줘" \
  --debug-retrieval
```

Phase 2 treats xlsx sheets as markdown tables. Deterministic spreadsheet query execution is planned for Phase 3.

## Queryless Document Compression

`current_message` is optional. If no message is provided, UCE ranks and compresses document sections by importance:

```bash
python3 scripts/try-uce.py \
  --context docs/architecture.md \
  --debug-retrieval \
  --show-prompts
```

## Integration Pattern

UCE is designed to be used as an optional HTTP middleware:

```text
Application -> UCE /build-context -> Application LLM entrypoint -> LLM
```

If UCE fails, the host application should fallback to its legacy prompt flow. UCE remains stateless and does not own conversations, messages, storage, or LLM orchestration.

## Docs

- [Architecture](docs/architecture.md)
- [API Reference](docs/api-reference.md)
- [Getting Started](docs/getting-started.md)
- [Implementation Guide](docs/implementation-guide.md)
- [Roadmap](docs/roadmap.md)
- [Phase 2 Validation Strategy](docs/phase2-validation.md)
