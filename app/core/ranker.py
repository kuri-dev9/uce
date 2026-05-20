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
        dropped = sorted_items[limit:]
        return selected, dropped

    eligible = [item for item in sorted_items if item.score >= min_score]
    selected = eligible[:limit]
    selected_ids = {item.id for item in selected}
    dropped = [item for item in sorted_items if item.id not in selected_ids]
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
    }


def _preview(text: str, limit: int = 180) -> str:
    compact = " ".join(text.split())
    return compact if len(compact) <= limit else compact[: limit - 3] + "..."
