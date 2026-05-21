from dataclasses import replace

from app.api.schemas import Memory
from app.core.retriever import ContextItem


def rank_context_items(
    items: list[ContextItem],
    limit: int = 10,
    min_score: float | None = None,
) -> tuple[list[ContextItem], list[ContextItem]]:
    sorted_items = sorted(items, key=lambda item: item.score, reverse=True)
    if min_score is None:
        selected = sorted_items[:limit]
        dropped = [_with_drop_reason(item, "limit_exceeded") for item in sorted_items[limit:]]
        return selected, dropped

    eligible = [item for item in sorted_items if item.score >= min_score]
    selected = eligible[:limit]
    selected_ids = {item.id for item in selected}
    dropped = [
        _with_drop_reason(item, "limit_exceeded" if item.score >= min_score else "below_min_score")
        for item in sorted_items
        if item.id not in selected_ids
    ]
    return selected, dropped


def rank_memories(memories: list[Memory], limit: int = 8) -> list[Memory]:
    return sorted(
        memories,
        key=lambda memory: (memory.importance * 0.7) + (memory.confidence * 0.3),
        reverse=True,
    )[:limit]


def survival_metadata(
    selected: list[ContextItem],
    dropped: list[ContextItem],
    limit: int = 20,
) -> tuple[list[dict], list[dict], dict[str, str]]:
    survived_items = [_metadata_item(item, "selected") for item in selected[:limit]]
    dropped_items = [_metadata_item(item, "dropped") for item in dropped[:limit]]
    survival_reasons = {
        item["id"]: item["reason"]
        for item in survived_items + dropped_items
    }
    return survived_items, dropped_items, survival_reasons


def _metadata_item(item: ContextItem, status: str) -> dict:
    metadata = item.metadata or {}
    return {
        "id": item.id,
        "source": item.source,
        "type": item.item_type,
        "status": status,
        "section": metadata.get("header_path") or metadata.get("section_title"),
        "heading_level": metadata.get("heading_level"),
        "parent_id": metadata.get("parent_id"),
        "children": metadata.get("children", []),
        "score": item.score,
        "preview": _preview(item.prompt_content or item.content),
        "reason": item.reason,
        "score_breakdown": item.score_breakdown,
        "taxonomy": list(item.taxonomy) if hasattr(item, "taxonomy") else [],
        "drop_reason": item.drop_reason if hasattr(item, "drop_reason") else None,
    }


def _preview(text: str, head: int = 700, tail: int = 300) -> str:
    compact = " ".join(text.split())
    if len(compact) <= head + tail + 3:
        return compact
    return f"{compact[:head]}...{compact[-tail:]}"


def _with_drop_reason(item: ContextItem, reason: str) -> ContextItem:
    return replace(item, drop_reason=reason)
