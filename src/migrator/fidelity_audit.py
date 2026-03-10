from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
import json
from pathlib import Path
import re
from typing import Any

from .models import AstNode, ScreenIR

_CATEGORY_POSITION = "position"
_CATEGORY_STYLE = "style"
_FALSE_ATTR_VALUES = frozenset({"false", "0", "off", "no", "n"})
_TRUE_ATTR_VALUES = frozenset({"true", "1", "on", "yes", "y"})
_STYLE_PROP_RE = re.compile(r"style=\{\{(?P<payload>.*?)\}\}")
_WIDGET_LINE_TOKEN = '<Box className="mi-widget-shell'
_NON_RENDERED_SOURCE_TAGS = frozenset(
    {
        "datasets",
        "dataset",
        "record",
        "colinfo",
        "column",
        "col",
        "columns",
        "format",
        "head",
        "body",
        "summary",
        "cell",
        "cd",
        "data",
        "script",
        "transaction",
        "params",
        "param",
        "httpfile",
        "filedialog",
        "file",
        "cylastinput",
        "persistdata",
        "_persistdata",
    }
)


@dataclass(frozen=True, slots=True)
class _CoverageSpec:
    style_key: str
    category: str
    requires_false: bool = False


_ATTR_TO_STYLE_SPEC: dict[str, _CoverageSpec] = {
    "left": _CoverageSpec("left", _CATEGORY_POSITION),
    "top": _CoverageSpec("top", _CATEGORY_POSITION),
    "right": _CoverageSpec("right", _CATEGORY_POSITION),
    "bottom": _CoverageSpec("bottom", _CATEGORY_POSITION),
    "width": _CoverageSpec("width", _CATEGORY_STYLE),
    "height": _CoverageSpec("height", _CATEGORY_STYLE),
    "minwidth": _CoverageSpec("minWidth", _CATEGORY_STYLE),
    "minheight": _CoverageSpec("minHeight", _CATEGORY_STYLE),
    "maxwidth": _CoverageSpec("maxWidth", _CATEGORY_STYLE),
    "maxheight": _CoverageSpec("maxHeight", _CATEGORY_STYLE),
    "padding": _CoverageSpec("padding", _CATEGORY_STYLE),
    "paddingleft": _CoverageSpec("paddingLeft", _CATEGORY_STYLE),
    "padding-left": _CoverageSpec("paddingLeft", _CATEGORY_STYLE),
    "paddingtop": _CoverageSpec("paddingTop", _CATEGORY_STYLE),
    "padding-top": _CoverageSpec("paddingTop", _CATEGORY_STYLE),
    "paddingright": _CoverageSpec("paddingRight", _CATEGORY_STYLE),
    "padding-right": _CoverageSpec("paddingRight", _CATEGORY_STYLE),
    "paddingbottom": _CoverageSpec("paddingBottom", _CATEGORY_STYLE),
    "padding-bottom": _CoverageSpec("paddingBottom", _CATEGORY_STYLE),
    "margin": _CoverageSpec("margin", _CATEGORY_STYLE),
    "marginleft": _CoverageSpec("marginLeft", _CATEGORY_STYLE),
    "margin-left": _CoverageSpec("marginLeft", _CATEGORY_STYLE),
    "margintop": _CoverageSpec("marginTop", _CATEGORY_STYLE),
    "margin-top": _CoverageSpec("marginTop", _CATEGORY_STYLE),
    "marginright": _CoverageSpec("marginRight", _CATEGORY_STYLE),
    "margin-right": _CoverageSpec("marginRight", _CATEGORY_STYLE),
    "marginbottom": _CoverageSpec("marginBottom", _CATEGORY_STYLE),
    "margin-bottom": _CoverageSpec("marginBottom", _CATEGORY_STYLE),
    "background": _CoverageSpec("background", _CATEGORY_STYLE),
    "backgroundcolor": _CoverageSpec("backgroundColor", _CATEGORY_STYLE),
    "backcolor": _CoverageSpec("backgroundColor", _CATEGORY_STYLE),
    "color": _CoverageSpec("color", _CATEGORY_STYLE),
    "textcolor": _CoverageSpec("color", _CATEGORY_STYLE),
    "forecolor": _CoverageSpec("color", _CATEGORY_STYLE),
    "border": _CoverageSpec("border", _CATEGORY_STYLE),
    "bordercolor": _CoverageSpec("borderColor", _CATEGORY_STYLE),
    "borderstyle": _CoverageSpec("borderStyle", _CATEGORY_STYLE),
    "borderwidth": _CoverageSpec("borderWidth", _CATEGORY_STYLE),
    "borderradius": _CoverageSpec("borderRadius", _CATEGORY_STYLE),
    "radius": _CoverageSpec("borderRadius", _CATEGORY_STYLE),
    "fontfamily": _CoverageSpec("fontFamily", _CATEGORY_STYLE),
    "fontsize": _CoverageSpec("fontSize", _CATEGORY_STYLE),
    "fontweight": _CoverageSpec("fontWeight", _CATEGORY_STYLE),
    "letterspacing": _CoverageSpec("letterSpacing", _CATEGORY_STYLE),
    "textalign": _CoverageSpec("textAlign", _CATEGORY_STYLE),
    "align": _CoverageSpec("textAlign", _CATEGORY_STYLE),
    "whitespace": _CoverageSpec("whiteSpace", _CATEGORY_STYLE),
    "overflow": _CoverageSpec("overflow", _CATEGORY_STYLE),
    "opacity": _CoverageSpec("opacity", _CATEGORY_STYLE),
    "zindex": _CoverageSpec("zIndex", _CATEGORY_STYLE),
    "display": _CoverageSpec("display", _CATEGORY_STYLE),
    "gap": _CoverageSpec("gap", _CATEGORY_STYLE),
    "visible": _CoverageSpec("display", _CATEGORY_STYLE, requires_false=True),
    "isvisible": _CoverageSpec("display", _CATEGORY_STYLE, requires_false=True),
    "enable": _CoverageSpec("pointerEvents", _CATEGORY_STYLE, requires_false=True),
    "enabled": _CoverageSpec("pointerEvents", _CATEGORY_STYLE, requires_false=True),
    "isenabled": _CoverageSpec("pointerEvents", _CATEGORY_STYLE, requires_false=True),
}


@dataclass(slots=True)
class FidelitySourceNodeInventory:
    node_path: str
    tag: str
    expected_position_attributes: list[str] = field(default_factory=list)
    expected_style_attributes: list[str] = field(default_factory=list)


@dataclass(slots=True)
class FidelityGeneratedNodeInventory:
    node_path: str
    tag: str | None
    style_keys: list[str] = field(default_factory=list)


@dataclass(slots=True)
class FidelityPositionStyleCoverageRisk:
    node_path: str
    source_tag: str
    expected_position_attributes: list[str] = field(default_factory=list)
    covered_position_attributes: list[str] = field(default_factory=list)
    missing_position_attributes: list[str] = field(default_factory=list)
    expected_style_attributes: list[str] = field(default_factory=list)
    covered_style_attributes: list[str] = field(default_factory=list)
    missing_style_attributes: list[str] = field(default_factory=list)
    generated_style_keys: list[str] = field(default_factory=list)


@dataclass(slots=True)
class FidelityAuditSummary:
    xml_node_count: int
    generated_ui_node_count: int
    missing_node_count: int
    extra_generated_node_count: int
    position_attribute_total: int
    position_attribute_covered: int
    position_attribute_coverage_ratio: float
    style_attribute_total: int
    style_attribute_covered: int
    style_attribute_coverage_ratio: float
    position_style_nodes_with_risk: int


@dataclass(slots=True)
class FidelityAuditReport:
    screen_id: str
    input_xml_path: str
    generated_ui_file: str
    xml_inventory: list[FidelitySourceNodeInventory]
    generated_ui_inventory: list[FidelityGeneratedNodeInventory]
    summary: FidelityAuditSummary
    missing_node_paths: list[str] = field(default_factory=list)
    extra_generated_node_paths: list[str] = field(default_factory=list)
    position_style_coverage_risks: list[FidelityPositionStyleCoverageRisk] = field(
        default_factory=list
    )
    warnings: list[str] = field(default_factory=list)
    generated_at_utc: str = field(default_factory=lambda: datetime.now(UTC).isoformat())

    def to_dict(self, *, include_generated_at: bool = True) -> dict[str, Any]:
        payload = asdict(self)
        if not include_generated_at:
            payload.pop("generated_at_utc", None)
        return payload

    def has_blocking_risks(self) -> bool:
        return (
            self.summary.missing_node_count > 0
            or self.summary.position_style_nodes_with_risk > 0
        )


class FidelityAuditStrictError(RuntimeError):
    """Raised when strict fidelity audit verification fails."""


@dataclass(slots=True)
class _SourceCoverageNode:
    node_path: str
    tag: str
    expected_position: list[tuple[str, str]]
    expected_style: list[tuple[str, str]]


def _normalize_boolean(raw: str | None) -> bool | None:
    if raw is None:
        return None
    value = raw.strip().lower()
    if not value:
        return None
    if value in _TRUE_ATTR_VALUES:
        return True
    if value in _FALSE_ATTR_VALUES:
        return False
    return None


def _iter_nodes(root: AstNode):
    yield root
    for child in root.children:
        yield from _iter_nodes(child)


def _should_skip_source_node(node: AstNode) -> bool:
    tag_lower = node.tag.lower()
    if tag_lower in _NON_RENDERED_SOURCE_TAGS:
        return True
    path_lower = node.source.node_path.lower()
    if "/record[" in path_lower or "/data[" in path_lower or "/cd[" in path_lower:
        return True
    return False


def _coverage_ratio(*, covered: int, total: int) -> float:
    if total <= 0:
        return 1.0
    return round(covered / total, 6)


def _extract_json_prop(line: str, prop_name: str) -> str | None:
    pattern = re.compile(
        rf"{re.escape(prop_name)}=\{{(?P<value>\"(?:(?:\\.)|[^\"\\])*\")\}}"
    )
    match = pattern.search(line)
    if not match:
        return None
    try:
        value = json.loads(match.group("value"))
    except json.JSONDecodeError:
        return None
    return value if isinstance(value, str) else None


def _extract_style_payload(line: str) -> dict[str, str] | None:
    match = _STYLE_PROP_RE.search(line)
    if not match:
        return {}
    payload = match.group("payload").strip()
    if not payload:
        return {}
    try:
        parsed = json.loads("{" + payload + "}")
    except json.JSONDecodeError:
        return None
    if not isinstance(parsed, dict):
        return None
    result: dict[str, str] = {}
    for key in sorted(parsed):
        result[str(key)] = str(parsed[key])
    return result


def _collect_generated_ui_inventory(
    generated_ui_file: Path,
) -> tuple[list[FidelityGeneratedNodeInventory], dict[str, FidelityGeneratedNodeInventory], list[str]]:
    inventory_by_node_path: dict[str, FidelityGeneratedNodeInventory] = {}
    warnings: list[str] = []
    lines = generated_ui_file.read_text(encoding="utf-8").splitlines()
    for line_number, line in enumerate(lines, start=1):
        if _WIDGET_LINE_TOKEN not in line:
            continue

        node_path = _extract_json_prop(line, "data-mi-source-node")
        if not node_path:
            warnings.append(
                f"Generated widget line {line_number} is missing data-mi-source-node trace."
            )
            continue

        tag = _extract_json_prop(line, "data-mi-tag")
        style_payload = _extract_style_payload(line)
        if style_payload is None:
            warnings.append(
                f"Generated widget style payload is not valid JSON at line {line_number}."
            )
            style_keys: list[str] = []
        else:
            style_keys = sorted(style_payload)

        if node_path in inventory_by_node_path:
            warnings.append(
                f"Duplicate generated widget trace for node '{node_path}' at line {line_number}; last entry wins."
            )
        inventory_by_node_path[node_path] = FidelityGeneratedNodeInventory(
            node_path=node_path,
            tag=tag,
            style_keys=style_keys,
        )

    inventory = [
        inventory_by_node_path[path]
        for path in sorted(inventory_by_node_path)
    ]
    return inventory, inventory_by_node_path, warnings


def _expected_attr_coverage(node: AstNode) -> tuple[list[tuple[str, str]], list[tuple[str, str]]]:
    attrs_by_lower: dict[str, str] = {}
    for attr_name in sorted(node.attributes, key=lambda key: key.lower()):
        attrs_by_lower.setdefault(attr_name.lower(), attr_name)

    expected_position: list[tuple[str, str]] = []
    expected_style: list[tuple[str, str]] = []

    for attr_lower in sorted(attrs_by_lower):
        attr_name = attrs_by_lower[attr_lower]
        spec = _ATTR_TO_STYLE_SPEC.get(attr_lower)
        if spec is None:
            continue
        if spec.requires_false:
            if _normalize_boolean(node.attributes[attr_name]) is not False:
                continue
        pair = (attr_name, spec.style_key)
        if spec.category == _CATEGORY_POSITION:
            expected_position.append(pair)
        else:
            expected_style.append(pair)

    return expected_position, expected_style


def _collect_source_inventory(
    root: AstNode,
) -> tuple[list[FidelitySourceNodeInventory], dict[str, _SourceCoverageNode]]:
    source_inventory: list[FidelitySourceNodeInventory] = []
    coverage_by_path: dict[str, _SourceCoverageNode] = {}

    for node in _iter_nodes(root):
        if _should_skip_source_node(node):
            continue
        expected_position, expected_style = _expected_attr_coverage(node)
        source_inventory.append(
            FidelitySourceNodeInventory(
                node_path=node.source.node_path,
                tag=node.tag,
                expected_position_attributes=[name for name, _ in expected_position],
                expected_style_attributes=[name for name, _ in expected_style],
            )
        )
        coverage_by_path[node.source.node_path] = _SourceCoverageNode(
            node_path=node.source.node_path,
            tag=node.tag,
            expected_position=expected_position,
            expected_style=expected_style,
        )

    source_inventory.sort(key=lambda entry: entry.node_path)
    return source_inventory, coverage_by_path


def enforce_fidelity_audit_strict(report: FidelityAuditReport) -> None:
    if not report.has_blocking_risks():
        return
    raise FidelityAuditStrictError(
        "Strict fidelity audit failed for risks: "
        f"missing_node_count={report.summary.missing_node_count}, "
        "position_style_coverage_risk="
        f"{report.summary.position_style_nodes_with_risk}"
    )


def generate_fidelity_audit_report(
    *,
    screen: ScreenIR,
    input_xml_path: str,
    generated_ui_file: str | Path,
) -> FidelityAuditReport:
    generated_ui_path = Path(generated_ui_file).resolve()
    source_inventory, coverage_by_path = _collect_source_inventory(screen.root)
    generated_inventory, generated_by_path, warnings = _collect_generated_ui_inventory(
        generated_ui_path
    )

    source_paths = set(coverage_by_path)
    generated_paths = set(generated_by_path)
    missing_node_paths = sorted(source_paths - generated_paths)
    extra_generated_node_paths = sorted(generated_paths - source_paths)

    position_attribute_total = 0
    position_attribute_covered = 0
    style_attribute_total = 0
    style_attribute_covered = 0
    coverage_risks: list[FidelityPositionStyleCoverageRisk] = []

    for node_path in sorted(coverage_by_path):
        source_node = coverage_by_path[node_path]
        generated_node = generated_by_path.get(node_path)
        generated_style_keys = (
            set(generated_node.style_keys) if generated_node is not None else set()
        )

        expected_position = source_node.expected_position
        expected_style = source_node.expected_style

        covered_position_attributes = [
            attr_name
            for attr_name, style_key in expected_position
            if style_key in generated_style_keys
        ]
        missing_position_attributes = [
            attr_name
            for attr_name, style_key in expected_position
            if style_key not in generated_style_keys
        ]
        covered_style_attributes = [
            attr_name
            for attr_name, style_key in expected_style
            if style_key in generated_style_keys
        ]
        missing_style_attributes = [
            attr_name
            for attr_name, style_key in expected_style
            if style_key not in generated_style_keys
        ]

        position_attribute_total += len(expected_position)
        position_attribute_covered += len(covered_position_attributes)
        style_attribute_total += len(expected_style)
        style_attribute_covered += len(covered_style_attributes)

        if missing_position_attributes or missing_style_attributes:
            coverage_risks.append(
                FidelityPositionStyleCoverageRisk(
                    node_path=node_path,
                    source_tag=source_node.tag,
                    expected_position_attributes=[
                        attr_name for attr_name, _ in expected_position
                    ],
                    covered_position_attributes=covered_position_attributes,
                    missing_position_attributes=missing_position_attributes,
                    expected_style_attributes=[attr_name for attr_name, _ in expected_style],
                    covered_style_attributes=covered_style_attributes,
                    missing_style_attributes=missing_style_attributes,
                    generated_style_keys=sorted(generated_style_keys),
                )
            )

    summary = FidelityAuditSummary(
        xml_node_count=len(source_inventory),
        generated_ui_node_count=len(generated_inventory),
        missing_node_count=len(missing_node_paths),
        extra_generated_node_count=len(extra_generated_node_paths),
        position_attribute_total=position_attribute_total,
        position_attribute_covered=position_attribute_covered,
        position_attribute_coverage_ratio=_coverage_ratio(
            covered=position_attribute_covered,
            total=position_attribute_total,
        ),
        style_attribute_total=style_attribute_total,
        style_attribute_covered=style_attribute_covered,
        style_attribute_coverage_ratio=_coverage_ratio(
            covered=style_attribute_covered,
            total=style_attribute_total,
        ),
        position_style_nodes_with_risk=len(coverage_risks),
    )

    return FidelityAuditReport(
        screen_id=screen.screen_id,
        input_xml_path=str(Path(input_xml_path).resolve()),
        generated_ui_file=str(generated_ui_path),
        xml_inventory=source_inventory,
        generated_ui_inventory=generated_inventory,
        summary=summary,
        missing_node_paths=missing_node_paths,
        extra_generated_node_paths=extra_generated_node_paths,
        position_style_coverage_risks=coverage_risks,
        warnings=warnings,
    )


__all__ = [
    "FidelityAuditReport",
    "FidelityAuditStrictError",
    "FidelityAuditSummary",
    "FidelityGeneratedNodeInventory",
    "FidelityPositionStyleCoverageRisk",
    "FidelitySourceNodeInventory",
    "enforce_fidelity_audit_strict",
    "generate_fidelity_audit_report",
]
