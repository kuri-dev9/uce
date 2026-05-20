import re
from dataclasses import dataclass, field

from app.api.schemas import DocumentInput


@dataclass
class Section:
    id: str
    source: str
    document_id: str
    document_title: str
    title: str
    heading_level: int
    content: str
    prompt_content: str
    importance: float
    parent_id: str | None = None
    children: list[str] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)


@dataclass
class _SectionNode:
    title: str
    heading_level: int
    own_lines: list[str]
    parent: "_SectionNode | None" = None
    children: list["_SectionNode"] = field(default_factory=list)
    section_id: str = ""


def split_documents(
    documents: list[DocumentInput],
    max_chars: int = 1400,
    overlap_chars: int = 120,
    enabled: bool = True,
) -> list[Section]:
    sections: list[Section] = []
    for doc_index, document in enumerate(documents):
        doc_id = document.id or f"doc_{doc_index + 1}"
        title = document.title or document.source or doc_id
        if enabled and document.content_type == "markdown":
            nodes = _parse_markdown_sections(document.content)
        elif enabled and document.content_type == "code":
            nodes = _parse_code_sections(document.content)
        else:
            nodes = [_SectionNode(title=title, heading_level=1, own_lines=[document.content])]

        semantic_nodes = _semantic_retrieval_nodes(nodes)
        for section_index, node in enumerate(semantic_nodes, start=1):
            node.section_id = f"{doc_id}_section_{section_index}"

        node_to_id = {id(node): node.section_id for node in semantic_nodes}
        for node in semantic_nodes:
            path = _heading_path(node)
            content = _subtree_content(node)
            descendant_titles = _descendant_titles(node)
            child_ids = [node_to_id[id(child)] for child in node.children if id(child) in node_to_id]
            parent_id = node_to_id.get(id(node.parent)) if node.parent else None
            sections.append(
                Section(
                    id=node.section_id,
                    source=document.source or doc_id,
                    document_id=doc_id,
                    document_title=title,
                    title=node.title or title,
                    heading_level=node.heading_level or 1,
                    content=content,
                    prompt_content=_prepend_context(header_path=path, content=content),
                    importance=document.importance,
                    parent_id=parent_id,
                    children=child_ids,
                    metadata={
                        "document_id": doc_id,
                        "title": title,
                        "section_title": node.title or title,
                        "header_path": path,
                        "heading_level": node.heading_level,
                        "parent_id": parent_id,
                        "children": child_ids,
                        "descendant_titles": descendant_titles,
                        "content_type": document.content_type,
                    },
                )
            )
    return sections


def _parse_markdown_sections(text: str) -> list[_SectionNode]:
    root = _SectionNode(title="", heading_level=0, own_lines=[])
    stack: list[_SectionNode] = [root]
    current = root
    in_code = False

    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("```"):
            in_code = not in_code
            current.own_lines.append(line)
            continue

        heading_level = _heading_level(stripped) if not in_code else 0
        if heading_level:
            title = stripped.lstrip("#").strip()
            while stack and stack[-1].heading_level >= heading_level:
                stack.pop()
            parent = stack[-1] if stack else root
            node = _SectionNode(
                title=title,
                heading_level=heading_level,
                own_lines=[line],
                parent=parent,
            )
            parent.children.append(node)
            stack.append(node)
            current = node
        else:
            current.own_lines.append(line)

    return root.children if root.children else [root]


def _parse_code_sections(text: str) -> list[_SectionNode]:
    root = _SectionNode(title="module", heading_level=1, own_lines=[])
    header_node = _SectionNode(
        title="module_header",
        heading_level=2,
        own_lines=[],
        parent=root,
    )
    root.children.append(header_node)
    current = header_node
    pending_decorators: list[str] = []

    for line in text.splitlines():
        stripped = line.strip()
        match = re.match(r"^(async\s+def|def|class)\s+(\w+)", line)
        if match:
            node = _SectionNode(
                title=f"{match.group(1).strip()} {match.group(2)}",
                heading_level=2,
                own_lines=[*pending_decorators, line],
                parent=root,
            )
            pending_decorators = []
            root.children.append(node)
            current = node
        elif not line.startswith((" ", "\t")) and stripped.startswith("@"):
            pending_decorators.append(line)
        elif _is_module_level_line(line) and current is not header_node:
            if pending_decorators:
                header_node.own_lines.extend(pending_decorators)
                pending_decorators = []
            header_node.own_lines.append(line)
            current = header_node
        else:
            current.own_lines.append(line)

    return [node for node in root.children if _subtree_content(node).strip()]


def _is_module_level_line(line: str) -> bool:
    stripped = line.strip()
    if not stripped:
        return False
    if line.startswith((" ", "\t")):
        return False
    if stripped.startswith(("#", ")", "]", "}")):
        return False
    return True


def _semantic_retrieval_nodes(nodes: list[_SectionNode]) -> list[_SectionNode]:
    selected: list[_SectionNode] = []

    def walk(node: _SectionNode) -> None:
        if node.heading_level == 1 and node.children:
            for child in node.children:
                walk(child)
            return
        if node.heading_level in {1, 2}:
            selected.append(node)
            return
        if node.heading_level == 3 and not _nearest_retrievable_parent(node):
            selected.append(node)
            return
        for child in node.children:
            walk(child)

    for node in nodes:
        walk(node)
    return [node for node in selected if _subtree_content(node).strip()]


def _nearest_retrievable_parent(node: _SectionNode) -> _SectionNode | None:
    parent = node.parent
    while parent:
        if parent.heading_level in {1, 2}:
            return parent
        parent = parent.parent
    return None


def _heading_level(stripped: str) -> int:
    if not stripped.startswith("#"):
        return 0
    level = len(stripped) - len(stripped.lstrip("#"))
    if 1 <= level <= 6 and stripped[level : level + 1] == " ":
        return level
    return 0


def _heading_path(node: _SectionNode) -> str:
    path: list[str] = []
    current: _SectionNode | None = node
    while current and current.heading_level > 0:
        if current.title:
            path.append(current.title)
        current = current.parent
    return " > ".join(reversed(path))


def _subtree_content(node: _SectionNode) -> str:
    lines = list(node.own_lines)
    for child in node.children:
        child_content = _subtree_content(child)
        if child_content:
            lines.append(child_content)
    return "\n".join(line for line in lines if line is not None).strip()


def _descendant_titles(node: _SectionNode) -> list[str]:
    titles: list[str] = []

    def walk(current: _SectionNode) -> None:
        for child in current.children:
            if child.title:
                titles.append(child.title)
            walk(child)

    walk(node)
    return titles


def _prepend_context(header_path: str, content: str) -> str:
    if not header_path:
        return content.strip()
    return f"[Section]\n{header_path}\n\n[Content]\n{content}".strip()
