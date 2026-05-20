#!/usr/bin/env python3
import argparse
import datetime as dt
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


DEFAULT_UCE_URL = "http://localhost:8100"
DEFAULT_OLLAMA_URL = "http://localhost:11434"
DEFAULT_MODEL = "exaone3.5:7.8b"


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Compare raw conversation prompt vs UCE prompt_pack using Ollama.",
    )
    parser.add_argument("scenario", type=Path, help="Path to examples/eval/*.json")
    parser.add_argument("--uce-url", default=DEFAULT_UCE_URL)
    parser.add_argument("--ollama-url", default=DEFAULT_OLLAMA_URL)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--temperature", type=float, default=0.1)
    parser.add_argument("--num-predict", type=int, default=900)
    parser.add_argument("--out-dir", type=Path, default=Path("runs/eval"))
    parser.add_argument("--raw-only", action="store_true", help="Only call Ollama with raw prompt.")
    parser.add_argument("--uce-only", action="store_true", help="Only call UCE prompt through Ollama.")
    parser.add_argument(
        "--raw-include-state",
        action="store_true",
        help="Include previous_state in the raw baseline prompt. Disabled by default for a stricter baseline.",
    )
    parser.add_argument(
        "--raw-include-memories",
        action="store_true",
        help="Include optional_memories in the raw baseline prompt. Disabled by default for a stricter baseline.",
    )
    args = parser.parse_args()

    if args.raw_only and args.uce_only:
        print("--raw-only and --uce-only cannot be used together.", file=sys.stderr)
        return 2

    scenario = load_json(args.scenario)
    scenario = expand_document_context(scenario, args.scenario.parent)
    uce_request = scenario["uce_request"]
    scenario_id = scenario.get("scenario_id", args.scenario.stem)

    raw_prompt = build_raw_prompt(
        scenario,
        include_state=args.raw_include_state,
        include_memories=args.raw_include_memories,
    )
    uce_response: dict[str, Any] | None = None
    uce_prompt = ""

    if not args.raw_only:
        uce_response = post_json(f"{args.uce_url}/build-context", uce_request)
        uce_prompt = uce_response["prompt_pack"]["content"]

    raw_response = None
    uce_model_response = None

    if not args.uce_only:
        raw_response = call_ollama(
            base_url=args.ollama_url,
            model=args.model,
            prompt=raw_prompt,
            temperature=args.temperature,
            num_predict=args.num_predict,
        )

    if not args.raw_only:
        uce_model_response = call_ollama(
            base_url=args.ollama_url,
            model=args.model,
            prompt=uce_prompt,
            temperature=args.temperature,
            num_predict=args.num_predict,
        )

    timestamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    run_dir = args.out_dir / f"{timestamp}-{scenario_id}"
    run_dir.mkdir(parents=True, exist_ok=True)

    result = {
        "scenario_id": scenario_id,
        "title": scenario.get("title"),
        "model": args.model,
        "temperature": args.temperature,
        "num_predict": args.num_predict,
        "manual_checks": scenario.get("manual_checks", {}),
        "raw_baseline": {
            "include_state": args.raw_include_state,
            "include_memories": args.raw_include_memories,
        },
        "target_failure": scenario.get("target_failure", []),
        "expected_uce_behavior": scenario.get("expected_uce_behavior", []),
        "uce_metadata": uce_response.get("metadata") if uce_response else None,
        "raw_prompt": raw_prompt,
        "uce_prompt": uce_prompt,
        "raw_response": raw_response,
        "uce_response": uce_model_response,
    }
    result["auto_checks"] = evaluate_auto_checks(result)

    (run_dir / "result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    (run_dir / "raw-prompt.txt").write_text(raw_prompt, encoding="utf-8")
    if uce_prompt:
        (run_dir / "uce-prompt.txt").write_text(uce_prompt, encoding="utf-8")
    if raw_response is not None:
        (run_dir / "raw-response.txt").write_text(raw_response, encoding="utf-8")
    if uce_model_response is not None:
        (run_dir / "uce-response.txt").write_text(uce_model_response, encoding="utf-8")
    (run_dir / "comparison.md").write_text(render_markdown(result), encoding="utf-8")

    print(f"Saved comparison to: {run_dir}")
    print()
    print_summary(result)
    return 0


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def expand_document_context(scenario: dict[str, Any], base_dir: Path) -> dict[str, Any]:
    document_context = scenario.get("document_context")
    if not document_context:
        return scenario

    path = Path(document_context["path"])
    if not path.is_absolute():
        repo_relative = Path.cwd() / path
        path = repo_relative if repo_relative.exists() else base_dir / path

    content = path.read_text(encoding="utf-8")
    req = scenario.setdefault("uce_request", {})
    documents = req.setdefault("documents", [])
    documents.append(
        {
            "id": document_context.get("id") or path.stem,
            "title": document_context.get("title") or extract_title(content) or path.stem,
            "content": content,
            "content_type": document_context.get("content_type") or ("markdown" if path.suffix == ".md" else "text"),
            "source": str(path),
            "importance": document_context.get("importance", 0.85),
        }
    )
    return scenario


def extract_title(text: str) -> str | None:
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("# "):
            return stripped[2:].strip()
    return None


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


def build_raw_prompt(
    scenario: dict[str, Any],
    include_state: bool = False,
    include_memories: bool = False,
) -> str:
    req = scenario["uce_request"]
    lines = [
        "You are a helpful assistant.",
        "Answer in Korean unless the user asks otherwise.",
        "",
        "[Recent Conversation]",
    ]
    for message in req.get("recent_messages", []):
        role = message.get("role", "user").capitalize()
        lines.append(f"{role}: {message.get('content', '')}")

    previous_state = req.get("previous_state")
    if include_state and previous_state:
        lines.extend(
            [
                "",
                "[Previous State, if useful]",
                json.dumps(previous_state, ensure_ascii=False),
            ]
        )

    memories = req.get("optional_memories") or []
    if include_memories and memories:
        lines.extend(
            [
                "",
                "[Optional Memories, if useful]",
                json.dumps(memories, ensure_ascii=False),
            ]
        )

    lines.extend(
        [
            "",
            "[Current User Question]",
            req["current_message"]["content"],
        ]
    )
    return "\n".join(lines)


def render_markdown(result: dict[str, Any]) -> str:
    metadata = result.get("uce_metadata") or {}
    manual_checks = result.get("manual_checks") or {}
    auto_checks = result.get("auto_checks") or {}
    return f"""# UCE Comparison: {result.get("scenario_id")}

Model: `{result.get("model")}`  
Temperature: `{result.get("temperature")}`  

## UCE Metadata

```json
{json.dumps(metadata, ensure_ascii=False, indent=2)}
```

## Manual Checks

```json
{json.dumps(manual_checks, ensure_ascii=False, indent=2)}
```

## Raw Baseline

```json
{json.dumps(result.get("raw_baseline") or {}, ensure_ascii=False, indent=2)}
```

## Auto Checks

{render_auto_checks(auto_checks)}

## Target Failures

{format_list(result.get("target_failure") or [])}

## Expected UCE Behavior

{format_list(result.get("expected_uce_behavior") or [])}

## Raw Response

```text
{result.get("raw_response") or ""}
```

## UCE Response

```text
{result.get("uce_response") or ""}
```

## Review Notes

- Response consistency:
- Constraint preservation:
- Hallucination reduction:
- Topic continuity:
- Implementation quality:
- Token efficiency:
- Long conversation stability:
"""


def format_list(items: list[str]) -> str:
    if not items:
        return "- none"
    return "\n".join(f"- {item}" for item in items)


def evaluate_auto_checks(result: dict[str, Any]) -> dict[str, Any]:
    checks = result.get("manual_checks") or {}
    raw_response = result.get("raw_response") or ""
    uce_response = result.get("uce_response") or ""
    return {
        "raw": evaluate_response_checks(raw_response, checks),
        "uce": evaluate_response_checks(uce_response, checks),
    }


def evaluate_response_checks(response: str, checks: dict[str, Any]) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for item in checks.get("must_include", []):
        results.append(
            {
                "rule": "must_include",
                "value": item,
                "passed": item in response,
            }
        )
    for key in ["must_not_include", "must_not_claim", "must_not_treat_as_budget"]:
        for item in checks.get(key, []):
            results.append(
                {
                    "rule": key,
                    "value": item,
                    "passed": item not in response,
                }
            )
    return results


def render_auto_checks(auto_checks: dict[str, Any]) -> str:
    lines = ["| Side | Rule | Value | Result |", "| --- | --- | --- | --- |"]
    for side in ["raw", "uce"]:
        for check in auto_checks.get(side, []):
            result = "PASS" if check.get("passed") else "FAIL"
            value = str(check.get("value", "")).replace("|", "\\|")
            lines.append(f"| {side.upper()} | `{check.get('rule')}` | {value} | **{result}** |")
    if len(lines) == 2:
        lines.append("| - | - | no checks | - |")
    return "\n".join(lines)


def print_summary(result: dict[str, Any]) -> None:
    metadata = result.get("uce_metadata") or {}
    print("== UCE metadata ==")
    for key in [
        "primary_intent",
        "intent_confidence",
        "topic_relation",
        "context_policy",
        "compression_ratio",
        "selected_context_count",
        "dropped_context_count",
        "retrieval_confidence",
        "retrieval_warning",
    ]:
        if key in metadata:
            print(f"{key}: {metadata[key]}")

    raw = result.get("raw_response") or ""
    uce = result.get("uce_response") or ""
    if raw:
        print(f"raw_response_chars: {len(raw)}")
    if uce:
        print(f"uce_response_chars: {len(uce)}")
    auto_checks = result.get("auto_checks") or {}
    for side in ["raw", "uce"]:
        checks = auto_checks.get(side, [])
        if checks:
            passed = sum(1 for check in checks if check.get("passed"))
            print(f"{side}_auto_checks: {passed}/{len(checks)} passed")


if __name__ == "__main__":
    raise SystemExit(main())
