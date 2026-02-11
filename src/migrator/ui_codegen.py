from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
import json
from pathlib import Path
import re
from typing import Any

from .models import AstNode, ScreenIR, SourceRef

_NON_ALNUM = re.compile(r"[^0-9A-Za-z]+")
_NUMERIC_VALUE_RE = re.compile(r"^-?\d+(\.\d+)?$")


@dataclass(slots=True)
class UiCodegenSummary:
    total_nodes: int
    rendered_nodes: int


@dataclass(slots=True)
class UiCodegenReport:
    screen_id: str
    input_xml_path: str
    component_name: str
    tsx_file: str
    summary: UiCodegenSummary
    warnings: list[str] = field(default_factory=list)
    generated_at_utc: str = field(default_factory=lambda: datetime.now(UTC).isoformat())

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _attr_lookup(attrs: dict[str, str], key: str) -> str | None:
    if key in attrs:
        return attrs[key]
    key_lower = key.lower()
    for attr_key, value in attrs.items():
        if attr_key.lower() == key_lower:
            return value
    return None


def _to_file_stem(raw: str) -> str:
    chunks = [chunk.lower() for chunk in _NON_ALNUM.split(raw) if chunk]
    return "-".join(chunks) if chunks else "screen"


def _to_component_name(raw: str) -> str:
    chunks = [chunk for chunk in _NON_ALNUM.split(raw) if chunk]
    if not chunks:
        return "GeneratedScreen"

    component = "".join(chunk[:1].upper() + chunk[1:] for chunk in chunks)
    if component[0].isdigit():
        component = f"Screen{component}"
    if component.lower().endswith("screen"):
        return component
    return f"{component}Screen"


def _to_jsx_string(value: str) -> str:
    return f"{{{json.dumps(value, ensure_ascii=False)}}}"


def _escape_comment(value: str) -> str:
    return value.replace("*/", "* /")


def _source_comment(source: SourceRef) -> str:
    line_part = f" line={source.line}" if source.line is not None else ""
    return _escape_comment(
        f"source file={source.file_path} node={source.node_path}{line_part}"
    )


def _to_css_token(raw: str) -> str:
    chunks = [chunk.lower() for chunk in _NON_ALNUM.split(raw) if chunk]
    return "-".join(chunks) if chunks else "node"


def _normalize_dimension(raw: str | None) -> str | None:
    if raw is None:
        return None
    value = raw.strip()
    if not value:
        return None
    if _NUMERIC_VALUE_RE.fullmatch(value):
        return f"{value}px"
    return value


def _build_node_style(node: AstNode, *, is_root: bool) -> dict[str, str]:
    style: dict[str, str] = {}
    if is_root:
        style["position"] = "relative"

    left = _normalize_dimension(_attr_lookup(node.attributes, "left"))
    top = _normalize_dimension(_attr_lookup(node.attributes, "top"))
    width = _normalize_dimension(_attr_lookup(node.attributes, "width"))
    height = _normalize_dimension(_attr_lookup(node.attributes, "height"))

    if left is not None:
        style["left"] = left
    if top is not None:
        style["top"] = top
    if width is not None:
        style["width"] = width
    if height is not None:
        style["height"] = height

    if left is not None or top is not None:
        style["position"] = "absolute"

    return style


def _style_attribute(style: dict[str, str]) -> str:
    if not style:
        return ""
    payload = {key: style[key] for key in sorted(style)}
    style_json = json.dumps(payload, ensure_ascii=False)
    return f" style={{{style_json}}}"


def _node_label(node: AstNode) -> str:
    label = node.tag
    node_id = _attr_lookup(node.attributes, "id")
    if node_id:
        label = f"{label}#{node_id}"
    text = _attr_lookup(node.attributes, "text")
    if text:
        label = f"{label} ({text})"
    return label


def _node_attrs_label(node: AstNode) -> str | None:
    if not node.attributes:
        return None
    parts = [
        f"{key}={value}"
        for key, value in sorted(node.attributes.items(), key=lambda item: item[0].lower())
    ]
    return ", ".join(parts)


def _render_node(node: AstNode, *, depth: int, is_root: bool = False) -> list[str]:
    indent = "  " * depth
    child_indent = "  " * (depth + 1)
    class_token = _to_css_token(node.tag)
    style_attr = _style_attribute(_build_node_style(node, is_root=is_root))

    lines = [
        f"{indent}{{/* {_source_comment(node.source)} */}}",
        (
            f'{indent}<div className="mi-node mi-node-{class_token}" '
            f"data-mi-tag={_to_jsx_string(node.tag)} "
            f"data-mi-source-node={_to_jsx_string(node.source.node_path)} "
            f"data-mi-source-file={_to_jsx_string(node.source.file_path)}"
            f"{style_attr}>"
        ),
        f'{child_indent}<div className="mi-node-label">{_to_jsx_string(_node_label(node))}</div>',
    ]

    attrs_label = _node_attrs_label(node)
    if attrs_label is not None:
        lines.append(
            f'{child_indent}<div className="mi-node-attrs">{_to_jsx_string(attrs_label)}</div>'
        )

    for child in node.children:
        lines.extend(_render_node(child, depth=depth + 1))

    lines.append(f"{indent}</div>")
    return lines


def _count_nodes(node: AstNode) -> int:
    total = 1
    for child in node.children:
        total += _count_nodes(child)
    return total


def _render_screen_component(screen: ScreenIR, component_name: str) -> str:
    root = screen.root
    header_source_file = _escape_comment(root.source.file_path)
    header_source_node = _escape_comment(root.source.node_path)

    lines = [
        "/* Generated by mifl-migrator gen-ui. */",
        f"/* sourceXmlPath: {header_source_file} */",
        f"/* sourceNodePath: {header_source_node} */",
        "",
        'import type { JSX } from "react";',
        "",
        f"export default function {component_name}(): JSX.Element {{",
        "  return (",
        (
            '    <section className="mi-generated-screen" '
            f"data-mi-screen-id={_to_jsx_string(screen.screen_id)} "
            f"data-mi-source-node={_to_jsx_string(root.source.node_path)} "
            f"data-mi-source-file={_to_jsx_string(root.source.file_path)}>"
        ),
    ]
    lines.extend(_render_node(root, depth=3, is_root=True))
    lines.extend(
        [
            "    </section>",
            "  );",
            "}",
            "",
        ]
    )
    return "\n".join(lines)


def generate_ui_codegen_artifacts(
    *,
    screen: ScreenIR,
    input_xml_path: str,
    out_dir: str | Path,
) -> UiCodegenReport:
    out_root = Path(out_dir).resolve()
    screen_stem = _to_file_stem(screen.screen_id)
    component_name = _to_component_name(screen.screen_id)
    tsx_path = out_root / "src" / "screens" / f"{screen_stem}.tsx"
    tsx_path.parent.mkdir(parents=True, exist_ok=True)

    tsx_path.write_text(_render_screen_component(screen, component_name), encoding="utf-8")

    total_nodes = _count_nodes(screen.root)
    warnings: list[str] = []
    if total_nodes <= 1:
        warnings.append("Screen has no child nodes; generated output is minimal.")

    return UiCodegenReport(
        screen_id=screen.screen_id,
        input_xml_path=str(Path(input_xml_path).resolve()),
        component_name=component_name,
        tsx_file=str(tsx_path),
        summary=UiCodegenSummary(total_nodes=total_nodes, rendered_nodes=total_nodes),
        warnings=warnings,
    )


__all__ = [
    "UiCodegenReport",
    "UiCodegenSummary",
    "generate_ui_codegen_artifacts",
]
