#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.adapters.document_loader import load_docx, load_xlsx


DEFAULT_UCE_URL = "http://localhost:8100"
DEFAULT_OLLAMA_URL = "http://localhost:11434"
DEFAULT_MODEL = "exaone3.5:7.8b"
CODE_EXTENSIONS = {".py", ".ts", ".js", ".go", ".rs", ".java", ".cpp", ".c", ".sh"}


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Type one message and compare normal LLM output vs UCE prompt_pack output.",
    )
    parser.add_argument("--message", "-m", default=None, help="Current user message. If omitted, UCE summarizes context without a query.")
    parser.add_argument(
        "--context",
        "-c",
        type=Path,
        help=(
            "Optional context file. Supports JSON fixtures/payloads, Markdown, or plain text."
        ),
    )
    parser.add_argument(
        "--doc-mode",
        choices=["memory", "recent"],
        default="memory",
        help="How to inject .md/.txt context files. memory keeps chunks as facts; recent keeps chunks as prior messages.",
    )
    parser.add_argument("--doc-max-chars", type=int, default=12000)
    parser.add_argument("--doc-chunk-chars", type=int, default=1400)
    parser.add_argument("--uce-url", default=DEFAULT_UCE_URL)
    parser.add_argument("--ollama-url", default=DEFAULT_OLLAMA_URL)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--temperature", type=float, default=0.1)
    parser.add_argument("--num-predict", type=int, default=900)
    parser.add_argument("--out-dir", type=Path, default=Path("runs/try"))
    parser.add_argument("--show-prompts", action="store_true")
    parser.add_argument("--debug-retrieval", action="store_true", help="Print selected/dropped context scoring metadata.")
    parser.add_argument("--save", action="store_true", help="Save prompts and outputs under runs/try/.")
    parser.add_argument("--no-save", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()

    message = args.message

    uce_payload = load_context_payload(
        args.context,
        doc_mode=args.doc_mode,
        doc_max_chars=args.doc_max_chars,
        doc_chunk_chars=args.doc_chunk_chars,
    )
    if message is None:
        uce_payload.pop("current_message", None)
    else:
        uce_payload["current_message"] = {
            "role": "user",
            "content": message,
            "created_at": dt.datetime.now().astimezone().isoformat(),
        }

    raw_prompt = build_raw_prompt(uce_payload)
    uce_response = post_json(f"{args.uce_url}/build-context", uce_payload)
    uce_prompt = uce_response["prompt_pack"]["content"]

    raw_answer = call_ollama(
        base_url=args.ollama_url,
        model=args.model,
        prompt=raw_prompt,
        temperature=args.temperature,
        num_predict=args.num_predict,
    )
    uce_answer = call_ollama(
        base_url=args.ollama_url,
        model=args.model,
        prompt=uce_prompt,
        temperature=args.temperature,
        num_predict=args.num_predict,
    )

    result = {
        "message": message or "",
        "model": args.model,
        "temperature": args.temperature,
        "num_predict": args.num_predict,
        "uce_metadata": uce_response["metadata"],
        "conversation_state": uce_response["conversation_state"],
        "compressed_context": uce_response["compressed_context"],
        "raw_prompt": raw_prompt,
        "uce_prompt": uce_prompt,
        "raw_answer": raw_answer,
        "uce_answer": uce_answer,
    }

    print_console_report(result, show_prompts=args.show_prompts, debug_retrieval=args.debug_retrieval)

    if args.save and not args.no_save:
        run_dir = save_result(result, args.out_dir)
        print()
        print(f"Saved to: {run_dir}")

    return 0


def load_context_payload(
    path: Path | None,
    doc_mode: str = "memory",
    doc_max_chars: int = 12000,
    doc_chunk_chars: int = 1400,
) -> dict[str, Any]:
    if path is None:
        return {
            "session_id": "try_uce_manual",
            "current_message": {"role": "user", "content": ""},
            "recent_messages": [],
            "previous_state": None,
            "optional_memories": [],
            "documents": [],
            "options": {
                "target_model": DEFAULT_MODEL,
                "compression_level": "medium",
                "max_prompt_tokens": 4000,
                "topic_shift_enabled": True,
            },
        }

    if path.suffix.lower() not in {".json"}:
        return build_payload_from_document(
            path=path,
            doc_mode=doc_mode,
            doc_max_chars=doc_max_chars,
            doc_chunk_chars=doc_chunk_chars,
        )

    data = json.loads(path.read_text(encoding="utf-8"))
    if "uce_request" in data:
        payload = data["uce_request"]
    else:
        payload = data

    payload = json.loads(json.dumps(payload, ensure_ascii=False))
    payload.setdefault("session_id", f"try_{path.stem}")
    payload.setdefault("recent_messages", [])
    payload.setdefault("previous_state", None)
    payload.setdefault("optional_memories", [])
    payload.setdefault("documents", [])
    payload.setdefault("options", {})
    payload["options"].setdefault("target_model", DEFAULT_MODEL)
    payload["options"].setdefault("compression_level", "medium")
    payload["options"].setdefault("max_prompt_tokens", 4000)
    payload["options"].setdefault("topic_shift_enabled", True)
    return payload


def build_payload_from_document(
    path: Path,
    doc_mode: str,
    doc_max_chars: int,
    doc_chunk_chars: int,
) -> dict[str, Any]:
    suffix = path.suffix.lower()
    if suffix == ".docx":
        text = load_docx(path)
    elif suffix == ".xlsx":
        text = load_xlsx(path)
    else:
        text = path.read_text(encoding="utf-8")
    trimmed = text[:doc_max_chars]
    title = extract_title(trimmed) or path.stem

    payload = {
        "session_id": f"try_doc_{path.stem}",
        "current_message": {"role": "user", "content": ""},
        "recent_messages": [],
        "previous_state": {
            "active_project": "UCE" if "Universal Context Engine" in trimmed or "UCE" in trimmed else None,
            "current_focus": f"Base document: {path.name}",
            "user_goal": f"Use the base document '{path.name}' as context for the current question.",
            "important_constraints": [],
            "open_questions": [],
            "decisions": [],
            "reasoning_mode": "general",
        },
        "optional_memories": [],
        "documents": [],
        "options": {
            "target_model": DEFAULT_MODEL,
            "compression_level": "medium",
            "max_prompt_tokens": 4000,
            "topic_shift_enabled": True,
            "topic_continue_threshold": 0.08,
            "topic_related_threshold": 0.03,
            "max_recent_messages": 20,
        },
    }

    if doc_mode == "recent":
        chunks = chunk_text(trimmed, doc_chunk_chars)
        payload["recent_messages"] = [
            {
                "id": f"{path.stem}_chunk_{index + 1}",
                "role": "assistant",
                "content": f"Base document {path.name} chunk {index + 1}/{len(chunks)}:\n{chunk}",
            }
            for index, chunk in enumerate(chunks)
        ]
    else:
        payload["documents"] = [
            {
                "id": path.stem,
                "title": title,
                "content": trimmed,
                "content_type": content_type_for_path(path),
                "source": str(path),
                "importance": 0.85,
            }
        ]

    if title:
        payload["optional_memories"].insert(
            0,
            {
                "type": "fact",
                "content": f"Base document title: {title}",
                "importance": 0.95,
                "confidence": 0.95,
            },
        )
    return payload


def extract_title(text: str) -> str | None:
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("# "):
            return stripped[2:].strip()
    return None


def content_type_for_path(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix in {".md", ".docx", ".xlsx"}:
        return "markdown"
    if suffix in CODE_EXTENSIONS:
        return "code"
    return "text"


def chunk_text(text: str, chunk_chars: int) -> list[str]:
    paragraphs = [part.strip() for part in text.split("\n\n") if part.strip()]
    chunks: list[str] = []
    current = ""
    for paragraph in paragraphs:
        if len(current) + len(paragraph) + 2 <= chunk_chars:
            current = f"{current}\n\n{paragraph}".strip()
        else:
            if current:
                chunks.append(current)
            if len(paragraph) <= chunk_chars:
                current = paragraph
            else:
                chunks.extend(paragraph[i : i + chunk_chars] for i in range(0, len(paragraph), chunk_chars))
                current = ""
    if current:
        chunks.append(current)
    return chunks or [text[:chunk_chars]]


def build_raw_prompt(payload: dict[str, Any]) -> str:
    current_message = payload.get("current_message") or {"content": ""}
    lines = [
        "You are a helpful assistant.",
        "Answer in Korean unless the user asks otherwise.",
        "",
        "[Recent Conversation]",
    ]
    recent = payload.get("recent_messages") or []
    if recent:
        for message in recent:
            role = message.get("role", "user").capitalize()
            lines.append(f"{role}: {message.get('content', '')}")
    else:
        lines.append("- none")

    lines.extend(
        [
            "",
            "[Current User Question]",
            current_message.get("content", ""),
        ]
    )
    return "\n".join(lines)


def post_json(url: str, payload: dict[str, Any]) -> dict[str, Any]:
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(url, data=data, method="POST")
    req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=30) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {exc.code} from {url}: {body}") from exc


def call_ollama(
    base_url: str,
    model: str,
    prompt: str,
    temperature: float,
    num_predict: int,
) -> str:
    payload = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "options": {
            "temperature": temperature,
            "num_predict": num_predict,
        },
    }
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(f"{base_url}/api/generate", data=data, method="POST")
    req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=180) as response:
            parsed = json.loads(response.read().decode("utf-8"))
            return parsed.get("response", "")
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Ollama HTTP {exc.code}: {body}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(
            f"Could not connect to Ollama at {base_url}. "
            f"Check `ollama serve` and `ollama pull {model}`."
        ) from exc


def print_console_report(result: dict[str, Any], show_prompts: bool = False, debug_retrieval: bool = False) -> None:
    metadata = result["uce_metadata"]
    compressed = result["compressed_context"]

    print("\n" + "=" * 80)
    print("UCE JUDGMENT")
    print("=" * 80)
    for key in [
        "primary_intent",
        "intent_confidence",
        "topic_relation",
        "context_policy",
        "topic_confidence",
        "topic_reason",
        "compression_ratio",
        "selected_context_count",
        "dropped_context_count",
        "retrieval_confidence",
        "retrieval_warning",
        "prompt_build_latency_ms",
    ]:
        print(f"{key}: {metadata.get(key)}")

    if debug_retrieval:
        print("\n" + "=" * 80)
        print("RETRIEVAL DEBUG")
        print("=" * 80)
        print_context_debug("SELECTED", metadata.get("survived_items") or [])
        print_context_debug("DROPPED", metadata.get("dropped_items") or [])

    print("\n" + "=" * 80)
    print("COMPRESSED CONTEXT")
    print("=" * 80)
    print("summary:")
    print(compressed.get("summary", ""))
    print("\nconstraints:")
    print_bullets(compressed.get("constraints") or [])
    print("\ndecisions:")
    print_bullets(compressed.get("decisions") or [])
    print("\nfacts:")
    print_bullets(compressed.get("facts") or [])

    if show_prompts:
        print("\n" + "=" * 80)
        print("RAW PROMPT")
        print("=" * 80)
        print(result["raw_prompt"])
        print("\n" + "=" * 80)
        print("UCE PROMPT")
        print("=" * 80)
        print(result["uce_prompt"])

    print("\n" + "=" * 80)
    print("1. NORMAL LLM OUTPUT")
    print("=" * 80)
    print(result["raw_answer"])

    print("\n" + "=" * 80)
    print("2. UCE LLM OUTPUT")
    print("=" * 80)
    print(result["uce_answer"])


def print_bullets(items: list[str]) -> None:
    if not items:
        print("- none")
        return
    for item in items:
        print(f"- {item}")


def print_context_debug(title: str, items: list[dict[str, Any]]) -> None:
    print(f"\n[{title}]")
    if not items:
        print("- none")
        return
    for item in items:
        breakdown = item.get("score_breakdown") or {}
        print(f"- {item.get('id')} score={item.get('score')} source={item.get('source')}")
        if item.get("section"):
            print(f"  section: {item.get('section')}")
        print(f"  reason: {item.get('reason')}")
        if breakdown:
            print(
                "  scores: "
                f"semantic={breakdown.get('semantic_score', 0.0)} "
                f"heading={breakdown.get('heading_score', 0.0)} "
                f"coherence={breakdown.get('section_coherence_score', 0.0)} "
                f"intent={breakdown.get('intent_alignment_score', 0.0)} "
                f"constraint={breakdown.get('constraint_score', 0.0)} "
                f"priority={breakdown.get('section_priority_score', 0.0)} "
                f"final={breakdown.get('final_score', item.get('score'))}"
            )
        else:
            print("  scores: unavailable")
        print(f"  preview: {item.get('preview')}")


def save_result(result: dict[str, Any], out_dir: Path) -> Path:
    timestamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    safe_name = "".join(ch if ch.isalnum() else "-" for ch in result["message"][:32]).strip("-")
    run_dir = out_dir / f"{timestamp}-{safe_name or 'manual'}"
    run_dir.mkdir(parents=True, exist_ok=True)

    (run_dir / "result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    (run_dir / "raw-prompt.txt").write_text(result["raw_prompt"], encoding="utf-8")
    (run_dir / "uce-prompt.txt").write_text(result["uce_prompt"], encoding="utf-8")
    (run_dir / "normal-output.txt").write_text(result["raw_answer"], encoding="utf-8")
    (run_dir / "uce-output.txt").write_text(result["uce_answer"], encoding="utf-8")
    (run_dir / "report.md").write_text(render_markdown(result), encoding="utf-8")
    return run_dir


def render_markdown(result: dict[str, Any]) -> str:
    return f"""# UCE Try Report

## Message

```text
{result["message"]}
```

## UCE Metadata

```json
{json.dumps(result["uce_metadata"], ensure_ascii=False, indent=2)}
```

## Compressed Context

```json
{json.dumps(result["compressed_context"], ensure_ascii=False, indent=2)}
```

## 1. Normal LLM Output

```text
{result["raw_answer"]}
```

## 2. UCE LLM Output

```text
{result["uce_answer"]}
```
"""


if __name__ == "__main__":
    raise SystemExit(main())
