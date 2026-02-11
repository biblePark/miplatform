from __future__ import annotations

import hashlib
import xml.etree.ElementTree as ET

from .canonical import canonical_xml_from_ast, canonical_xml_from_element
from .models import AstNode, StructuralMismatch


def compute_roundtrip_structural_diff(
    xml_root: ET.Element,
    ast_root: AstNode,
    *,
    include_text: bool = True,
) -> int:
    return len(
        compute_roundtrip_mismatches(xml_root, ast_root, include_text=include_text)
    )


def compute_roundtrip_mismatches(
    xml_root: ET.Element,
    ast_root: AstNode,
    *,
    include_text: bool = True,
) -> list[StructuralMismatch]:
    source_signatures = _structural_signatures_from_element(xml_root, include_text=include_text)
    ast_signatures = _structural_signatures_from_ast(ast_root, include_text=include_text)

    mismatches: list[StructuralMismatch] = []
    all_paths = sorted(set(source_signatures) | set(ast_signatures))
    for path in all_paths:
        source_sig = source_signatures.get(path)
        ast_sig = ast_signatures.get(path)
        if source_sig == ast_sig:
            continue
        reason = _mismatch_reason(source_sig, ast_sig)
        mismatches.append(
            StructuralMismatch(
                position_path=_format_position_path(path),
                reason=reason,
                source_signature=_signature_to_text(source_sig),
                ast_signature=_signature_to_text(ast_sig),
            )
        )

    return mismatches


def compute_canonical_hash_pair(
    xml_root: ET.Element,
    ast_root: AstNode,
    *,
    include_text: bool = True,
) -> tuple[str, str]:
    source_canonical = canonical_xml_from_element(xml_root, include_text=include_text)
    ast_canonical = canonical_xml_from_ast(ast_root, include_text=include_text)

    source_hash = hashlib.sha256(source_canonical.encode("utf-8")).hexdigest()
    ast_hash = hashlib.sha256(ast_canonical.encode("utf-8")).hexdigest()
    return source_hash, ast_hash


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


def _mismatch_reason(
    source_sig: tuple[object, ...] | None,
    ast_sig: tuple[object, ...] | None,
) -> str:
    if source_sig is None:
        return "missing_in_source"
    if ast_sig is None:
        return "missing_in_ast"

    source_tag, source_attrs, source_text = source_sig
    ast_tag, ast_attrs, ast_text = ast_sig

    if source_tag != ast_tag:
        return "tag_mismatch"
    if source_attrs != ast_attrs:
        return "attribute_mismatch"
    if source_text != ast_text:
        return "text_mismatch"
    return "signature_mismatch"


def _format_position_path(path: tuple[int, ...]) -> str:
    return ".".join(str(part) for part in path)


def _signature_to_text(signature: tuple[object, ...] | None) -> str | None:
    if signature is None:
        return None
    tag, attrs, text = signature
    return f"tag={tag};attrs={attrs};text={text}"


def diff_gate_message(diff_count: int) -> str:
    if diff_count == 0:
        return "Roundtrip structural diff is zero."
    return f"Roundtrip structural diff detected: {diff_count}"


def canonical_gate_message(matched: bool) -> str:
    if matched:
        return "Canonical XML hashes match between source XML and AST regeneration."
    return "Canonical XML hash mismatch between source XML and AST regeneration."
