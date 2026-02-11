from __future__ import annotations

import xml.etree.ElementTree as ET

from .models import AstNode


def compute_roundtrip_structural_diff(
    xml_root: ET.Element,
    ast_root: AstNode,
    *,
    include_text: bool = True,
) -> int:
    source_signatures = _structural_signatures_from_element(xml_root, include_text=include_text)
    ast_signatures = _structural_signatures_from_ast(ast_root, include_text=include_text)
    all_paths = set(source_signatures) | set(ast_signatures)
    return sum(1 for path in all_paths if source_signatures.get(path) != ast_signatures.get(path))


def _normalize_text(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    return normalized if normalized else None


def _signature(tag: str, attrs: dict[str, str], text: str | None) -> tuple[object, ...]:
    return (
        tag,
        tuple(sorted(attrs.items())),
        text,
    )


def _structural_signatures_from_element(
    root: ET.Element, *, include_text: bool
) -> dict[tuple[int, ...], tuple[object, ...]]:
    signatures: dict[tuple[int, ...], tuple[object, ...]] = {}

    def walk(elem: ET.Element, position_path: tuple[int, ...]) -> None:
        text = _normalize_text(elem.text) if include_text else None
        signatures[position_path] = _signature(elem.tag, dict(elem.attrib), text)
        for idx, child in enumerate(list(elem), start=1):
            walk(child, position_path + (idx,))

    walk(root, (1,))
    return signatures


def _structural_signatures_from_ast(
    root: AstNode, *, include_text: bool
) -> dict[tuple[int, ...], tuple[object, ...]]:
    signatures: dict[tuple[int, ...], tuple[object, ...]] = {}

    def walk(node: AstNode, position_path: tuple[int, ...]) -> None:
        text = _normalize_text(node.text) if include_text else None
        signatures[position_path] = _signature(node.tag, node.attributes, text)
        for idx, child in enumerate(node.children, start=1):
            walk(child, position_path + (idx,))

    walk(root, (1,))
    return signatures


def diff_gate_message(diff_count: int) -> str:
    if diff_count == 0:
        return "Roundtrip structural diff is zero."
    return f"Roundtrip structural diff detected: {diff_count}"
