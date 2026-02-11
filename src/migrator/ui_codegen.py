from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
import json
from pathlib import Path
import re
from typing import Any

from .behavior_store_codegen import (
    BehaviorEventActionBinding,
    generate_behavior_store_artifacts,
)
from .models import AstNode, ScreenIR, SourceRef
from .runtime_wiring import RuntimeWiringContract, build_runtime_wiring_contract

_NUMERIC_VALUE_RE = re.compile(r"^-?\d+(\.\d+)?$")
_NON_ALNUM = re.compile(r"[^0-9A-Za-z]+")
_CONTAINER_TAGS = frozenset({"screen", "contents", "container"})
_EVENT_ATTR_TO_REACT_PROP: dict[str, str] = {
    "onclick": "onClick",
    "ondblclick": "onDoubleClick",
    "onchange": "onChange",
    "oninput": "onInput",
    "onfocus": "onFocus",
    "onblur": "onBlur",
    "onkeydown": "onKeyDown",
    "onkeyup": "onKeyUp",
    "onmousedown": "onMouseDown",
    "onmouseup": "onMouseUp",
    "onmouseenter": "onMouseEnter",
    "onmouseleave": "onMouseLeave",
}


@dataclass(slots=True)
class UiCodegenSummary:
    total_nodes: int
    rendered_nodes: int
    wired_event_bindings: int


@dataclass(slots=True)
class UiCodegenReport:
    screen_id: str
    input_xml_path: str
    component_name: str
    tsx_file: str
    behavior_store_file: str
    behavior_actions_file: str
    wiring_contract: RuntimeWiringContract
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


def _node_attrs_label(node: AstNode) -> str | None:
    if not node.attributes:
        return None
    parts = [
        f"{key}={value}"
        for key, value in sorted(node.attributes.items(), key=lambda item: item[0].lower())
    ]
    return ", ".join(parts)


def _widget_kind(tag: str) -> str:
    tag_lower = tag.lower()
    if tag_lower in _CONTAINER_TAGS:
        return "container"
    if tag_lower in {"button", "edit", "static", "combo", "grid"}:
        return tag_lower
    return "fallback"


def _node_display_text(node: AstNode, *, fallback: str) -> str:
    text_attr = _attr_lookup(node.attributes, "text")
    if text_attr is not None and text_attr.strip():
        return text_attr.strip()
    if node.text is not None and node.text.strip():
        return node.text.strip()
    node_id = _attr_lookup(node.attributes, "id")
    if node_id is not None and node_id.strip():
        return node_id.strip()
    return fallback


def _trace_attributes(node: AstNode) -> list[str]:
    attrs = [
        f"data-mi-tag={_to_jsx_string(node.tag)}",
        f"data-mi-source-node={_to_jsx_string(node.source.node_path)}",
        f"data-mi-source-file={_to_jsx_string(node.source.file_path)}",
    ]
    if node.source.line is not None:
        attrs.append(f"data-mi-source-line={_to_jsx_string(str(node.source.line))}")
    attrs_label = _node_attrs_label(node)
    if attrs_label is not None:
        attrs.append(f"data-mi-attrs={_to_jsx_string(attrs_label)}")
    return attrs


def _event_lookup_key(
    *,
    node_path: str,
    event_name: str,
    handler: str,
) -> tuple[str, str, str]:
    return (node_path, event_name.lower(), handler.strip())


def _build_event_action_lookup(
    event_action_bindings: list[BehaviorEventActionBinding],
) -> dict[tuple[str, str, str], str]:
    lookup: dict[tuple[str, str, str], str] = {}
    for binding in event_action_bindings:
        lookup[
            _event_lookup_key(
                node_path=binding.node_path,
                event_name=binding.event_name,
                handler=binding.handler,
            )
        ] = binding.action_name
    return lookup


def _render_widget_body(node: AstNode, *, widget_kind: str, depth: int) -> list[str]:
    indent = "  " * depth
    if widget_kind == "container":
        return []

    if widget_kind == "button":
        label = _node_display_text(node, fallback="Button")
        return [
            (
                f'{indent}<Button className="mi-widget mi-widget-button" '
                f'variant="contained">{_to_jsx_string(label)}</Button>'
            )
        ]

    if widget_kind == "edit":
        label = _node_display_text(node, fallback="Edit")
        default_value = _attr_lookup(node.attributes, "value") or ""
        return [
            (
                f'{indent}<TextField className="mi-widget mi-widget-edit" '
                f'size="small" label={_to_jsx_string(label)} '
                f'defaultValue={_to_jsx_string(default_value)} />'
            )
        ]

    if widget_kind == "static":
        value = _node_display_text(node, fallback="Static")
        return [
            (
                f'{indent}<Typography className="mi-widget mi-widget-static" '
                f'variant="body2">{_to_jsx_string(value)}</Typography>'
            )
        ]

    if widget_kind == "combo":
        label = _node_display_text(node, fallback="Combo")
        placeholder = f"Select {label}"
        return [
            f'{indent}<FormControl className="mi-widget mi-widget-combo" size="small">',
            f"{indent}  <InputLabel>{_to_jsx_string(label)}</InputLabel>",
            (
                f"{indent}  <Select label={_to_jsx_string(label)} "
                f"defaultValue={_to_jsx_string('')}>"
            ),
            f"{indent}    <MenuItem value={_to_jsx_string('')}>{_to_jsx_string(placeholder)}</MenuItem>",
            f"{indent}  </Select>",
            f"{indent}</FormControl>",
        ]

    if widget_kind == "grid":
        grid_title = _node_display_text(node, fallback="Grid")
        bind_dataset = _attr_lookup(node.attributes, "binddataset")
        header_text = (
            f"{grid_title} ({bind_dataset})"
            if bind_dataset is not None and bind_dataset.strip()
            else grid_title
        )
        return [
            f'{indent}<TableContainer className="mi-widget mi-widget-grid">',
            f"{indent}  <Table size=\"small\" aria-label={_to_jsx_string(grid_title)}>",
            f"{indent}    <TableHead>",
            f"{indent}      <TableRow>",
            f"{indent}        <TableCell>{_to_jsx_string(header_text)}</TableCell>",
            f"{indent}      </TableRow>",
            f"{indent}    </TableHead>",
            f"{indent}    <TableBody>",
            f"{indent}      <TableRow>",
            f"{indent}        <TableCell>{_to_jsx_string('Generated grid placeholder')}</TableCell>",
            f"{indent}      </TableRow>",
            f"{indent}    </TableBody>",
            f"{indent}  </Table>",
            f"{indent}</TableContainer>",
        ]

    return [
        (
            f'{indent}<Typography className="mi-widget mi-widget-fallback" '
            f'variant="caption">{_to_jsx_string(f"Unsupported tag: {node.tag}")}</Typography>'
        )
    ]


def _render_node(
    node: AstNode,
    *,
    depth: int,
    warnings: list[str],
    event_action_lookup: dict[tuple[str, str, str], str],
    behavior_store_var: str,
    is_root: bool = False,
) -> list[str]:
    indent = "  " * depth
    class_token = _to_css_token(node.tag)
    widget_kind = _widget_kind(node.tag)
    trace_attrs = _trace_attributes(node)
    if widget_kind == "fallback":
        trace_attrs.append(f"data-mi-fallback={_to_jsx_string('unsupported-tag')}")
        warnings.append(
            (
                f"Unsupported widget tag '{node.tag}' at {node.source.node_path}; "
                "rendered as fallback widget."
            )
        )

    event_props: list[str] = []
    for attr_name, attr_value in sorted(node.attributes.items(), key=lambda item: item[0].lower()):
        attr_lower = attr_name.lower()
        if not attr_lower.startswith("on") or len(attr_lower) <= 2:
            continue

        action_name = event_action_lookup.get(
            _event_lookup_key(
                node_path=node.source.node_path,
                event_name=attr_lower,
                handler=attr_value,
            )
        )
        if action_name is None:
            warnings.append(
                (
                    f"No behavior action binding resolved for event '{attr_name}' "
                    f"at {node.source.node_path}; runtime handler not wired."
                )
            )
            continue

        trace_attrs.append(
            f"data-mi-action-{_to_css_token(attr_lower)}={_to_jsx_string(action_name)}"
        )
        react_event_prop = _EVENT_ATTR_TO_REACT_PROP.get(attr_lower)
        if react_event_prop is None:
            warnings.append(
                (
                    f"No React event mapping for '{attr_name}' at {node.source.node_path}; "
                    f"action '{action_name}' trace emitted only."
                )
            )
            continue

        event_props.append(f"{react_event_prop}={{{behavior_store_var}.{action_name}}}")

    style_attr = _style_attribute(_build_node_style(node, is_root=is_root))
    trace_payload = " ".join(trace_attrs)
    event_payload = " ".join(event_props)
    event_segment = f" {event_payload}" if event_payload else ""

    lines = [
        f"{indent}{{/* {_source_comment(node.source)} */}}",
        (
            f'{indent}<Box className="mi-widget-shell mi-widget-shell-{class_token}" '
            f"data-mi-widget={_to_jsx_string(widget_kind)} "
            f"{trace_payload}{event_segment}{style_attr}>"
        ),
    ]

    lines.extend(_render_widget_body(node, widget_kind=widget_kind, depth=depth + 1))
    for child in node.children:
        lines.extend(
            _render_node(
                child,
                depth=depth + 1,
                warnings=warnings,
                event_action_lookup=event_action_lookup,
                behavior_store_var=behavior_store_var,
            )
        )
    lines.append(f"{indent}</Box>")
    return lines


def _count_nodes(node: AstNode) -> int:
    total = 1
    for child in node.children:
        total += _count_nodes(child)
    return total


def _render_screen_component(
    screen: ScreenIR,
    *,
    wiring_contract: RuntimeWiringContract,
    warnings: list[str],
    event_action_lookup: dict[tuple[str, str, str], str],
) -> str:
    root = screen.root
    header_source_file = _escape_comment(root.source.file_path)
    header_source_node = _escape_comment(root.source.node_path)
    behavior_store_var = "behaviorStore"

    lines = [
        "/* Generated by mifl-migrator gen-ui. */",
        f"/* sourceXmlPath: {header_source_file} */",
        f"/* sourceNodePath: {header_source_node} */",
        (
            "/* runtimeWiring: "
            f"storeHook={wiring_contract.behavior_store_hook_name} "
            f"storeImport={wiring_contract.behavior_store_import_from_screen} */"
        ),
        "",
        'import type { JSX } from "react";',
        'import { Box, Button, FormControl, InputLabel, MenuItem, Select, Table, TableBody, TableCell, TableContainer, TableHead, TableRow, TextField, Typography } from "@mui/material";',
        (
            f'import {{ {wiring_contract.behavior_store_hook_name} }} '
            f'from "{wiring_contract.behavior_store_import_from_screen}";'
        ),
        "",
        f"export default function {wiring_contract.screen_component_name}(): JSX.Element {{",
        f"  const {behavior_store_var} = {wiring_contract.behavior_store_hook_name}();",
        "",
        "  return (",
        (
            '    <section className="mi-generated-screen" '
            f"data-mi-screen-id={_to_jsx_string(screen.screen_id)} "
            f"data-mi-source-node={_to_jsx_string(root.source.node_path)} "
            f"data-mi-source-file={_to_jsx_string(root.source.file_path)}>"
        ),
    ]
    lines.extend(
        _render_node(
            root,
            depth=3,
            warnings=warnings,
            event_action_lookup=event_action_lookup,
            behavior_store_var=behavior_store_var,
            is_root=True,
        )
    )
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
    wiring_contract = build_runtime_wiring_contract(screen.screen_id)
    tsx_path = out_root / "src" / "screens" / f"{wiring_contract.screen_file_stem}.tsx"
    tsx_path.parent.mkdir(parents=True, exist_ok=True)

    behavior_report = generate_behavior_store_artifacts(
        screen=screen,
        input_xml_path=input_xml_path,
        out_dir=out_root,
    )

    warnings: list[str] = []
    tsx_path.write_text(
        _render_screen_component(
            screen,
            wiring_contract=wiring_contract,
            warnings=warnings,
            event_action_lookup=_build_event_action_lookup(
                behavior_report.event_action_bindings
            ),
        ),
        encoding="utf-8",
    )

    total_nodes = _count_nodes(screen.root)
    if total_nodes <= 1:
        warnings.append("Screen has no child nodes; generated output is minimal.")

    return UiCodegenReport(
        screen_id=screen.screen_id,
        input_xml_path=str(Path(input_xml_path).resolve()),
        component_name=wiring_contract.screen_component_name,
        tsx_file=str(tsx_path),
        behavior_store_file=behavior_report.store_file,
        behavior_actions_file=behavior_report.actions_file,
        wiring_contract=wiring_contract,
        summary=UiCodegenSummary(
            total_nodes=total_nodes,
            rendered_nodes=total_nodes,
            wired_event_bindings=len(behavior_report.event_action_bindings),
        ),
        warnings=warnings,
    )


__all__ = [
    "UiCodegenReport",
    "UiCodegenSummary",
    "generate_ui_codegen_artifacts",
]
