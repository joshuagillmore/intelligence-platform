"""Mind map export utilities — JSON, Markdown, Mermaid formats."""
from __future__ import annotations


def tree_to_markdown(node: dict, depth: int = 0) -> str:
    """Convert a topic tree to indented Markdown outline."""
    lines = []
    indent = "  " * depth
    name = node.get("name", "")
    count = node.get("count", node.get("document_count", ""))
    count_str = f" ({count})" if count else ""
    prefix = "#" * min(depth + 1, 6) + " " if depth < 3 else f"{indent}- "
    lines.append(f"{prefix}{name}{count_str}")

    keywords = node.get("keywords", [])
    if keywords and depth > 0:
        lines.append(f"{indent}  Keywords: {', '.join(keywords[:5])}")

    for child in node.get("children", []):
        lines.append(tree_to_markdown(child, depth + 1))

    return "\n".join(lines)


def tree_to_mermaid(node: dict) -> str:
    """Convert a topic tree to Mermaid mindmap syntax."""
    lines = ["mindmap"]

    def _walk(n: dict, depth: int = 1) -> None:
        indent = "  " * depth
        name = n.get("name", "unnamed")
        safe_name = name.replace('"', "'").replace("\n", " ")
        lines.append(f"{indent}{safe_name}")
        for child in n.get("children", []):
            _walk(child, depth + 1)

    _walk(node)
    return "\n".join(lines)
