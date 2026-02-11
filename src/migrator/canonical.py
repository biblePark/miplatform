from __future__ import annotations

import xml.etree.ElementTree as ET
from xml.sax.saxutils import escape, quoteattr

from .models import AstNode


def canonical_xml_from_element(root: ET.Element, *, include_text: bool = True) -> str:
    return _serialize_element(root, include_text=include_text, level=0)


def canonical_xml_from_ast(root: AstNode, *, include_text: bool = True) -> str:
    return _serialize_ast(root, include_text=include_text, level=0)


def _normalize_text(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    return normalized if normalized else None


def _attrs_to_string(attrs: dict[str, str]) -> str:
    if not attrs:
        return ""
    ordered = " ".join(f"{key}={quoteattr(str(value))}" for key, value in sorted(attrs.items()))
    return f" {ordered}"


def _serialize_element(elem: ET.Element, *, include_text: bool, level: int) -> str:
    indent = "  " * level
    attrs = _attrs_to_string(dict(elem.attrib))
    text = _normalize_text(elem.text) if include_text else None
    children = list(elem)

    if not children and text is None:
        return f"{indent}<{elem.tag}{attrs}/>"

    if not children:
        return f"{indent}<{elem.tag}{attrs}>{escape(text or '')}</{elem.tag}>"

    lines = [f"{indent}<{elem.tag}{attrs}>"]
    if text is not None:
        lines.append(f"{'  ' * (level + 1)}{escape(text)}")
    for child in children:
        lines.append(_serialize_element(child, include_text=include_text, level=level + 1))
    lines.append(f"{indent}</{elem.tag}>")
    return "\n".join(lines)


def _serialize_ast(node: AstNode, *, include_text: bool, level: int) -> str:
    indent = "  " * level
    attrs = _attrs_to_string(node.attributes)
    text = _normalize_text(node.text) if include_text else None
    children = node.children

    if not children and text is None:
        return f"{indent}<{node.tag}{attrs}/>"

    if not children:
        return f"{indent}<{node.tag}{attrs}>{escape(text or '')}</{node.tag}>"

    lines = [f"{indent}<{node.tag}{attrs}>"]
    if text is not None:
        lines.append(f"{'  ' * (level + 1)}{escape(text)}")
    for child in children:
        lines.append(_serialize_ast(child, include_text=include_text, level=level + 1))
    lines.append(f"{indent}</{node.tag}>")
    return "\n".join(lines)
