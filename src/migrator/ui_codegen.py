from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
import json
import os
from pathlib import Path
import re
from typing import Any, Literal

from .behavior_store_codegen import (
    BehaviorEventActionBinding,
    generate_behavior_store_artifacts,
)
from .models import AstNode, ScreenIR, SourceRef
from .runtime_wiring import RuntimeWiringContract, build_runtime_wiring_contract

_NUMERIC_VALUE_RE = re.compile(r"^-?\d+(\.\d+)?$")
_NON_ALNUM = re.compile(r"[^0-9A-Za-z]+")
_XML_DECL_ENCODING_RE = re.compile(
    br"<\?xml[^>]*encoding\s*=\s*[\"']([^\"']+)[\"']",
    re.IGNORECASE,
)
_HANDLER_IDENTIFIER = re.compile(r"[A-Za-z_][A-Za-z0-9_.]*")
_FUNCTION_DECL_RE = re.compile(
    r"function\s+([A-Za-z_][A-Za-z0-9_]*)\s*\(([^)]*)\)\s*\{",
    re.IGNORECASE,
)
_VISIBLE_ASSIGN_RE = re.compile(
    r"([A-Za-z_][A-Za-z0-9_.]*)\s*\.Visible\s*=\s*(true|false)\s*;",
    re.IGNORECASE,
)
_IF_ELSE_RE = re.compile(
    r"if\s*\((?P<cond>[^)]*)\)\s*\{(?P<if_body>[^{}]*)\}\s*else\s*\{(?P<else_body>[^{}]*)\}",
    re.IGNORECASE | re.DOTALL,
)
_COND_EQ_RE = re.compile(
    r"""([A-Za-z_][A-Za-z0-9_]*)\s*==\s*(?:"([^"]*)"|'([^']*)'|([0-9]+))""",
    re.IGNORECASE,
)
_CONTAINER_TAGS = frozenset(
    {
        "screen",
        "contents",
        "container",
        "window",
        "form",
        "div",
        "shape",
        "tab",
        "tabpage",
        "layout",
        "layouts",
        "popupdiv",
    }
)
_WIDGET_TAG_ALIASES = {
    "button": "button",
    "edit": "edit",
    "static": "static",
    "combo": "combo",
    "grid": "grid",
    "textarea": "textarea",
    "maskedit": "maskedit",
    "image": "image",
    "radio": "radio",
    "checkbox": "checkbox",
    "calendar": "calendar",
    "calendarex": "calendar",
    "spin": "spin",
    "treeview": "treeview",
    "webbrowser": "webbrowser",
    "msie": "webbrowser",
    "rexpert": "webbrowser",
    "xchart": "xchart",
}
_IGNORED_META_TAGS = frozenset(
    {
        "datasets",
        "dataset",
        "record",
        "colinfo",
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
        "httpfile",
        "filedialog",
        "file",
        "cylastinput",
        "persistdata",
        "_persistdata",
    }
)
_HIDDEN_IGNORED_TRACE_TAGS = frozenset(
    {
        "record",
        "colinfo",
        "col",
        "columns",
        "format",
        "head",
        "body",
        "summary",
        "cell",
        "cd",
        "data",
    }
)
_EVENT_ATTR_TO_REACT_PROP: dict[str, str] = {
    "onabort": "onAbort",
    "onanimationend": "onAnimationEnd",
    "onanimationiteration": "onAnimationIteration",
    "onanimationstart": "onAnimationStart",
    "onbeforeinput": "onBeforeInput",
    "onblur": "onBlur",
    "oncanplay": "onCanPlay",
    "oncanplaythrough": "onCanPlayThrough",
    "onchange": "onChange",
    "onchanged": "onChange",
    "onclick": "onClick",
    "oncompositionend": "onCompositionEnd",
    "oncompositionstart": "onCompositionStart",
    "oncompositionupdate": "onCompositionUpdate",
    "oncontextmenu": "onContextMenu",
    "oncopy": "onCopy",
    "oncut": "onCut",
    "ondblclick": "onDoubleClick",
    "ondrag": "onDrag",
    "ondragend": "onDragEnd",
    "ondragenter": "onDragEnter",
    "ondragexit": "onDragExit",
    "ondragleave": "onDragLeave",
    "ondragover": "onDragOver",
    "ondragstart": "onDragStart",
    "ondrop": "onDrop",
    "ondurationchange": "onDurationChange",
    "onemptied": "onEmptied",
    "onencrypted": "onEncrypted",
    "onended": "onEnded",
    "onerror": "onError",
    "onfocus": "onFocus",
    "ongotpointercapture": "onGotPointerCapture",
    "oninput": "onInput",
    "oninvalid": "onInvalid",
    "onkeydown": "onKeyDown",
    "onkeypress": "onKeyPress",
    "onkeyup": "onKeyUp",
    "onload": "onLoad",
    "onloadeddata": "onLoadedData",
    "onloadedmetadata": "onLoadedMetadata",
    "onloadstart": "onLoadStart",
    "onlostpointercapture": "onLostPointerCapture",
    "onmousedown": "onMouseDown",
    "onmouseenter": "onMouseEnter",
    "onmouseleave": "onMouseLeave",
    "onmousemove": "onMouseMove",
    "onmouseout": "onMouseOut",
    "onmouseover": "onMouseOver",
    "onmouseup": "onMouseUp",
    "onpaste": "onPaste",
    "onpause": "onPause",
    "onplay": "onPlay",
    "onplaying": "onPlaying",
    "onpointercancel": "onPointerCancel",
    "onpointerdown": "onPointerDown",
    "onpointerenter": "onPointerEnter",
    "onpointerleave": "onPointerLeave",
    "onpointermove": "onPointerMove",
    "onpointerout": "onPointerOut",
    "onpointerover": "onPointerOver",
    "onpointerup": "onPointerUp",
    "onprogress": "onProgress",
    "onratechange": "onRateChange",
    "onreset": "onReset",
    "onresize": "onResize",
    "onscroll": "onScroll",
    "onseeked": "onSeeked",
    "onseeking": "onSeeking",
    "onselect": "onSelect",
    "onstalled": "onStalled",
    "onsubmit": "onSubmit",
    "onsuspend": "onSuspend",
    "ontimeupdate": "onTimeUpdate",
    "ontoggle": "onToggle",
    "ontouchcancel": "onTouchCancel",
    "ontouchend": "onTouchEnd",
    "ontouchmove": "onTouchMove",
    "ontouchstart": "onTouchStart",
    "ontransitionend": "onTransitionEnd",
    "onvolumechange": "onVolumeChange",
    "onwaiting": "onWaiting",
    "onwheel": "onWheel",
}
UNSUPPORTED_EVENT_REASON_MISSING_BINDING = "missing_behavior_action_binding"
UNSUPPORTED_EVENT_REASON_MISSING_REACT_MAPPING = "missing_react_event_mapping"
_STYLE_DIMENSION_KEYS = frozenset(
    {
        "left",
        "top",
        "right",
        "bottom",
        "width",
        "height",
        "minWidth",
        "minHeight",
        "maxWidth",
        "maxHeight",
        "padding",
        "paddingLeft",
        "paddingTop",
        "paddingRight",
        "paddingBottom",
        "margin",
        "marginLeft",
        "marginTop",
        "marginRight",
        "marginBottom",
        "borderWidth",
        "borderRadius",
        "fontSize",
        "letterSpacing",
        "gap",
    }
)
_FALSE_ATTR_VALUES = frozenset({"false", "0", "off", "no", "n"})
_TRUE_ATTR_VALUES = frozenset({"true", "1", "on", "yes", "y"})
_VALID_TEXT_ALIGN_VALUES = frozenset(
    {
        "left",
        "right",
        "center",
        "justify",
        "start",
        "end",
        "match-parent",
    }
)
_TEXT_ALIGN_ALIASES = {
    "centre": "center",
    "middle": "center",
}
_RENDER_POLICY_MODES = frozenset({"strict", "mui", "auto"})
_AUTO_RENDER_POLICY_RISK_THRESHOLD = 0.58
_AUTO_RENDER_POLICY_RISK_THRESHOLD_ENV = "MIFL_UI_AUTO_RISK_THRESHOLD"
_SCRIPT_XML_FALLBACK_CODECS: tuple[str, ...] = (
    "utf-8-sig",
    "cp949",
    "euc-kr",
    "iso-8859-1",
)

UiRenderPolicyMode = Literal["strict", "mui", "auto"]
UiRenderMode = Literal["strict", "mui"]


@dataclass(slots=True)
class UiCodegenSummary:
    total_nodes: int
    rendered_nodes: int
    wired_event_bindings: int
    total_event_attributes: int = 0
    runtime_wired_event_props: int = 0
    unsupported_event_bindings: int = 0


@dataclass(slots=True)
class UnsupportedUiEventBinding:
    node_path: str
    node_tag: str
    event_name: str
    source_attr_name: str
    handler: str
    action_name: str | None
    reason: str
    warning: str
    source: SourceRef | None = None


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
    requested_mode: UiRenderPolicyMode
    mode: UiRenderMode
    decision_reason: str
    risk_score: float
    auto_risk_threshold: float
    risk_signal_counts: dict[str, int]
    risk_signal_scores: dict[str, float]
    unsupported_event_inventory: list[UnsupportedUiEventBinding] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    generated_at_utc: str = field(default_factory=lambda: datetime.now(UTC).isoformat())

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class _EventWiringStats:
    total_event_attributes: int = 0
    runtime_wired_event_props: int = 0


@dataclass(slots=True)
class _TabPageEntry:
    node_path: str
    label: str


@dataclass(slots=True)
class _TabBinding:
    node_path: str
    state_var: str
    set_state_var: str
    page_entries: list[_TabPageEntry] = field(default_factory=list)


@dataclass(slots=True)
class _GridHeaderCellSpec:
    row: int
    col: int
    row_span: int
    col_span: int
    label: str
    expr: str | None
    col_id: str | None
    display_type: str | None
    order: int


@dataclass(slots=True)
class _GridRenderLayout:
    column_widths: list[str]
    header_rows: list[list[_GridHeaderCellSpec]]
    body_rows: list[list[_GridHeaderCellSpec]]
    summary_rows: list[list[_GridHeaderCellSpec]]
    column_count: int


@dataclass(slots=True)
class _RuntimeVisibilityAssignment:
    node_path: str
    visible: bool


@dataclass(slots=True)
class _RuntimeVisibilityConditionalRule:
    match_source: Literal["selectedIndex", "value"]
    match_values: tuple[str, ...]
    true_assignments: tuple[_RuntimeVisibilityAssignment, ...]
    false_assignments: tuple[_RuntimeVisibilityAssignment, ...]


@dataclass(slots=True)
class _RuntimeVisibilityFunctionRule:
    unconditional_assignments: tuple[_RuntimeVisibilityAssignment, ...]
    conditional_rules: tuple[_RuntimeVisibilityConditionalRule, ...]


@dataclass(slots=True)
class _RuntimeVisibilityCodegenPlan:
    state_var: str
    set_state_var: str
    apply_patch_fn: str
    initial_state: dict[str, bool]
    target_node_paths: set[str]
    action_wrappers: dict[str, str]
    function_lines: list[str]


@dataclass(slots=True)
class _RenderRiskSignals:
    total_nodes: int = 0
    positioned_nodes: int = 0
    fallback_nodes: int = 0
    tab_nodes: int = 0
    event_attributes: int = 0


@dataclass(slots=True)
class _RenderPolicyDecision:
    requested_mode: UiRenderPolicyMode
    resolved_mode: UiRenderMode
    decision_reason: str
    risk_score: float
    auto_risk_threshold: float
    risk_signal_counts: dict[str, int]
    risk_signal_scores: dict[str, float]


def _attr_lookup(attrs: dict[str, str], key: str) -> str | None:
    if key in attrs:
        return attrs[key]
    key_lower = key.lower()
    for attr_key, value in attrs.items():
        if attr_key.lower() == key_lower:
            return value
    return None


def _normalize_xml_codec_name(raw: str) -> str:
    token = raw.strip().lower().replace("_", "-")
    if token == "utf8":
        return "utf-8"
    if token in {"x-windows-949", "windows-949", "ks-c-5601-1987", "ks-c-5601-1989"}:
        return "cp949"
    return token


def _read_xml_text_with_fallback(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return ""
    except UnicodeDecodeError:
        pass

    try:
        raw = path.read_bytes()
    except OSError:
        return ""

    candidates: list[str] = []
    declared_match = _XML_DECL_ENCODING_RE.search(raw[:512])
    if declared_match is not None:
        declared = declared_match.group(1).decode("ascii", errors="ignore").strip()
        if declared:
            candidates.append(_normalize_xml_codec_name(declared))
    candidates.extend(_SCRIPT_XML_FALLBACK_CODECS)

    seen: set[str] = set()
    for codec in candidates:
        normalized = _normalize_xml_codec_name(codec)
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        try:
            return raw.decode(normalized)
        except UnicodeDecodeError:
            continue
        except LookupError:
            continue

    return raw.decode("utf-8", errors="ignore")


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


def _normalized_style_value(raw: str | None, *, style_key: str) -> str | None:
    if raw is None:
        return None
    value = raw.strip()
    if not value:
        return None
    if style_key in _STYLE_DIMENSION_KEYS:
        return _normalize_dimension(value)
    if style_key == "textAlign":
        lowered = value.lower()
        normalized = _TEXT_ALIGN_ALIASES.get(lowered, lowered)
        if normalized in _VALID_TEXT_ALIGN_VALUES:
            return normalized
        return None
    return value


def _set_style_from_attr(
    style: dict[str, str],
    attrs: dict[str, str],
    *,
    style_key: str,
    attr_names: tuple[str, ...],
) -> None:
    for attr_name in attr_names:
        value = _normalized_style_value(_attr_lookup(attrs, attr_name), style_key=style_key)
        if value is not None:
            style[style_key] = value
            return


def _parse_numeric_attr(raw: str | None) -> float | None:
    if raw is None:
        return None
    value = raw.strip()
    if not value or not _NUMERIC_VALUE_RE.fullmatch(value):
        return None
    return float(value)


def _format_numeric_attr(value: float) -> str:
    if float(value).is_integer():
        return str(int(value))
    return f"{value:.4f}".rstrip("0").rstrip(".")


def _resolve_axis_style_from_legacy_attrs(
    attrs: dict[str, str],
    *,
    start_attr: str,
    end_attr: str,
    size_attr: str,
    start_style_key: str,
    end_style_key: str,
    size_style_key: str,
) -> dict[str, str]:
    start_raw = _attr_lookup(attrs, start_attr)
    end_raw = _attr_lookup(attrs, end_attr)
    size_raw = _attr_lookup(attrs, size_attr)
    start_num = _parse_numeric_attr(start_raw)
    end_num = _parse_numeric_attr(end_raw)
    size_num = _parse_numeric_attr(size_raw)

    output: dict[str, str] = {}
    coordinate_rewrite_applied = False

    if (
        start_num is not None
        and end_num is not None
        and size_num is not None
        and abs((end_num - start_num) - size_num) <= 0.5
    ):
        coordinate_rewrite_applied = True
        output[start_style_key] = _normalize_dimension(_format_numeric_attr(start_num)) or ""
        output[size_style_key] = _normalize_dimension(_format_numeric_attr(size_num)) or ""
    elif (
        start_num is None
        and end_num is not None
        and size_num is not None
        and end_num >= size_num
    ):
        coordinate_rewrite_applied = True
        inferred_start = end_num - size_num
        output[start_style_key] = _normalize_dimension(_format_numeric_attr(inferred_start)) or ""
        output[size_style_key] = _normalize_dimension(_format_numeric_attr(size_num)) or ""
    elif (
        size_num is None
        and start_num is not None
        and end_num is not None
        and end_num > start_num
    ):
        coordinate_rewrite_applied = True
        inferred_size = end_num - start_num
        output[start_style_key] = _normalize_dimension(_format_numeric_attr(start_num)) or ""
        output[size_style_key] = _normalize_dimension(_format_numeric_attr(inferred_size)) or ""

    if not coordinate_rewrite_applied:
        if start_raw is not None:
            normalized_start = _normalized_style_value(start_raw, style_key=start_style_key)
            if normalized_start is not None:
                output[start_style_key] = normalized_start
        if end_raw is not None:
            normalized_end = _normalized_style_value(end_raw, style_key=end_style_key)
            if normalized_end is not None:
                output[end_style_key] = normalized_end
        if size_raw is not None:
            normalized_size = _normalized_style_value(size_raw, style_key=size_style_key)
            if normalized_size is not None:
                output[size_style_key] = normalized_size

    return {key: value for key, value in output.items() if value}


def _apply_font_shorthand_style(style: dict[str, str], attrs: dict[str, str]) -> None:
    raw_font = _attr_lookup(attrs, "font")
    if raw_font is None:
        return
    tokens = [token.strip() for token in raw_font.split(",") if token.strip()]
    if not tokens:
        return
    if "fontFamily" not in style and tokens[0]:
        style["fontFamily"] = tokens[0]
    if "fontSize" not in style and len(tokens) > 1 and _NUMERIC_VALUE_RE.fullmatch(tokens[1]):
        style["fontSize"] = f"{tokens[1]}px"
    if len(tokens) > 2:
        font_flags = tokens[2].lower()
        if "bold" in font_flags and "fontWeight" not in style:
            style["fontWeight"] = "700"
        if "italic" in font_flags:
            style["fontStyle"] = "italic"


def _build_node_style(node: AstNode, *, is_root: bool, widget_kind: str) -> dict[str, str]:
    style: dict[str, str] = {}

    style.update(
        _resolve_axis_style_from_legacy_attrs(
            node.attributes,
            start_attr="left",
            end_attr="right",
            size_attr="width",
            start_style_key="left",
            end_style_key="right",
            size_style_key="width",
        )
    )
    style.update(
        _resolve_axis_style_from_legacy_attrs(
            node.attributes,
            start_attr="top",
            end_attr="bottom",
            size_attr="height",
            start_style_key="top",
            end_style_key="bottom",
            size_style_key="height",
        )
    )
    _set_style_from_attr(style, node.attributes, style_key="minWidth", attr_names=("minwidth",))
    _set_style_from_attr(style, node.attributes, style_key="minHeight", attr_names=("minheight",))
    _set_style_from_attr(style, node.attributes, style_key="maxWidth", attr_names=("maxwidth",))
    _set_style_from_attr(style, node.attributes, style_key="maxHeight", attr_names=("maxheight",))
    _set_style_from_attr(style, node.attributes, style_key="padding", attr_names=("padding",))
    _set_style_from_attr(
        style,
        node.attributes,
        style_key="paddingLeft",
        attr_names=("paddingleft", "padding-left"),
    )
    _set_style_from_attr(
        style,
        node.attributes,
        style_key="paddingTop",
        attr_names=("paddingtop", "padding-top"),
    )
    _set_style_from_attr(
        style,
        node.attributes,
        style_key="paddingRight",
        attr_names=("paddingright", "padding-right"),
    )
    _set_style_from_attr(
        style,
        node.attributes,
        style_key="paddingBottom",
        attr_names=("paddingbottom", "padding-bottom"),
    )
    _set_style_from_attr(style, node.attributes, style_key="margin", attr_names=("margin",))
    _set_style_from_attr(
        style,
        node.attributes,
        style_key="marginLeft",
        attr_names=("marginleft", "margin-left"),
    )
    _set_style_from_attr(
        style,
        node.attributes,
        style_key="marginTop",
        attr_names=("margintop", "margin-top"),
    )
    _set_style_from_attr(
        style,
        node.attributes,
        style_key="marginRight",
        attr_names=("marginright", "margin-right"),
    )
    _set_style_from_attr(
        style,
        node.attributes,
        style_key="marginBottom",
        attr_names=("marginbottom", "margin-bottom"),
    )
    _set_style_from_attr(
        style,
        node.attributes,
        style_key="background",
        attr_names=("background",),
    )
    _set_style_from_attr(
        style,
        node.attributes,
        style_key="backgroundColor",
        attr_names=("backgroundcolor", "backcolor"),
    )
    _set_style_from_attr(
        style,
        node.attributes,
        style_key="color",
        attr_names=("color", "textcolor", "forecolor"),
    )
    _set_style_from_attr(style, node.attributes, style_key="border", attr_names=("border",))
    _set_style_from_attr(
        style,
        node.attributes,
        style_key="borderColor",
        attr_names=("bordercolor",),
    )
    _set_style_from_attr(
        style,
        node.attributes,
        style_key="borderStyle",
        attr_names=("borderstyle",),
    )
    _set_style_from_attr(
        style,
        node.attributes,
        style_key="borderWidth",
        attr_names=("borderwidth",),
    )
    _set_style_from_attr(
        style,
        node.attributes,
        style_key="borderRadius",
        attr_names=("borderradius", "radius"),
    )
    _set_style_from_attr(
        style,
        node.attributes,
        style_key="fontFamily",
        attr_names=("fontfamily",),
    )
    _set_style_from_attr(
        style,
        node.attributes,
        style_key="fontSize",
        attr_names=("fontsize",),
    )
    _set_style_from_attr(
        style,
        node.attributes,
        style_key="fontWeight",
        attr_names=("fontweight",),
    )
    _apply_font_shorthand_style(style, node.attributes)
    _set_style_from_attr(
        style,
        node.attributes,
        style_key="letterSpacing",
        attr_names=("letterspacing",),
    )
    _set_style_from_attr(
        style,
        node.attributes,
        style_key="textAlign",
        attr_names=("textalign", "align"),
    )
    _set_style_from_attr(
        style,
        node.attributes,
        style_key="whiteSpace",
        attr_names=("whitespace",),
    )
    _set_style_from_attr(style, node.attributes, style_key="overflow", attr_names=("overflow",))
    _set_style_from_attr(style, node.attributes, style_key="opacity", attr_names=("opacity",))
    _set_style_from_attr(style, node.attributes, style_key="zIndex", attr_names=("zindex",))
    _set_style_from_attr(style, node.attributes, style_key="display", attr_names=("display",))
    _set_style_from_attr(style, node.attributes, style_key="gap", attr_names=("gap",))

    positioned = any(key in style for key in ("left", "top", "right", "bottom"))
    if positioned:
        style["position"] = "absolute"
    elif is_root or widget_kind == "container":
        style["position"] = "relative"

    visible = _normalize_boolean(
        _attr_lookup(node.attributes, "visible") or _attr_lookup(node.attributes, "isvisible")
    )
    if visible is False:
        style["display"] = "none"

    enabled = _normalize_boolean(
        _attr_lookup(node.attributes, "enable")
        or _attr_lookup(node.attributes, "enabled")
        or _attr_lookup(node.attributes, "isenabled")
    )
    if enabled is False:
        style["pointerEvents"] = "none"

    if widget_kind == "ignored" and not _should_render_ignored_trace(node):
        style["display"] = "none"

    if widget_kind == "static":
        style.setdefault("lineHeight", "1")
        style.setdefault("overflow", "hidden")
        style.setdefault("whiteSpace", "pre")

    return style


def _style_attribute(style: dict[str, str]) -> str:
    if not style:
        return ""
    payload = {key: style[key] for key in sorted(style)}
    style_json = json.dumps(payload, ensure_ascii=False)
    return f" style={{{style_json}}}"


def _style_attribute_with_runtime_visibility(
    style: dict[str, str],
    *,
    node_path: str,
    visibility_state_var: str,
) -> str:
    payload = {key: style[key] for key in sorted(style) if key != "display"}
    payload_json = json.dumps(payload, ensure_ascii=False)
    node_path_literal = json.dumps(node_path, ensure_ascii=False)
    return (
        " style={{ "
        f"...{payload_json}, "
        f"...({visibility_state_var}[{node_path_literal}] === false ? {{\"display\": \"none\"}} : {{}}) "
        "}}"
    )


def _widget_content_style(widget_kind: str) -> dict[str, str]:
    if widget_kind == "container":
        return {}
    return {
        "height": "100%",
        "width": "100%",
    }


def _node_attrs_label(node: AstNode) -> str | None:
    if not node.attributes:
        return None
    parts = [
        f"{key}={value}"
        for key, value in sorted(node.attributes.items(), key=lambda item: item[0].lower())
    ]
    return ", ".join(parts)


def _ignored_trace_label(node: AstNode) -> str:
    attrs_label = _node_attrs_label(node)
    node_text = node.text.strip() if node.text and node.text.strip() else None
    if attrs_label is not None and node_text is not None:
        return f"{node.tag}: {node_text} ({attrs_label})"
    if attrs_label is not None:
        return f"{node.tag}: {attrs_label}"
    if node_text is not None:
        return f"{node.tag}: {node_text}"
    return node.tag


def _should_render_ignored_trace(node: AstNode) -> bool:
    return node.tag.lower() not in _HIDDEN_IGNORED_TRACE_TAGS


def _widget_kind(tag: str) -> str:
    tag_lower = tag.lower()
    if tag_lower in _CONTAINER_TAGS:
        return "container"
    widget_kind = _WIDGET_TAG_ALIASES.get(tag_lower)
    if widget_kind is not None:
        return widget_kind
    if tag_lower in _IGNORED_META_TAGS:
        return "ignored"
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


def _iter_descendants(node: AstNode) -> list[AstNode]:
    descendants: list[AstNode] = []
    for child in node.children:
        descendants.append(child)
        descendants.extend(_iter_descendants(child))
    return descendants


def _dedupe_nonempty(values: list[str]) -> list[str]:
    output: list[str] = []
    seen: set[str] = set()
    for raw in values:
        candidate = raw.strip()
        if not candidate:
            continue
        if candidate in seen:
            continue
        seen.add(candidate)
        output.append(candidate)
    return output


def _grid_head_cell_labels(node: AstNode) -> list[str]:
    labels: list[str] = []

    def walk(current: AstNode, *, in_head: bool) -> None:
        tag_lower = current.tag.lower()
        next_in_head = in_head or tag_lower == "head"
        if tag_lower == "cell" and next_in_head:
            text = _attr_lookup(current.attributes, "text")
            if text is None and current.text is not None and current.text.strip():
                text = current.text.strip()
            if text is None:
                text = _attr_lookup(current.attributes, "id")
            if text is not None and text.strip():
                labels.append(text.strip())
        for child in current.children:
            walk(child, in_head=next_in_head)

    walk(node, in_head=False)
    return _dedupe_nonempty(labels)


def _grid_col_labels(node: AstNode) -> list[str]:
    labels: list[str] = []
    for descendant in _iter_descendants(node):
        if descendant.tag.lower() != "col":
            continue
        for attr_name in ("id", "name", "colid", "text"):
            value = _attr_lookup(descendant.attributes, attr_name)
            if value is not None and value.strip():
                labels.append(value.strip())
                break
    return _dedupe_nonempty(labels)


def _grid_column_labels(node: AstNode, *, fallback: str) -> list[str]:
    head_labels = _grid_head_cell_labels(node)
    if head_labels:
        return head_labels
    col_labels = _grid_col_labels(node)
    if col_labels:
        return col_labels
    return [fallback]


def _parse_int_attr(raw: str | None, *, default: int = 0, minimum: int | None = None) -> int:
    numeric = _parse_numeric_attr(raw)
    if numeric is None:
        value = default
    else:
        value = int(numeric)
    if minimum is not None:
        value = max(minimum, value)
    return value


def _extract_handler_identifier(handler: str | None) -> str | None:
    if handler is None:
        return None
    match = _HANDLER_IDENTIFIER.search(handler.strip())
    if not match:
        return None
    return match.group(0).split(".")[-1]


def _grid_column_widths(node: AstNode) -> list[str]:
    widths: list[str] = []
    for descendant in _iter_descendants(node):
        if descendant.tag.lower() != "col":
            continue
        normalized = _normalize_dimension(_attr_lookup(descendant.attributes, "width"))
        widths.append(normalized or "auto")
    return widths


def _parse_dimension_number(raw: str | None) -> float | None:
    if raw is None:
        return None
    token = raw.strip().lower()
    if not token:
        return None
    if token.endswith("px"):
        token = token[:-2].strip()
    if not token or not _NUMERIC_VALUE_RE.fullmatch(token):
        return None
    return float(token)


def _is_hidden_grid_column_width(width: str) -> bool:
    numeric = _parse_dimension_number(width)
    if numeric is None:
        return False
    return numeric <= 0


def _visible_grid_column_indices(column_widths: list[str]) -> list[int]:
    if not column_widths:
        return []
    visible_indices = [
        index for index, width in enumerate(column_widths) if not _is_hidden_grid_column_width(width)
    ]
    if visible_indices:
        return visible_indices
    return list(range(len(column_widths)))


def _filter_grid_column_labels(labels: list[str], visible_indices: list[int]) -> list[str]:
    if not labels or not visible_indices:
        return labels
    if max(visible_indices, default=-1) >= len(labels):
        return labels
    filtered = [labels[index] for index in visible_indices if 0 <= index < len(labels)]
    return filtered or labels


def _filter_grid_band_rows_for_visible_columns(
    band_rows: list[list[_GridHeaderCellSpec]],
    *,
    visible_indices: list[int],
) -> list[list[_GridHeaderCellSpec]]:
    if not band_rows or not visible_indices:
        return band_rows

    position_by_original_col = {original_col: index for index, original_col in enumerate(visible_indices)}
    filtered_rows: list[list[_GridHeaderCellSpec]] = []
    for row in band_rows:
        filtered_cells: list[_GridHeaderCellSpec] = []
        for cell in row:
            col_start = max(0, cell.col)
            col_end = col_start + max(1, cell.col_span)
            mapped_positions: list[int] = []
            for original_col in range(col_start, col_end):
                mapped = position_by_original_col.get(original_col)
                if mapped is not None:
                    mapped_positions.append(mapped)
            if not mapped_positions:
                continue
            filtered_cells.append(
                _GridHeaderCellSpec(
                    row=cell.row,
                    col=min(mapped_positions),
                    row_span=cell.row_span,
                    col_span=max(1, len(mapped_positions)),
                    label=cell.label,
                    expr=cell.expr,
                    col_id=cell.col_id,
                    display_type=cell.display_type,
                    order=cell.order,
                )
            )
        filtered_cells.sort(key=lambda item: (item.col, item.order))
        filtered_rows.append(filtered_cells)
    return filtered_rows


def _scale_grid_column_widths_for_autofit(
    column_widths: list[str],
    *,
    container_width_attr: str | None,
    auto_fit_attr: str | None,
) -> list[str]:
    if not column_widths:
        return column_widths
    if not _normalize_boolean(auto_fit_attr):
        return column_widths
    container_width = _parse_dimension_number(container_width_attr)
    if container_width is None or container_width <= 0:
        return column_widths

    numeric_widths = [_parse_dimension_number(width) for width in column_widths]
    known_total_width = sum(width for width in numeric_widths if width is not None)
    if known_total_width <= 0 or known_total_width <= container_width + 0.5:
        return column_widths

    scale = container_width / known_total_width
    scaled_widths: list[str] = []
    for original_width, numeric_width in zip(column_widths, numeric_widths):
        if numeric_width is None:
            scaled_widths.append(original_width)
            continue
        scaled = max(1.0, round(numeric_width * scale, 2))
        normalized = _normalize_dimension(_format_numeric_attr(scaled))
        scaled_widths.append(normalized or original_width)
    return scaled_widths


def _grid_render_layout(node: AstNode, *, fallback_header: str) -> _GridRenderLayout:
    column_labels = _grid_column_labels(node, fallback=fallback_header)
    column_widths = _grid_column_widths(node)
    header_rows = _grid_header_rows(node, fallback_header=fallback_header)
    body_rows = _grid_body_rows(node)
    summary_rows = _grid_summary_rows(node)

    if column_widths:
        visible_indices = _visible_grid_column_indices(column_widths)
        if len(visible_indices) != len(column_widths):
            column_widths = [column_widths[index] for index in visible_indices]
            column_labels = _filter_grid_column_labels(column_labels, visible_indices)
            header_rows = _filter_grid_band_rows_for_visible_columns(
                header_rows,
                visible_indices=visible_indices,
            )
            body_rows = _filter_grid_band_rows_for_visible_columns(
                body_rows,
                visible_indices=visible_indices,
            )
            summary_rows = _filter_grid_band_rows_for_visible_columns(
                summary_rows,
                visible_indices=visible_indices,
            )

        column_widths = _scale_grid_column_widths_for_autofit(
            column_widths,
            container_width_attr=_attr_lookup(node.attributes, "width"),
            auto_fit_attr=_attr_lookup(node.attributes, "autofit"),
        )

    column_count = _grid_column_count(
        column_widths=column_widths,
        band_rows=[*header_rows, *body_rows, *summary_rows],
        fallback_labels=column_labels,
    )
    return _GridRenderLayout(
        column_widths=column_widths,
        header_rows=header_rows,
        body_rows=body_rows,
        summary_rows=summary_rows,
        column_count=column_count,
    )


def _grid_head_cell_specs(node: AstNode) -> list[_GridHeaderCellSpec]:
    return _grid_band_cell_specs(node, band_tag="head")


def _grid_cell_label(cell: AstNode) -> str:
    label = _node_display_text(cell, fallback="")
    if label.strip():
        return label
    for attr_name in ("text", "id"):
        raw = _attr_lookup(cell.attributes, attr_name)
        if raw is not None and raw.strip():
            return raw.strip()
    return ""


def _grid_band_cell_specs(node: AstNode, *, band_tag: str) -> list[_GridHeaderCellSpec]:
    specs: list[_GridHeaderCellSpec] = []
    order = 0
    normalized_band_tag = band_tag.strip().lower()

    def walk(current: AstNode, *, in_head: bool) -> None:
        nonlocal order
        tag_lower = current.tag.lower()
        next_in_head = in_head or tag_lower == normalized_band_tag
        if tag_lower == "cell" and next_in_head:
            label = _grid_cell_label(current)
            specs.append(
                _GridHeaderCellSpec(
                    row=_parse_int_attr(_attr_lookup(current.attributes, "row"), default=0, minimum=0),
                    col=_parse_int_attr(_attr_lookup(current.attributes, "col"), default=order, minimum=0),
                    row_span=_parse_int_attr(
                        _attr_lookup(current.attributes, "rowspan"), default=1, minimum=1
                    ),
                    col_span=_parse_int_attr(
                        _attr_lookup(current.attributes, "colspan"), default=1, minimum=1
                    ),
                    label=label,
                    expr=_attr_lookup(current.attributes, "expr"),
                    col_id=_attr_lookup(current.attributes, "colid"),
                    display_type=_attr_lookup(current.attributes, "displaytype"),
                    order=order,
                )
            )
            order += 1
        for child in current.children:
            walk(child, in_head=next_in_head)

    walk(node, in_head=False)
    specs.sort(key=lambda item: (item.row, item.col, item.order))
    return specs


def _grid_band_rows(
    band_specs: list[_GridHeaderCellSpec],
) -> list[list[_GridHeaderCellSpec]]:
    if not band_specs:
        return []
    grouped: dict[int, list[_GridHeaderCellSpec]] = {}
    max_row_index = 0
    for spec in band_specs:
        grouped.setdefault(spec.row, []).append(spec)
        max_row_index = max(max_row_index, spec.row + max(1, spec.row_span) - 1)

    dense_rows: list[list[_GridHeaderCellSpec]] = []
    for row_index in range(max_row_index + 1):
        row_cells = grouped.get(row_index, [])
        row_cells.sort(key=lambda item: (item.col, item.order))
        dense_rows.append(row_cells)
    return dense_rows


def _grid_header_rows(
    node: AstNode,
    *,
    fallback_header: str,
) -> list[list[_GridHeaderCellSpec]]:
    head_specs = _grid_head_cell_specs(node)
    if not head_specs:
        return [
            [
                _GridHeaderCellSpec(
                    row=0,
                    col=0,
                    row_span=1,
                    col_span=1,
                    label=fallback_header,
                    expr=None,
                    col_id=None,
                    display_type=None,
                    order=0,
                )
            ]
        ]
    return _grid_band_rows(head_specs)


def _grid_body_rows(node: AstNode) -> list[list[_GridHeaderCellSpec]]:
    return _grid_band_rows(_grid_band_cell_specs(node, band_tag="body"))


def _grid_summary_rows(node: AstNode) -> list[list[_GridHeaderCellSpec]]:
    return _grid_band_rows(_grid_band_cell_specs(node, band_tag="summary"))


def _screen_has_grid_summary_band(root: AstNode) -> bool:
    for descendant in _iter_descendants(root):
        if descendant.tag.lower() != "grid":
            continue
        if _grid_summary_rows(descendant):
            return True
    return False


def _grid_column_count(
    *,
    column_widths: list[str],
    band_rows: list[list[_GridHeaderCellSpec]],
    fallback_labels: list[str],
) -> int:
    if column_widths:
        return len(column_widths)
    max_col_index = 0
    for row in band_rows:
        for cell in row:
            max_col_index = max(max_col_index, cell.col + cell.col_span)
    if max_col_index > 0:
        return max_col_index
    return max(1, len(fallback_labels))


_GRID_PREVIEW_ROW_LIMIT = 50


@dataclass(slots=True)
class _GridExprToken:
    kind: str
    value: str


class _GridExprEvaluationError(ValueError):
    pass


def _grid_value_to_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, float):
        if value.is_integer():
            return str(int(value))
        return f"{value:.4f}".rstrip("0").rstrip(".")
    return str(value)


def _coerce_grid_number(value: Any) -> float | None:
    if isinstance(value, (int, float)):
        return float(value)
    if value is None:
        return None
    candidate = str(value).strip().replace(",", "")
    if not candidate:
        return None
    if _NUMERIC_VALUE_RE.fullmatch(candidate):
        return float(candidate)
    return None


def _grid_plus(left: Any, right: Any) -> Any:
    left_num = _coerce_grid_number(left)
    right_num = _coerce_grid_number(right)
    if left_num is not None and right_num is not None:
        return left_num + right_num
    return f"{_grid_value_to_text(left)}{_grid_value_to_text(right)}"


def _grid_minus(left: Any, right: Any) -> float:
    left_num = _coerce_grid_number(left) or 0.0
    right_num = _coerce_grid_number(right) or 0.0
    return left_num - right_num


def _grid_multiply(left: Any, right: Any) -> float:
    left_num = _coerce_grid_number(left) or 0.0
    right_num = _coerce_grid_number(right) or 0.0
    return left_num * right_num


def _grid_divide(left: Any, right: Any) -> float:
    left_num = _coerce_grid_number(left) or 0.0
    right_num = _coerce_grid_number(right) or 0.0
    if right_num == 0:
        return 0.0
    return left_num / right_num


def _grid_equals(left: Any, right: Any) -> bool:
    left_num = _coerce_grid_number(left)
    right_num = _coerce_grid_number(right)
    if left_num is not None and right_num is not None:
        return abs(left_num - right_num) <= 1e-9
    return _grid_value_to_text(left) == _grid_value_to_text(right)


def _grid_compare(left: Any, right: Any) -> tuple[float | None, str, str]:
    left_num = _coerce_grid_number(left)
    right_num = _coerce_grid_number(right)
    if left_num is not None and right_num is not None:
        return left_num - right_num, "", ""
    left_text = _grid_value_to_text(left)
    right_text = _grid_value_to_text(right)
    if left_text < right_text:
        return -1.0, left_text, right_text
    if left_text > right_text:
        return 1.0, left_text, right_text
    return 0.0, left_text, right_text


def _grid_truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    numeric = _coerce_grid_number(value)
    if numeric is not None:
        return numeric != 0.0
    lowered = _grid_value_to_text(value).strip().lower()
    return lowered not in {"", "false", "null", "none", "nan"}


def _lookup_grid_row_value(
    row: dict[str, str] | None,
    column_id: str,
) -> str:
    if row is None:
        return ""
    if column_id in row:
        return row[column_id]
    normalized_target = column_id.strip().lower()
    for key, value in row.items():
        if key.strip().lower() == normalized_target:
            return value
    return ""


def _sum_grid_dataset_column(
    dataset_rows: list[dict[str, str]],
    column_id: str,
) -> float:
    total = 0.0
    for row in dataset_rows:
        numeric = _coerce_grid_number(_lookup_grid_row_value(row, column_id))
        if numeric is not None:
            total += numeric
    return total


def _count_grid_dataset_column(
    dataset_rows: list[dict[str, str]],
    column_id: str,
) -> int:
    if not column_id:
        return len(dataset_rows)
    count = 0
    for row in dataset_rows:
        if _lookup_grid_row_value(row, column_id).strip():
            count += 1
    return count


def _avg_grid_dataset_column(
    dataset_rows: list[dict[str, str]],
    column_id: str,
) -> float:
    if not column_id:
        return 0.0
    total = 0.0
    count = 0
    for row in dataset_rows:
        numeric = _coerce_grid_number(_lookup_grid_row_value(row, column_id))
        if numeric is None:
            continue
        total += numeric
        count += 1
    if count == 0:
        return 0.0
    return total / float(count)


def _grid_substr(value: Any, start: Any, length: Any | None = None) -> str:
    text = _grid_value_to_text(value)
    start_num = int(_coerce_grid_number(start) or 0)
    if start_num < 0:
        start_num = max(0, len(text) + start_num)
    if length is None:
        return text[start_num:]
    length_num = int(_coerce_grid_number(length) or 0)
    if length_num <= 0:
        return ""
    return text[start_num : start_num + length_num]


def _tokenize_grid_expr(expr: str) -> list[_GridExprToken]:
    output: list[_GridExprToken] = []
    index = 0
    length = len(expr)

    while index < length:
        ch = expr[index]
        if ch.isspace():
            index += 1
            continue
        next_two = expr[index : index + 2]
        if next_two in {"==", "!=", "<=", ">=", "&&", "||"}:
            kind_map = {
                "==": "EQ",
                "!=": "NE",
                "<=": "LE",
                ">=": "GE",
                "&&": "AND",
                "||": "OR",
            }
            output.append(_GridExprToken(kind=kind_map[next_two], value=next_two))
            index += 2
            continue
        if ch in "<>!":
            kind_map = {
                "<": "LT",
                ">": "GT",
                "!": "NOT",
            }
            output.append(_GridExprToken(kind=kind_map[ch], value=ch))
            index += 1
            continue
        if ch in "+-*/(),":
            kind_map = {
                "+": "PLUS",
                "-": "MINUS",
                "*": "STAR",
                "/": "SLASH",
                "(": "LPAREN",
                ")": "RPAREN",
                ",": "COMMA",
            }
            output.append(_GridExprToken(kind=kind_map[ch], value=ch))
            index += 1
            continue
        if ch == "'" or ch == '"':
            quote = ch
            cursor = index + 1
            escaped = False
            literal_chars: list[str] = []
            while cursor < length:
                current = expr[cursor]
                if escaped:
                    escape_map = {"n": "\n", "r": "\r", "t": "\t", "\\": "\\", "'": "'", '"': '"'}
                    literal_chars.append(escape_map.get(current, current))
                    escaped = False
                    cursor += 1
                    continue
                if current == "\\":
                    escaped = True
                    cursor += 1
                    continue
                if current == quote:
                    break
                literal_chars.append(current)
                cursor += 1
            if cursor >= length or expr[cursor] != quote:
                raise _GridExprEvaluationError("Unterminated string literal in grid expression.")
            output.append(_GridExprToken(kind="STRING", value="".join(literal_chars)))
            index = cursor + 1
            continue
        if ch.isdigit() or (ch == "." and index + 1 < length and expr[index + 1].isdigit()):
            cursor = index
            saw_dot = False
            while cursor < length:
                current = expr[cursor]
                if current.isdigit():
                    cursor += 1
                    continue
                if current == "." and not saw_dot:
                    saw_dot = True
                    cursor += 1
                    continue
                break
            output.append(_GridExprToken(kind="NUMBER", value=expr[index:cursor]))
            index = cursor
            continue
        if ch.isalpha() or ch == "_":
            cursor = index + 1
            while cursor < length and (expr[cursor].isalnum() or expr[cursor] == "_"):
                cursor += 1
            output.append(_GridExprToken(kind="IDENT", value=expr[index:cursor]))
            index = cursor
            continue
        raise _GridExprEvaluationError(
            f"Unsupported token '{ch}' in grid expression: {expr!r}"
        )

    output.append(_GridExprToken(kind="EOF", value=""))
    return output


class _GridExprParser:
    def __init__(
        self,
        *,
        tokens: list[_GridExprToken],
        row: dict[str, str] | None,
        dataset_rows: list[dict[str, str]],
        row_index: int | None,
    ) -> None:
        self._tokens = tokens
        self._index = 0
        self._row = row
        self._dataset_rows = dataset_rows
        self._row_index = row_index

    def parse(self) -> Any:
        value = self._parse_expression()
        self._expect("EOF")
        return value

    def _current(self) -> _GridExprToken:
        return self._tokens[self._index]

    def _advance(self) -> _GridExprToken:
        current = self._current()
        self._index += 1
        return current

    def _match(self, kind: str) -> bool:
        if self._current().kind != kind:
            return False
        self._advance()
        return True

    def _expect(self, kind: str) -> _GridExprToken:
        token = self._current()
        if token.kind != kind:
            raise _GridExprEvaluationError(
                f"Expected token '{kind}', got '{token.kind}'."
            )
        return self._advance()

    def _parse_expression(self) -> Any:
        return self._parse_or()

    def _parse_or(self) -> Any:
        value = self._parse_and()
        while self._match("OR"):
            value = _grid_truthy(value) or _grid_truthy(self._parse_and())
        return value

    def _parse_and(self) -> Any:
        value = self._parse_equality()
        while self._match("AND"):
            value = _grid_truthy(value) and _grid_truthy(self._parse_equality())
        return value

    def _parse_equality(self) -> Any:
        value = self._parse_comparison()
        while True:
            if self._match("EQ"):
                value = _grid_equals(value, self._parse_comparison())
                continue
            if self._match("NE"):
                value = not _grid_equals(value, self._parse_comparison())
                continue
            return value

    def _parse_comparison(self) -> Any:
        value = self._parse_term()
        while True:
            if self._match("LT"):
                compared, _, _ = _grid_compare(value, self._parse_term())
                value = compared < 0
                continue
            if self._match("LE"):
                compared, _, _ = _grid_compare(value, self._parse_term())
                value = compared <= 0
                continue
            if self._match("GT"):
                compared, _, _ = _grid_compare(value, self._parse_term())
                value = compared > 0
                continue
            if self._match("GE"):
                compared, _, _ = _grid_compare(value, self._parse_term())
                value = compared >= 0
                continue
            return value

    def _parse_term(self) -> Any:
        value = self._parse_factor()
        while True:
            if self._match("PLUS"):
                value = _grid_plus(value, self._parse_factor())
                continue
            if self._match("MINUS"):
                value = _grid_minus(value, self._parse_factor())
                continue
            return value

    def _parse_factor(self) -> Any:
        value = self._parse_unary()
        while True:
            if self._match("STAR"):
                value = _grid_multiply(value, self._parse_unary())
                continue
            if self._match("SLASH"):
                value = _grid_divide(value, self._parse_unary())
                continue
            return value

    def _parse_unary(self) -> Any:
        if self._match("PLUS"):
            return self._parse_unary()
        if self._match("MINUS"):
            return -(_coerce_grid_number(self._parse_unary()) or 0.0)
        if self._match("NOT"):
            return not _grid_truthy(self._parse_unary())
        return self._parse_primary()

    def _parse_primary(self) -> Any:
        current = self._current()
        if self._match("NUMBER"):
            return float(current.value)
        if self._match("STRING"):
            return current.value
        if self._match("IDENT"):
            identifier = current.value
            if self._match("LPAREN"):
                return self._parse_function_call(identifier)
            normalized = identifier.strip().lower()
            if normalized == "null":
                return None
            if normalized == "true":
                return True
            if normalized == "false":
                return False
            if normalized in {"row", "currow"}:
                return float(self._row_index or 0)
            return _lookup_grid_row_value(self._row, identifier)
        if self._match("LPAREN"):
            nested = self._parse_expression()
            self._expect("RPAREN")
            return nested
        raise _GridExprEvaluationError(
            f"Unexpected token '{current.kind}' in grid expression."
        )

    def _parse_function_call(self, function_name: str) -> Any:
        args: list[Any] = []
        if self._current().kind != "RPAREN":
            while True:
                args.append(self._parse_expression())
                if not self._match("COMMA"):
                    break
        self._expect("RPAREN")

        fn = function_name.strip().lower()
        if fn == "sum":
            if not args:
                return 0.0
            column_id = _grid_value_to_text(args[0]).strip()
            if not column_id:
                return 0.0
            return _sum_grid_dataset_column(self._dataset_rows, column_id)
        if fn == "count":
            if not args:
                return len(self._dataset_rows)
            column_id = _grid_value_to_text(args[0]).strip()
            return _count_grid_dataset_column(self._dataset_rows, column_id)
        if fn == "avg":
            if not args:
                return 0.0
            column_id = _grid_value_to_text(args[0]).strip()
            return _avg_grid_dataset_column(self._dataset_rows, column_id)
        if fn == "rowcount":
            return len(self._dataset_rows)
        if fn == "substr":
            if len(args) < 2:
                raise _GridExprEvaluationError("substr() requires at least 2 arguments.")
            length = args[2] if len(args) > 2 else None
            return _grid_substr(args[0], args[1], length)
        if fn == "decode":
            if not args:
                return ""
            target = args[0]
            remainder = args[1:]
            if not remainder:
                return ""
            fallback = ""
            if len(remainder) % 2 == 1:
                fallback = remainder[-1]
                remainder = remainder[:-1]
            for index in range(0, len(remainder), 2):
                if _grid_equals(target, remainder[index]):
                    return remainder[index + 1]
            return fallback
        if fn == "iif":
            if len(args) < 2:
                return ""
            condition = args[0]
            if _grid_truthy(condition):
                return args[1]
            return args[2] if len(args) > 2 else ""
        if fn == "to_number" or fn == "tonumber" or fn == "number":
            if not args:
                return 0.0
            return _coerce_grid_number(args[0]) or 0.0
        if fn == "int":
            if not args:
                return 0
            return int(_coerce_grid_number(args[0]) or 0.0)
        if fn == "ceil":
            if not args:
                return 0
            value = _coerce_grid_number(args[0]) or 0.0
            return int(-(-value // 1))
        if fn == "floor":
            if not args:
                return 0
            value = _coerce_grid_number(args[0]) or 0.0
            return int(value // 1)
        if fn == "trim":
            if not args:
                return ""
            return _grid_value_to_text(args[0]).strip()
        if fn == "len" or fn == "length":
            if not args:
                return 0
            return len(_grid_value_to_text(args[0]))
        if fn == "upper":
            if not args:
                return ""
            return _grid_value_to_text(args[0]).upper()
        if fn == "lower":
            if not args:
                return ""
            return _grid_value_to_text(args[0]).lower()
        if fn == "replace":
            if not args:
                return ""
            text = _grid_value_to_text(args[0])
            old = _grid_value_to_text(args[1]) if len(args) > 1 else ""
            new = _grid_value_to_text(args[2]) if len(args) > 2 else ""
            if not old:
                return text
            return text.replace(old, new)
        if fn == "getrowtype":
            if self._row is None:
                return "normal"
            for key in ("_rowtype", "rowtype", "ROWTYPE", "__rowtype__"):
                if key in self._row and self._row[key].strip():
                    return self._row[key]
            return "normal"
        if fn == "nvl":
            if not args:
                return ""
            primary = args[0]
            if _grid_value_to_text(primary):
                return primary
            return args[1] if len(args) > 1 else ""
        if fn == "round":
            if not args:
                return 0.0
            number = _coerce_grid_number(args[0]) or 0.0
            precision = int(_coerce_grid_number(args[1]) or 0) if len(args) > 1 else 0
            return round(number, precision)
        if fn == "abs":
            if not args:
                return 0.0
            return abs(_coerce_grid_number(args[0]) or 0.0)

        raise _GridExprEvaluationError(
            f"Unsupported function '{function_name}' in grid expression."
        )


def _evaluate_grid_expression(
    expr: str,
    *,
    row: dict[str, str] | None,
    dataset_rows: list[dict[str, str]],
    row_index: int | None,
) -> Any:
    parser = _GridExprParser(
        tokens=_tokenize_grid_expr(expr),
        row=row,
        dataset_rows=dataset_rows,
        row_index=row_index,
    )
    return parser.parse()


def _resolve_grid_cell_text(
    cell: _GridHeaderCellSpec,
    *,
    row: dict[str, str] | None,
    dataset_rows: list[dict[str, str]],
    row_index: int | None,
) -> str:
    if cell.label.strip():
        return cell.label
    if cell.expr is not None and cell.expr.strip():
        try:
            return _grid_value_to_text(
                _evaluate_grid_expression(
                    cell.expr.strip(),
                    row=row,
                    dataset_rows=dataset_rows,
                    row_index=row_index,
                )
            )
        except _GridExprEvaluationError:
            return ""
    if cell.col_id is not None and cell.col_id.strip():
        return _grid_value_to_text(_lookup_grid_row_value(row, cell.col_id.strip()))
    return ""


def _normalize_dataset_binding_token(raw: str | None) -> str | None:
    if raw is None:
        return None
    token = raw.strip()
    if not token:
        return None
    if token.startswith("@"):
        token = token[1:]
    if ":" in token:
        maybe_prefix, maybe_name = token.split(":", 1)
        if maybe_prefix.strip().lower() in {"dataset", "ds"} and maybe_name.strip():
            token = maybe_name.strip()
    return token or None


def _build_dataset_record_lookup(screen: ScreenIR) -> dict[str, list[dict[str, str]]]:
    lookup: dict[str, list[dict[str, str]]] = {}
    for dataset in screen.datasets:
        dataset_id = _normalize_dataset_binding_token(dataset.dataset_id)
        if dataset_id is None:
            continue
        key = dataset_id.lower()
        if key in lookup:
            continue
        records: list[dict[str, str]] = []
        for record in dataset.records:
            records.append(dict(record.values))
        lookup[key] = records
    return lookup


def _resolve_grid_dataset_rows(
    node: AstNode,
    *,
    dataset_record_lookup: dict[str, list[dict[str, str]]],
) -> list[dict[str, str]]:
    dataset_binding = _normalize_dataset_binding_token(
        _attr_lookup(node.attributes, "binddataset") or _attr_lookup(node.attributes, "dataset")
    )
    if dataset_binding is None:
        return []
    return dataset_record_lookup.get(dataset_binding.lower(), [])


def _add_unique_lookup_entry(
    lookup: dict[str, str | None],
    *,
    key: str,
    value: str,
) -> None:
    normalized_key = key.strip().lower()
    if not normalized_key:
        return
    if normalized_key not in lookup:
        lookup[normalized_key] = value
        return
    if lookup[normalized_key] != value:
        lookup[normalized_key] = None


def _build_visibility_target_lookup(root: AstNode) -> dict[str, str | None]:
    lookup: dict[str, str | None] = {}

    def walk(node: AstNode, id_chain: list[str]) -> None:
        node_id = _attr_lookup(node.attributes, "id")
        next_chain = id_chain
        if node_id is not None and node_id.strip():
            node_id_token = node_id.strip()
            next_chain = [*id_chain, node_id_token]
            _add_unique_lookup_entry(lookup, key=node_id_token, value=node.source.node_path)
            for offset in range(len(next_chain)):
                chain_key = ".".join(next_chain[offset:])
                _add_unique_lookup_entry(lookup, key=chain_key, value=node.source.node_path)

        for child in node.children:
            walk(child, next_chain)

    walk(root, [])
    return lookup


def _resolve_visibility_target_node_path(
    raw_target: str,
    *,
    target_lookup: dict[str, str | None],
) -> str | None:
    candidate = raw_target.strip()
    if not candidate:
        return None
    if candidate.lower().startswith("this."):
        candidate = candidate[5:]
    resolved = target_lookup.get(candidate.lower())
    return resolved or None


def _extract_script_function_blocks(script_source: str) -> dict[str, tuple[list[str], str]]:
    functions: dict[str, tuple[list[str], str]] = {}
    for match in _FUNCTION_DECL_RE.finditer(script_source):
        function_name = match.group(1).strip()
        params_raw = match.group(2).strip()
        params = [token.strip() for token in params_raw.split(",") if token.strip()]
        cursor = match.end()
        depth = 1
        quote: str | None = None
        escaped = False
        while cursor < len(script_source) and depth > 0:
            ch = script_source[cursor]
            if quote is not None:
                if escaped:
                    escaped = False
                elif ch == "\\":
                    escaped = True
                elif ch == quote:
                    quote = None
                cursor += 1
                continue
            if ch in {"\"", "'"}:
                quote = ch
                cursor += 1
                continue
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
            cursor += 1
        if depth != 0:
            continue
        body = script_source[match.end() : cursor - 1]
        functions[function_name.lower()] = (params, body)
    return functions


def _extract_visibility_assignments(
    snippet: str,
    *,
    target_lookup: dict[str, str | None],
) -> list[_RuntimeVisibilityAssignment]:
    assignments: list[_RuntimeVisibilityAssignment] = []
    for match in _VISIBLE_ASSIGN_RE.finditer(snippet):
        target_node_path = _resolve_visibility_target_node_path(
            match.group(1),
            target_lookup=target_lookup,
        )
        if target_node_path is None:
            continue
        visible = match.group(2).strip().lower() == "true"
        assignments.append(
            _RuntimeVisibilityAssignment(
                node_path=target_node_path,
                visible=visible,
            )
        )
    return assignments


def _extract_condition_match_terms(
    raw_condition: str,
    *,
    function_params: list[str],
) -> tuple[Literal["selectedIndex", "value"], tuple[str, ...]] | None:
    if "&&" in raw_condition:
        return None
    matches = list(_COND_EQ_RE.finditer(raw_condition))
    if not matches:
        return None
    variable_names = {match.group(1).lower() for match in matches}
    if len(variable_names) != 1:
        return None
    variable_name = next(iter(variable_names))
    values: list[str] = []
    for match in matches:
        literal = match.group(2) or match.group(3) or match.group(4) or ""
        values.append(literal)
    ordered_values = tuple(dict.fromkeys(value.strip() for value in values if value.strip()))
    if not ordered_values:
        return None
    source_hint = "value"
    if "index" in variable_name:
        source_hint = "selectedIndex"
    elif function_params:
        param_index_map = {name.lower(): idx for idx, name in enumerate(function_params)}
        index_position = param_index_map.get(variable_name)
        if index_position is not None and index_position >= 3:
            source_hint = "selectedIndex"
    return (source_hint, ordered_values)


def _build_runtime_visibility_function_rules(
    *,
    screen: ScreenIR,
    input_xml_path: str,
) -> dict[str, _RuntimeVisibilityFunctionRule]:
    target_lookup = _build_visibility_target_lookup(screen.root)
    script_sources: list[str] = []

    for script in screen.scripts:
        if script.body and "function" in script.body:
            script_sources.append(script.body)

    input_path = Path(input_xml_path)
    if input_path.exists():
        raw_xml = _read_xml_text_with_fallback(input_path)
        if raw_xml and "function" in raw_xml:
            script_sources.append(raw_xml)

    if not script_sources:
        return {}

    function_blocks: dict[str, tuple[list[str], str]] = {}
    for source in script_sources:
        function_blocks.update(_extract_script_function_blocks(source))

    output: dict[str, _RuntimeVisibilityFunctionRule] = {}
    for function_name, (function_params, function_body) in function_blocks.items():
        conditional_rules: list[_RuntimeVisibilityConditionalRule] = []
        body_without_conditionals = function_body
        for conditional_match in _IF_ELSE_RE.finditer(function_body):
            condition_terms = _extract_condition_match_terms(
                conditional_match.group("cond"),
                function_params=function_params,
            )
            if condition_terms is None:
                continue
            match_source, match_values = condition_terms
            true_assignments = tuple(
                _extract_visibility_assignments(
                    conditional_match.group("if_body"),
                    target_lookup=target_lookup,
                )
            )
            false_assignments = tuple(
                _extract_visibility_assignments(
                    conditional_match.group("else_body"),
                    target_lookup=target_lookup,
                )
            )
            if not true_assignments and not false_assignments:
                continue
            conditional_rules.append(
                _RuntimeVisibilityConditionalRule(
                    match_source=match_source,
                    match_values=match_values,
                    true_assignments=true_assignments,
                    false_assignments=false_assignments,
                )
            )
            span_start, span_end = conditional_match.span()
            body_without_conditionals = (
                body_without_conditionals[:span_start]
                + (" " * (span_end - span_start))
                + body_without_conditionals[span_end:]
            )

        unconditional_assignments = tuple(
            _extract_visibility_assignments(
                body_without_conditionals,
                target_lookup=target_lookup,
            )
        )
        if not unconditional_assignments and not conditional_rules:
            continue
        output[function_name] = _RuntimeVisibilityFunctionRule(
            unconditional_assignments=unconditional_assignments,
            conditional_rules=tuple(conditional_rules),
        )
    return output


def _dedupe_visibility_assignments(
    assignments: tuple[_RuntimeVisibilityAssignment, ...],
) -> dict[str, bool]:
    deduped: dict[str, bool] = {}
    for assignment in assignments:
        deduped[assignment.node_path] = assignment.visible
    return deduped


def _build_runtime_visibility_codegen_plan(
    *,
    screen: ScreenIR,
    input_xml_path: str,
    event_action_bindings: list[BehaviorEventActionBinding],
) -> _RuntimeVisibilityCodegenPlan | None:
    function_rules = _build_runtime_visibility_function_rules(
        screen=screen,
        input_xml_path=input_xml_path,
    )
    if not function_rules:
        return None

    action_wrappers: dict[str, str] = {}
    function_lines: list[str] = []
    initial_state: dict[str, bool] = {}
    target_node_paths: set[str] = set()

    onload_handler_identifiers: set[str] = set()
    for event in screen.events:
        if event.event_name.lower() not in {"onload", "onloadcompleted"}:
            continue
        handler_identifier = _extract_handler_identifier(event.handler)
        if handler_identifier is None:
            continue
        onload_handler_identifiers.add(handler_identifier.lower())

    for binding in event_action_bindings:
        handler_identifier = _extract_handler_identifier(binding.handler)
        if handler_identifier is None:
            continue
        function_rule = function_rules.get(handler_identifier.lower())
        if function_rule is None:
            continue

        for assignment in function_rule.unconditional_assignments:
            target_node_paths.add(assignment.node_path)
        for conditional in function_rule.conditional_rules:
            for assignment in conditional.true_assignments:
                target_node_paths.add(assignment.node_path)
            for assignment in conditional.false_assignments:
                target_node_paths.add(assignment.node_path)

        if handler_identifier.lower() in onload_handler_identifiers:
            initial_state.update(_dedupe_visibility_assignments(function_rule.unconditional_assignments))

        wrapper_name = f"handle{binding.action_name[:1].upper()}{binding.action_name[1:]}"
        action_wrappers[binding.action_name] = wrapper_name
        function_lines.extend(
            [
                f"  const {wrapper_name} = (event: unknown): void => {{",
                (
                    "    const eventTarget = (event as { currentTarget?: "
                    "{ value?: unknown; selectedIndex?: unknown } } | undefined)?.currentTarget;"
                ),
                (
                    '    const runtimeValue = eventTarget?.value !== undefined '
                    '? String(eventTarget.value) : "";'
                ),
                (
                    '    const runtimeSelectedIndex = eventTarget?.selectedIndex !== undefined '
                    '? String(eventTarget.selectedIndex) : "";'
                ),
                "    const visibilityPatch: Record<string, boolean> = {};",
            ]
        )
        for assignment in function_rule.unconditional_assignments:
            function_lines.append(
                f'    visibilityPatch[{json.dumps(assignment.node_path, ensure_ascii=False)}] = '
                f'{"true" if assignment.visible else "false"};'
            )
        for conditional_rule in function_rule.conditional_rules:
            source_var = (
                "runtimeSelectedIndex"
                if conditional_rule.match_source == "selectedIndex"
                else "runtimeValue"
            )
            values_literal = ", ".join(
                json.dumps(value, ensure_ascii=False) for value in conditional_rule.match_values
            )
            function_lines.append(
                f"    if ([{values_literal}].includes({source_var})) {{"
            )
            for assignment in conditional_rule.true_assignments:
                function_lines.append(
                    f'      visibilityPatch[{json.dumps(assignment.node_path, ensure_ascii=False)}] = '
                    f'{"true" if assignment.visible else "false"};'
                )
            function_lines.append("    } else {")
            for assignment in conditional_rule.false_assignments:
                function_lines.append(
                    f'      visibilityPatch[{json.dumps(assignment.node_path, ensure_ascii=False)}] = '
                    f'{"true" if assignment.visible else "false"};'
                )
            function_lines.append("    }")
        function_lines.extend(
            [
                "    applyRuntimeVisibilityPatch(visibilityPatch);",
                f"    behaviorStore.{binding.action_name}();",
                "  };",
                "",
            ]
        )

    if not action_wrappers and not initial_state:
        return None

    if not target_node_paths:
        target_node_paths.update(initial_state.keys())

    return _RuntimeVisibilityCodegenPlan(
        state_var="runtimeVisibilityState",
        set_state_var="setRuntimeVisibilityState",
        apply_patch_fn="applyRuntimeVisibilityPatch",
        initial_state=initial_state,
        target_node_paths=target_node_paths,
        action_wrappers=action_wrappers,
        function_lines=function_lines,
    )


def _should_ignore_fallback_node(node: AstNode) -> bool:
    path_lower = node.source.node_path.lower()
    return "/record[" in path_lower or "/data[" in path_lower or "/cd[" in path_lower


def _normalize_render_policy_mode(mode: str) -> UiRenderPolicyMode:
    token = mode.strip().lower()
    if token == "strict":
        return "strict"
    if token == "mui":
        return "mui"
    if token == "auto":
        return "auto"
    raise ValueError(
        f"Unsupported render policy mode '{mode}'. Expected one of: {sorted(_RENDER_POLICY_MODES)}"
    )


def _resolve_auto_render_policy_risk_threshold(override: float | None) -> float:
    candidate: float | str | None = override
    if candidate is None:
        env_value = os.getenv(_AUTO_RENDER_POLICY_RISK_THRESHOLD_ENV)
        if env_value is not None and env_value.strip():
            candidate = env_value.strip()
    if candidate is None:
        return _AUTO_RENDER_POLICY_RISK_THRESHOLD

    try:
        threshold = float(candidate)
    except (TypeError, ValueError) as exc:
        raise ValueError(
            "Auto render policy threshold must be a float between 0.0 and 1.0 "
            f"(source: function arg or env {_AUTO_RENDER_POLICY_RISK_THRESHOLD_ENV})."
        ) from exc
    if threshold < 0.0 or threshold > 1.0:
        raise ValueError(
            "Auto render policy threshold must be between 0.0 and 1.0 "
            f"(got {threshold})."
        )
    return round(threshold, 4)


def _collect_render_risk_signals(node: AstNode) -> _RenderRiskSignals:
    signals = _RenderRiskSignals()

    def walk(current: AstNode) -> None:
        signals.total_nodes += 1
        lower_attr_names = {name.lower() for name in current.attributes}
        if lower_attr_names.intersection({"left", "top", "right", "bottom"}):
            signals.positioned_nodes += 1

        widget_kind = _widget_kind(current.tag)
        if widget_kind == "fallback" and not _should_ignore_fallback_node(current):
            signals.fallback_nodes += 1

        if current.tag.lower() in {"tab", "tabpage"}:
            signals.tab_nodes += 1

        signals.event_attributes += sum(
            1
            for attr_name in lower_attr_names
            if attr_name.startswith("on") and len(attr_name) > 2
        )
        for child in current.children:
            walk(child)

    walk(node)
    return signals


def _to_render_risk_signal_counts(signals: _RenderRiskSignals) -> dict[str, int]:
    return {
        "total_nodes": signals.total_nodes,
        "positioned_nodes": signals.positioned_nodes,
        "fallback_nodes": signals.fallback_nodes,
        "tab_nodes": signals.tab_nodes,
        "event_attributes": signals.event_attributes,
    }


def _compute_render_risk_signal_scores(signals: _RenderRiskSignals) -> dict[str, float]:
    if signals.total_nodes <= 0:
        return {
            "positioned_nodes": 0.0,
            "fallback_nodes": 0.0,
            "event_attributes": 0.0,
            "tab_nodes": 0.0,
            "total": 0.0,
        }
    position_ratio = signals.positioned_nodes / signals.total_nodes
    fallback_ratio = signals.fallback_nodes / signals.total_nodes
    event_density = signals.event_attributes / signals.total_nodes
    tab_presence = 1.0 if signals.tab_nodes > 0 else 0.0
    positioned_score = min(1.0, position_ratio) * 0.4
    fallback_score = min(1.0, fallback_ratio * 4.0) * 0.4
    event_score = min(1.0, event_density / 2.0) * 0.1
    tab_score = tab_presence * 0.1
    total = min(1.0, positioned_score + fallback_score + event_score + tab_score)
    return {
        "positioned_nodes": round(positioned_score, 4),
        "fallback_nodes": round(fallback_score, 4),
        "event_attributes": round(event_score, 4),
        "tab_nodes": round(tab_score, 4),
        "total": round(total, 4),
    }


def _resolve_render_policy(
    *,
    screen: ScreenIR,
    requested_mode: str,
    auto_risk_threshold: float | None = None,
) -> _RenderPolicyDecision:
    normalized_mode = _normalize_render_policy_mode(requested_mode)
    threshold = _AUTO_RENDER_POLICY_RISK_THRESHOLD
    if normalized_mode == "auto":
        threshold = _resolve_auto_render_policy_risk_threshold(auto_risk_threshold)
    elif auto_risk_threshold is not None:
        threshold = _resolve_auto_render_policy_risk_threshold(auto_risk_threshold)
    signals = _collect_render_risk_signals(screen.root)
    risk_signal_counts = _to_render_risk_signal_counts(signals)
    risk_signal_scores = _compute_render_risk_signal_scores(signals)
    risk_score = risk_signal_scores["total"]
    signal_snapshot = (
        f"risk={risk_score:.4f}; threshold={threshold:.4f}; "
        f"positioned_nodes={signals.positioned_nodes}/{signals.total_nodes}; "
        f"fallback_nodes={signals.fallback_nodes}; tab_nodes={signals.tab_nodes}; "
        f"event_attrs={signals.event_attributes}; "
        f"signal_scores=positioned_nodes:{risk_signal_scores['positioned_nodes']:.4f},"
        f"fallback_nodes:{risk_signal_scores['fallback_nodes']:.4f},"
        f"event_attributes:{risk_signal_scores['event_attributes']:.4f},"
        f"tab_nodes:{risk_signal_scores['tab_nodes']:.4f}"
    )

    if normalized_mode == "strict":
        return _RenderPolicyDecision(
            requested_mode=normalized_mode,
            resolved_mode="strict",
            decision_reason=f"explicit_strict_mode ({signal_snapshot})",
            risk_score=risk_score,
            auto_risk_threshold=threshold,
            risk_signal_counts=risk_signal_counts,
            risk_signal_scores=risk_signal_scores,
        )
    if normalized_mode == "mui":
        return _RenderPolicyDecision(
            requested_mode=normalized_mode,
            resolved_mode="mui",
            decision_reason=f"explicit_mui_mode ({signal_snapshot})",
            risk_score=risk_score,
            auto_risk_threshold=threshold,
            risk_signal_counts=risk_signal_counts,
            risk_signal_scores=risk_signal_scores,
        )
    if risk_score >= threshold:
        return _RenderPolicyDecision(
            requested_mode=normalized_mode,
            resolved_mode="strict",
            decision_reason=(
                "auto_selected_strict_high_fidelity_risk "
                f"({signal_snapshot})"
            ),
            risk_score=risk_score,
            auto_risk_threshold=threshold,
            risk_signal_counts=risk_signal_counts,
            risk_signal_scores=risk_signal_scores,
        )
    return _RenderPolicyDecision(
        requested_mode=normalized_mode,
        resolved_mode="mui",
        decision_reason=(
            "auto_selected_mui_low_fidelity_risk "
            f"({signal_snapshot})"
        ),
        risk_score=risk_score,
        auto_risk_threshold=threshold,
        risk_signal_counts=risk_signal_counts,
        risk_signal_scores=risk_signal_scores,
    )


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


def _collect_tab_bindings(
    root: AstNode,
) -> tuple[
    list[_TabBinding],
    dict[str, _TabBinding],
    dict[str, tuple[_TabBinding, int]],
]:
    bindings: list[_TabBinding] = []
    tab_lookup: dict[str, _TabBinding] = {}
    tab_page_lookup: dict[str, tuple[_TabBinding, int]] = {}
    tab_counter = 0

    def walk(node: AstNode, current_tab: _TabBinding | None) -> None:
        nonlocal tab_counter
        next_tab = current_tab
        tag_lower = node.tag.lower()
        if tag_lower == "tab":
            binding = _TabBinding(
                node_path=node.source.node_path,
                state_var=f"tabIndex{tab_counter}",
                set_state_var=f"setTabIndex{tab_counter}",
            )
            tab_counter += 1
            bindings.append(binding)
            tab_lookup[node.source.node_path] = binding
            next_tab = binding
        elif tag_lower == "tabpage" and current_tab is not None:
            page_index = len(current_tab.page_entries)
            page_entry = _TabPageEntry(
                node_path=node.source.node_path,
                label=_node_display_text(node, fallback=f"Tab {page_index + 1}"),
            )
            current_tab.page_entries.append(page_entry)
            tab_page_lookup[node.source.node_path] = (current_tab, page_index)

        for child in node.children:
            walk(child, next_tab)

    walk(root, None)
    return bindings, tab_lookup, tab_page_lookup


def _record_unsupported_event_warning(
    *,
    warnings: list[str],
    unsupported_event_inventory: list[UnsupportedUiEventBinding],
    node: AstNode,
    attr_name: str,
    attr_lower: str,
    handler: str,
    action_name: str | None,
    reason: str,
    warning_message: str,
) -> None:
    warnings.append(warning_message)
    unsupported_event_inventory.append(
        UnsupportedUiEventBinding(
            node_path=node.source.node_path,
            node_tag=node.tag,
            event_name=attr_lower,
            source_attr_name=attr_name,
            handler=handler,
            action_name=action_name,
            reason=reason,
            warning=warning_message,
            source=node.source,
        )
    )


def _render_widget_body_mui(
    node: AstNode,
    *,
    widget_kind: str,
    depth: int,
    tab_binding_lookup: dict[str, _TabBinding],
    dataset_record_lookup: dict[str, list[dict[str, str]]],
) -> list[str]:
    indent = "  " * depth
    content_style = _style_attribute(_widget_content_style(widget_kind))
    if widget_kind == "container" and node.tag.lower() == "tab":
        tab_binding = tab_binding_lookup.get(node.source.node_path)
        if tab_binding is None or not tab_binding.page_entries:
            return []
        lines = [
            (
                f'{indent}<Box className="mi-widget mi-widget-tab-nav" '
                'sx={{ borderBottom: 1, borderColor: "divider" }}>'
            ),
            (
                f"{indent}  <Tabs value={{{tab_binding.state_var}}} "
                f"onChange={{(_event, nextIndex) => {tab_binding.set_state_var}(nextIndex)}} "
                'variant="scrollable" scrollButtons="auto">'
            ),
        ]
        for page_entry in tab_binding.page_entries:
            lines.append(f"{indent}    <MuiTab label={_to_jsx_string(page_entry.label)} />")
        lines.extend(
            [
                f"{indent}  </Tabs>",
                f"{indent}</Box>",
            ]
        )
        return lines

    if widget_kind == "container":
        return []

    if widget_kind == "ignored":
        if not _should_render_ignored_trace(node):
            return []
        trace_label = _ignored_trace_label(node)
        return [
            (
                f'{indent}<Box className="mi-widget mi-widget-ignored"'
                f'{content_style} '
                'sx={{ backgroundColor: "#f3f6fb", border: "1px dashed #b7c4da", boxSizing: "border-box", color: "#334562", fontFamily: "monospace", fontSize: "11px", lineHeight: 1.3, overflow: "hidden", p: "2px 4px", whiteSpace: "pre-wrap" }}>'
                f"{_to_jsx_string(trace_label)}</Box>"
            )
        ]

    if widget_kind == "button":
        label = _node_display_text(node, fallback="Button")
        return [
            (
                f'{indent}<Box className="mi-widget mi-widget-button" component="button" '
                f'type="button"{content_style} '
                'sx={{ boxSizing: "border-box", cursor: "pointer", font: "inherit", m: 0, p: 0 }}>'
                f"{_to_jsx_string(label)}</Box>"
            )
        ]

    if widget_kind == "edit":
        label = _node_display_text(node, fallback="Edit")
        default_value = _attr_lookup(node.attributes, "value") or ""
        return [
            (
                f'{indent}<Box className="mi-widget mi-widget-edit" component="input" '
                f'type="text" aria-label={_to_jsx_string(label)}'
                f"{content_style} "
                'sx={{ boxSizing: "border-box", font: "inherit", m: 0, minWidth: 0, p: 0 }} '
                f"defaultValue={_to_jsx_string(default_value)} />"
            )
        ]

    if widget_kind == "textarea":
        label = _node_display_text(node, fallback="TextArea")
        default_value = _attr_lookup(node.attributes, "value") or ""
        rows = _attr_lookup(node.attributes, "rows")
        min_rows = 3
        if rows is not None:
            rows_token = rows.strip()
            if rows_token.isdigit():
                min_rows = max(1, int(rows_token))
        return [
            (
                f'{indent}<Box className="mi-widget mi-widget-textarea" component="textarea" '
                f'aria-label={_to_jsx_string(label)} rows={{{min_rows}}}{content_style} '
                'sx={{ boxSizing: "border-box", font: "inherit", m: 0, minWidth: 0, p: 0 }} '
                f"defaultValue={_to_jsx_string(default_value)} />"
            )
        ]

    if widget_kind == "maskedit":
        label = _node_display_text(node, fallback="MaskEdit")
        default_value = _attr_lookup(node.attributes, "value") or ""
        mask = _attr_lookup(node.attributes, "mask") or _attr_lookup(node.attributes, "format")
        placeholder_segment = (
            f" placeholder={_to_jsx_string(mask.strip())}"
            if mask is not None and mask.strip()
            else ""
        )
        return [
            (
                f'{indent}<Box className="mi-widget mi-widget-maskedit" component="input" '
                f'type="text" aria-label={_to_jsx_string(label)}'
                f"{content_style}{placeholder_segment} "
                'sx={{ boxSizing: "border-box", font: "inherit", m: 0, minWidth: 0, p: 0 }} '
                f"defaultValue={_to_jsx_string(default_value)} />"
            )
        ]

    if widget_kind == "static":
        value = _node_display_text(node, fallback="Static")
        return [
            (
                f'{indent}<Box className="mi-widget mi-widget-static" component="span"'
                f'{content_style} '
                'sx={{ boxSizing: "border-box", display: "inline-block", font: "inherit", lineHeight: 1, m: 0, overflow: "hidden", p: 0, whiteSpace: "pre" }}>'
                f"{_to_jsx_string(value)}</Box>"
            )
        ]

    if widget_kind == "combo":
        label = _node_display_text(node, fallback="Combo")
        placeholder = f"Select {label}"
        default_value = _attr_lookup(node.attributes, "value") or ""
        return [
            (
                f'{indent}<Box className="mi-widget mi-widget-combo" component="select" '
                f'aria-label={_to_jsx_string(label)}{content_style} '
                'sx={{ boxSizing: "border-box", font: "inherit", m: 0, minWidth: 0, p: 0 }} '
                f"defaultValue={_to_jsx_string(default_value)}>"
            ),
            f'{indent}  <option value="">{_to_jsx_string(placeholder)}</option>',
            f"{indent}</Box>",
        ]

    if widget_kind == "image":
        alt_text = _node_display_text(node, fallback="Image")
        src = (
            _attr_lookup(node.attributes, "src")
            or _attr_lookup(node.attributes, "url")
            or _attr_lookup(node.attributes, "image")
            or ""
        )
        if src.strip():
            src_segment = f" src={_to_jsx_string(src.strip())}"
            return [
                (
                    f'{indent}<Box className="mi-widget mi-widget-image" component="img"'
                    f"{content_style}{src_segment} alt={_to_jsx_string(alt_text)} loading=\"lazy\" />"
                )
            ]
        return [
            (
                f'{indent}<Box className="mi-widget mi-widget-image mi-widget-image-placeholder"'
                f"{content_style} "
                'sx={{ alignItems: "center", border: "1px dashed #b8c4d9", boxSizing: "border-box", color: "#4f5f7a", display: "flex", justifyContent: "center", overflow: "hidden", p: "2px" }}>'
                f"{_to_jsx_string(alt_text)}</Box>"
            )
        ]

    if widget_kind == "radio":
        label = _node_display_text(node, fallback="Radio")
        option_label = _attr_lookup(node.attributes, "itemtext") or "Option"
        radio_name = _to_css_token(_attr_lookup(node.attributes, "id") or node.source.node_path)
        default_checked = _normalize_boolean(
            _attr_lookup(node.attributes, "value") or _attr_lookup(node.attributes, "checked")
        )
        checked_literal = "true" if default_checked else "false"
        return [
            (
                f'{indent}<Box className="mi-widget mi-widget-radio" component="label" '
                f'aria-label={_to_jsx_string(label)}{content_style} '
                'sx={{ alignItems: "center", boxSizing: "border-box", display: "inline-flex", gap: "4px", m: 0, p: 0 }}>'
            ),
            (
                f'{indent}  <Box component="input" type="radio" '
                f'name={_to_jsx_string(radio_name)} defaultChecked={{{checked_literal}}} '
                'sx={{ m: 0 }} />'
            ),
            f'{indent}  <Box component="span" sx={{{{ lineHeight: 1 }}}}>{_to_jsx_string(option_label)}</Box>',
            f"{indent}</Box>",
        ]

    if widget_kind == "checkbox":
        label = _node_display_text(node, fallback="Checkbox")
        default_checked = _normalize_boolean(
            _attr_lookup(node.attributes, "value") or _attr_lookup(node.attributes, "checked")
        )
        checked_literal = "true" if default_checked else "false"
        return [
            (
                f'{indent}<Box className="mi-widget mi-widget-checkbox" component="label"'
                f'{content_style} '
                'sx={{ alignItems: "center", boxSizing: "border-box", display: "inline-flex", gap: "4px", m: 0, p: 0 }}>'
            ),
            (
                f'{indent}  <Box component="input" type="checkbox" defaultChecked={{{checked_literal}}} '
                'sx={{ m: 0 }} />'
            ),
            f'{indent}  <Box component="span" sx={{{{ lineHeight: 1 }}}}>{_to_jsx_string(label)}</Box>',
            f"{indent}</Box>",
        ]

    if widget_kind == "calendar":
        label = _node_display_text(node, fallback="Calendar")
        default_value = _attr_lookup(node.attributes, "value") or ""
        return [
            (
                f'{indent}<Box className="mi-widget mi-widget-calendar" component="input" '
                f'type="date" aria-label={_to_jsx_string(label)}'
                f"{content_style} "
                'sx={{ boxSizing: "border-box", font: "inherit", m: 0, minWidth: 0, p: 0 }} '
                f"defaultValue={_to_jsx_string(default_value)} />"
            )
        ]

    if widget_kind == "spin":
        label = _node_display_text(node, fallback="Spin")
        default_value = _attr_lookup(node.attributes, "value") or ""
        return [
            (
                f'{indent}<Box className="mi-widget mi-widget-spin" component="input" '
                f'type="number" aria-label={_to_jsx_string(label)} '
                f"{content_style} "
                'sx={{ boxSizing: "border-box", font: "inherit", m: 0, minWidth: 0, p: 0 }} '
                'step={1} '
                f"defaultValue={_to_jsx_string(default_value)} />"
            )
        ]

    if widget_kind == "treeview":
        label = _node_display_text(node, fallback="TreeView")
        return [
            (
                f'{indent}<Typography className="mi-widget mi-widget-treeview"'
                f'{content_style} variant="caption">{_to_jsx_string(f"TreeView: {label}")}</Typography>'
            )
        ]

    if widget_kind == "xchart":
        chart_title = _node_display_text(node, fallback="XChart")
        bind_dataset = _attr_lookup(node.attributes, "binddataset") or _attr_lookup(
            node.attributes, "dataset"
        )
        chart_caption = (
            f"{chart_title} ({bind_dataset})"
            if bind_dataset is not None and bind_dataset.strip()
            else chart_title
        )
        return [
            (
                f'{indent}<Box className="mi-widget mi-widget-xchart"'
                f'{content_style} '
                'sx={{ alignItems: "center", border: "1px solid #c7cfdd", boxSizing: "border-box", display: "flex", justifyContent: "center", p: "4px" }}>'
            ),
            (
                f'{indent}  <Typography variant="caption">'
                f"{_to_jsx_string(f'XChart placeholder: {chart_caption}')}"
                "</Typography>"
            ),
            f"{indent}</Box>",
        ]

    if widget_kind == "webbrowser":
        title = _node_display_text(node, fallback="WebBrowser")
        src = _attr_lookup(node.attributes, "url") or _attr_lookup(node.attributes, "src") or ""
        src_segment = f" src={_to_jsx_string(src.strip())}" if src.strip() else ""
        return [
            (
                f'{indent}<Box className="mi-widget mi-widget-webbrowser" component="iframe"'
                f"{content_style}{src_segment} title={_to_jsx_string(title)} loading=\"lazy\" />"
            )
        ]

    if widget_kind == "grid":
        grid_title = _node_display_text(node, fallback="Grid")
        bind_dataset = _attr_lookup(node.attributes, "binddataset")
        header_text = (
            f"{grid_title} ({bind_dataset})"
            if bind_dataset is not None and bind_dataset.strip()
            else grid_title
        )
        grid_layout = _grid_render_layout(node, fallback_header=header_text)
        column_widths = grid_layout.column_widths
        header_rows = grid_layout.header_rows
        body_rows = grid_layout.body_rows
        summary_rows = grid_layout.summary_rows
        dataset_rows = _resolve_grid_dataset_rows(
            node,
            dataset_record_lookup=dataset_record_lookup,
        )
        column_count = grid_layout.column_count
        lines = [
            f'{indent}<TableContainer className="mi-widget mi-widget-grid"{content_style}>',
            (
                f"{indent}  <Table size=\"small\" aria-label={_to_jsx_string(grid_title)} "
                'sx={{ tableLayout: "fixed", width: "100%" }}>'
            ),
        ]
        if column_widths:
            lines.extend(
                [
                    f"{indent}    <colgroup>",
                ]
            )
            for width in column_widths:
                lines.append(
                    f'{indent}      <col style={{{{"width": {json.dumps(width, ensure_ascii=False)}}}}} />'
                )
            lines.append(f"{indent}    </colgroup>")
        lines.extend(
            [
            f"{indent}    <TableHead>",
            ]
        )
        for row in header_rows:
            lines.append(f"{indent}      <TableRow>")
            for cell in row:
                cell_props: list[str] = []
                if cell.row_span > 1:
                    cell_props.append(f"rowSpan={{{cell.row_span}}}")
                if cell.col_span > 1:
                    cell_props.append(f"colSpan={{{cell.col_span}}}")
                cell_prop_segment = f" {' '.join(cell_props)}" if cell_props else ""
                lines.append(
                    (
                        f"{indent}        <TableCell{cell_prop_segment} "
                        'sx={{ fontSize: "12px", lineHeight: 1.2, p: "2px 4px", whiteSpace: "pre-line" }}>'
                        f"{_to_jsx_string(_resolve_grid_cell_text(cell, row=None, dataset_rows=dataset_rows, row_index=None))}</TableCell>"
                    )
                )
            lines.append(f"{indent}      </TableRow>")
        lines.extend(
            [
                f"{indent}    </TableHead>",
                f"{indent}    <TableBody>",
            ]
        )
        if body_rows:
            body_template_rows = body_rows
            if dataset_rows:
                preview_rows = dataset_rows[:_GRID_PREVIEW_ROW_LIMIT]
                for dataset_index, dataset_row in enumerate(preview_rows):
                    for row in body_template_rows:
                        lines.append(f"{indent}      <TableRow>")
                        if row:
                            for cell in row:
                                cell_props: list[str] = []
                                if cell.row_span > 1:
                                    cell_props.append(f"rowSpan={{{cell.row_span}}}")
                                if cell.col_span > 1:
                                    cell_props.append(f"colSpan={{{cell.col_span}}}")
                                cell_prop_segment = f" {' '.join(cell_props)}" if cell_props else ""
                                lines.append(
                                    (
                                        f"{indent}        <TableCell{cell_prop_segment} "
                                        'sx={{ fontSize: "12px", lineHeight: 1.2, p: "2px 4px", whiteSpace: "pre-line" }}>'
                                        f"{_to_jsx_string(_resolve_grid_cell_text(cell, row=dataset_row, dataset_rows=dataset_rows, row_index=dataset_index))}</TableCell>"
                                    )
                                )
                        lines.append(f"{indent}      </TableRow>")
            else:
                for row in body_template_rows:
                    lines.append(f"{indent}      <TableRow>")
                    if row:
                        for cell in row:
                            cell_props: list[str] = []
                            if cell.row_span > 1:
                                cell_props.append(f"rowSpan={{{cell.row_span}}}")
                            if cell.col_span > 1:
                                cell_props.append(f"colSpan={{{cell.col_span}}}")
                            cell_prop_segment = f" {' '.join(cell_props)}" if cell_props else ""
                            lines.append(
                                (
                                    f"{indent}        <TableCell{cell_prop_segment} "
                                    'sx={{ fontSize: "12px", lineHeight: 1.2, p: "2px 4px", whiteSpace: "pre-line" }}>'
                                    f"{_to_jsx_string(_resolve_grid_cell_text(cell, row=None, dataset_rows=dataset_rows, row_index=None))}</TableCell>"
                                )
                            )
                    lines.append(f"{indent}      </TableRow>")
        else:
            lines.append(f"{indent}      <TableRow>")
            for index in range(column_count):
                placeholder = "Generated grid placeholder" if index == 0 else ""
                lines.append(
                    (
                        f"{indent}        <TableCell "
                        'sx={{ fontSize: "12px", lineHeight: 1.2, p: "2px 4px", whiteSpace: "nowrap" }}>'
                        f"{_to_jsx_string(placeholder)}</TableCell>"
                    )
                )
            lines.append(f"{indent}      </TableRow>")
        lines.extend(
            [
                f"{indent}    </TableBody>",
            ]
        )
        if summary_rows:
            lines.append(f"{indent}    <TableFooter>")
            summary_row = dataset_rows[0] if dataset_rows else None
            for row in summary_rows:
                lines.append(f"{indent}      <TableRow>")
                if row:
                    for cell in row:
                        cell_props: list[str] = []
                        if cell.row_span > 1:
                            cell_props.append(f"rowSpan={{{cell.row_span}}}")
                        if cell.col_span > 1:
                            cell_props.append(f"colSpan={{{cell.col_span}}}")
                        cell_prop_segment = f" {' '.join(cell_props)}" if cell_props else ""
                        lines.append(
                            (
                                f"{indent}        <TableCell{cell_prop_segment} "
                                'sx={{ fontSize: "12px", fontWeight: 600, lineHeight: 1.2, p: "2px 4px", whiteSpace: "pre-line" }}>'
                                f"{_to_jsx_string(_resolve_grid_cell_text(cell, row=summary_row, dataset_rows=dataset_rows, row_index=0 if summary_row is not None else None))}</TableCell>"
                            )
                        )
                lines.append(f"{indent}      </TableRow>")
            lines.append(f"{indent}    </TableFooter>")
        lines.extend(
            [
                f"{indent}  </Table>",
                f"{indent}</TableContainer>",
            ]
        )
        return lines

    return [
        (
            f'{indent}<Typography className="mi-widget mi-widget-fallback"'
            f'{content_style} variant="caption">'
            f"{_to_jsx_string(f'Unsupported tag: {node.tag}')}</Typography>"
        )
    ]


def _render_widget_body_strict(
    node: AstNode,
    *,
    widget_kind: str,
    depth: int,
    tab_binding_lookup: dict[str, _TabBinding],
    dataset_record_lookup: dict[str, list[dict[str, str]]],
) -> list[str]:
    indent = "  " * depth
    content_style = _style_attribute(_widget_content_style(widget_kind))

    if widget_kind == "container" and node.tag.lower() == "tab":
        tab_binding = tab_binding_lookup.get(node.source.node_path)
        if tab_binding is None or not tab_binding.page_entries:
            return []
        lines = [f'{indent}<div className="mi-widget mi-widget-tab-nav">']
        for index, page_entry in enumerate(tab_binding.page_entries):
            lines.append(
                (
                    f'{indent}  <button type="button" '
                    f"onClick={{() => {tab_binding.set_state_var}({index})}} "
                    f"data-mi-tab-selected={{{tab_binding.state_var} === {index}}}>"
                    f"{_to_jsx_string(page_entry.label)}</button>"
                )
            )
        lines.append(f"{indent}</div>")
        return lines

    if widget_kind == "container":
        return []

    if widget_kind == "ignored":
        if not _should_render_ignored_trace(node):
            return []
        trace_label = _ignored_trace_label(node)
        return [
            (
                f'{indent}<div className="mi-widget mi-widget-ignored"'
                f'{content_style}>{_to_jsx_string(trace_label)}</div>'
            )
        ]

    if widget_kind == "button":
        label = _node_display_text(node, fallback="Button")
        return [
            (
                f'{indent}<button className="mi-widget mi-widget-button" '
                f'type="button"{content_style}>{_to_jsx_string(label)}</button>'
            )
        ]

    if widget_kind == "edit":
        label = _node_display_text(node, fallback="Edit")
        default_value = _attr_lookup(node.attributes, "value") or ""
        return [
            (
                f'{indent}<input className="mi-widget mi-widget-edit" type="text" '
                f"aria-label={_to_jsx_string(label)}{content_style} "
                f"defaultValue={_to_jsx_string(default_value)} />"
            )
        ]

    if widget_kind == "textarea":
        label = _node_display_text(node, fallback="TextArea")
        default_value = _attr_lookup(node.attributes, "value") or ""
        rows = _attr_lookup(node.attributes, "rows")
        min_rows = 3
        if rows is not None:
            rows_token = rows.strip()
            if rows_token.isdigit():
                min_rows = max(1, int(rows_token))
        return [
            (
                f'{indent}<textarea className="mi-widget mi-widget-textarea" '
                f"aria-label={_to_jsx_string(label)} rows={{{min_rows}}}{content_style} "
                f"defaultValue={_to_jsx_string(default_value)} />"
            )
        ]

    if widget_kind == "maskedit":
        label = _node_display_text(node, fallback="MaskEdit")
        default_value = _attr_lookup(node.attributes, "value") or ""
        mask = _attr_lookup(node.attributes, "mask") or _attr_lookup(node.attributes, "format")
        placeholder_segment = (
            f" placeholder={_to_jsx_string(mask.strip())}"
            if mask is not None and mask.strip()
            else ""
        )
        return [
            (
                f'{indent}<input className="mi-widget mi-widget-maskedit" type="text" '
                f"aria-label={_to_jsx_string(label)}{content_style}{placeholder_segment} "
                f"defaultValue={_to_jsx_string(default_value)} />"
            )
        ]

    if widget_kind == "static":
        value = _node_display_text(node, fallback="Static")
        return [
            (
                f'{indent}<span className="mi-widget mi-widget-static"'
                f'{content_style}>{_to_jsx_string(value)}</span>'
            )
        ]

    if widget_kind == "combo":
        label = _node_display_text(node, fallback="Combo")
        placeholder = f"Select {label}"
        default_value = _attr_lookup(node.attributes, "value") or ""
        return [
            (
                f'{indent}<select className="mi-widget mi-widget-combo" '
                f"aria-label={_to_jsx_string(label)}{content_style} "
                f"defaultValue={_to_jsx_string(default_value)}>"
            ),
            f'{indent}  <option value="">{_to_jsx_string(placeholder)}</option>',
            f"{indent}</select>",
        ]

    if widget_kind == "image":
        alt_text = _node_display_text(node, fallback="Image")
        src = (
            _attr_lookup(node.attributes, "src")
            or _attr_lookup(node.attributes, "url")
            or _attr_lookup(node.attributes, "image")
            or ""
        )
        if src.strip():
            src_segment = f" src={_to_jsx_string(src.strip())}"
            return [
                (
                    f'{indent}<img className="mi-widget mi-widget-image"'
                    f"{content_style}{src_segment} alt={_to_jsx_string(alt_text)} loading=\"lazy\" />"
                )
            ]
        return [
            (
                f'{indent}<div className="mi-widget mi-widget-image mi-widget-image-placeholder"'
                f'{content_style}>'
                f"{_to_jsx_string(alt_text)}</div>"
            )
        ]

    if widget_kind == "radio":
        label = _node_display_text(node, fallback="Radio")
        option_label = _attr_lookup(node.attributes, "itemtext") or "Option"
        radio_name = _to_css_token(_attr_lookup(node.attributes, "id") or node.source.node_path)
        default_checked = _normalize_boolean(
            _attr_lookup(node.attributes, "value") or _attr_lookup(node.attributes, "checked")
        )
        checked_literal = "true" if default_checked else "false"
        return [
            (
                f'{indent}<label className="mi-widget mi-widget-radio" '
                f'aria-label={_to_jsx_string(label)}{content_style}>'
            ),
            (
                f'{indent}  <input type="radio" name={_to_jsx_string(radio_name)} '
                f"defaultChecked={{{checked_literal}}} />"
            ),
            f"{indent}  <span>{_to_jsx_string(option_label)}</span>",
            f"{indent}</label>",
        ]

    if widget_kind == "checkbox":
        label = _node_display_text(node, fallback="Checkbox")
        default_checked = _normalize_boolean(
            _attr_lookup(node.attributes, "value") or _attr_lookup(node.attributes, "checked")
        )
        checked_literal = "true" if default_checked else "false"
        return [
            f'{indent}<label className="mi-widget mi-widget-checkbox"{content_style}>',
            f'{indent}  <input type="checkbox" defaultChecked={{{checked_literal}}} />',
            f"{indent}  <span>{_to_jsx_string(label)}</span>",
            f"{indent}</label>",
        ]

    if widget_kind == "calendar":
        label = _node_display_text(node, fallback="Calendar")
        default_value = _attr_lookup(node.attributes, "value") or ""
        return [
            (
                f'{indent}<input className="mi-widget mi-widget-calendar" type="date" '
                f"aria-label={_to_jsx_string(label)}{content_style} "
                f"defaultValue={_to_jsx_string(default_value)} />"
            )
        ]

    if widget_kind == "spin":
        label = _node_display_text(node, fallback="Spin")
        default_value = _attr_lookup(node.attributes, "value") or ""
        return [
            (
                f'{indent}<input className="mi-widget mi-widget-spin" type="number" '
                f"aria-label={_to_jsx_string(label)}{content_style} step={1} "
                f"defaultValue={_to_jsx_string(default_value)} />"
            )
        ]

    if widget_kind == "treeview":
        label = _node_display_text(node, fallback="TreeView")
        return [
            (
                f'{indent}<span className="mi-widget mi-widget-treeview"'
                f'{content_style}>{_to_jsx_string(f"TreeView: {label}")}</span>'
            )
        ]

    if widget_kind == "xchart":
        chart_title = _node_display_text(node, fallback="XChart")
        bind_dataset = _attr_lookup(node.attributes, "binddataset") or _attr_lookup(
            node.attributes, "dataset"
        )
        chart_caption = (
            f"{chart_title} ({bind_dataset})"
            if bind_dataset is not None and bind_dataset.strip()
            else chart_title
        )
        return [
            (
                f'{indent}<div className="mi-widget mi-widget-xchart"'
                f'{content_style}>'
            ),
            f"{indent}  <span>{_to_jsx_string(f'XChart placeholder: {chart_caption}')}</span>",
            f"{indent}</div>",
        ]

    if widget_kind == "webbrowser":
        title = _node_display_text(node, fallback="WebBrowser")
        src = _attr_lookup(node.attributes, "url") or _attr_lookup(node.attributes, "src") or ""
        src_segment = f" src={_to_jsx_string(src.strip())}" if src.strip() else ""
        return [
            (
                f'{indent}<iframe className="mi-widget mi-widget-webbrowser"'
                f"{content_style}{src_segment} title={_to_jsx_string(title)} loading=\"lazy\" />"
            )
        ]

    if widget_kind == "grid":
        grid_title = _node_display_text(node, fallback="Grid")
        bind_dataset = _attr_lookup(node.attributes, "binddataset")
        header_text = (
            f"{grid_title} ({bind_dataset})"
            if bind_dataset is not None and bind_dataset.strip()
            else grid_title
        )
        grid_layout = _grid_render_layout(node, fallback_header=header_text)
        column_widths = grid_layout.column_widths
        header_rows = grid_layout.header_rows
        body_rows = grid_layout.body_rows
        summary_rows = grid_layout.summary_rows
        dataset_rows = _resolve_grid_dataset_rows(
            node,
            dataset_record_lookup=dataset_record_lookup,
        )
        column_count = grid_layout.column_count
        lines = [
            f'{indent}<div className="mi-widget mi-widget-grid"{content_style}>',
            (
                f"{indent}  <table aria-label={_to_jsx_string(grid_title)} "
                'style={{"tableLayout": "fixed", "width": "100%"}}>'
            ),
        ]
        if column_widths:
            lines.append(f"{indent}    <colgroup>")
            for width in column_widths:
                lines.append(
                    f'{indent}      <col style={{{{"width": {json.dumps(width, ensure_ascii=False)}}}}} />'
                )
            lines.append(f"{indent}    </colgroup>")
        lines.extend(
            [
            f"{indent}    <thead>",
            ]
        )
        for row in header_rows:
            lines.append(f"{indent}      <tr>")
            for cell in row:
                row_span_attr = f' rowSpan={{{cell.row_span}}}' if cell.row_span > 1 else ""
                col_span_attr = f' colSpan={{{cell.col_span}}}' if cell.col_span > 1 else ""
                lines.append(
                    (
                        f'{indent}        <th{row_span_attr}{col_span_attr} '
                        'style={{"fontSize": "12px", "lineHeight": "1.2", "padding": "2px 4px", "whiteSpace": "pre-line"}}>'
                        f"{_to_jsx_string(_resolve_grid_cell_text(cell, row=None, dataset_rows=dataset_rows, row_index=None))}</th>"
                    )
                )
            lines.append(f"{indent}      </tr>")
        lines.extend(
            [
                f"{indent}    </thead>",
                f"{indent}    <tbody>",
            ]
        )
        if body_rows:
            body_template_rows = body_rows
            if dataset_rows:
                preview_rows = dataset_rows[:_GRID_PREVIEW_ROW_LIMIT]
                for dataset_index, dataset_row in enumerate(preview_rows):
                    for row in body_template_rows:
                        lines.append(f"{indent}      <tr>")
                        if row:
                            for cell in row:
                                row_span_attr = (
                                    f' rowSpan={{{cell.row_span}}}' if cell.row_span > 1 else ""
                                )
                                col_span_attr = (
                                    f' colSpan={{{cell.col_span}}}' if cell.col_span > 1 else ""
                                )
                                lines.append(
                                    (
                                        f'{indent}        <td{row_span_attr}{col_span_attr} '
                                        'style={{"fontSize": "12px", "lineHeight": "1.2", "padding": "2px 4px", "whiteSpace": "pre-line"}}>'
                                        f"{_to_jsx_string(_resolve_grid_cell_text(cell, row=dataset_row, dataset_rows=dataset_rows, row_index=dataset_index))}</td>"
                                    )
                                )
                        lines.append(f"{indent}      </tr>")
            else:
                for row in body_template_rows:
                    lines.append(f"{indent}      <tr>")
                    if row:
                        for cell in row:
                            row_span_attr = f' rowSpan={{{cell.row_span}}}' if cell.row_span > 1 else ""
                            col_span_attr = f' colSpan={{{cell.col_span}}}' if cell.col_span > 1 else ""
                            lines.append(
                                (
                                    f'{indent}        <td{row_span_attr}{col_span_attr} '
                                    'style={{"fontSize": "12px", "lineHeight": "1.2", "padding": "2px 4px", "whiteSpace": "pre-line"}}>'
                                    f"{_to_jsx_string(_resolve_grid_cell_text(cell, row=None, dataset_rows=dataset_rows, row_index=None))}</td>"
                                )
                            )
                    lines.append(f"{indent}      </tr>")
        else:
            lines.append(f"{indent}      <tr>")
            for index in range(column_count):
                placeholder = "Generated grid placeholder" if index == 0 else ""
                lines.append(
                    (
                        f'{indent}        <td '
                        'style={{"fontSize": "12px", "lineHeight": "1.2", "padding": "2px 4px", "whiteSpace": "nowrap"}}>'
                        f"{_to_jsx_string(placeholder)}</td>"
                    )
                )
            lines.append(f"{indent}      </tr>")
        lines.extend(
            [
                f"{indent}    </tbody>",
            ]
        )
        if summary_rows:
            lines.append(f"{indent}    <tfoot>")
            summary_row = dataset_rows[0] if dataset_rows else None
            for row in summary_rows:
                lines.append(f"{indent}      <tr>")
                if row:
                    for cell in row:
                        row_span_attr = f' rowSpan={{{cell.row_span}}}' if cell.row_span > 1 else ""
                        col_span_attr = f' colSpan={{{cell.col_span}}}' if cell.col_span > 1 else ""
                        lines.append(
                            (
                                f'{indent}        <td{row_span_attr}{col_span_attr} '
                                'style={{"fontSize": "12px", "fontWeight": "600", "lineHeight": "1.2", "padding": "2px 4px", "whiteSpace": "pre-line"}}>'
                                f"{_to_jsx_string(_resolve_grid_cell_text(cell, row=summary_row, dataset_rows=dataset_rows, row_index=0 if summary_row is not None else None))}</td>"
                            )
                        )
                lines.append(f"{indent}      </tr>")
            lines.append(f"{indent}    </tfoot>")
        lines.extend(
            [
                f"{indent}  </table>",
                f"{indent}</div>",
            ]
        )
        return lines

    return [
        (
            f'{indent}<span className="mi-widget mi-widget-fallback"'
            f'{content_style}>{_to_jsx_string(f"Unsupported tag: {node.tag}")}</span>'
        )
    ]


def _render_widget_body(
    node: AstNode,
    *,
    widget_kind: str,
    depth: int,
    tab_binding_lookup: dict[str, _TabBinding],
    render_mode: UiRenderMode,
    dataset_record_lookup: dict[str, list[dict[str, str]]],
) -> list[str]:
    if render_mode == "strict":
        return _render_widget_body_strict(
            node,
            widget_kind=widget_kind,
            depth=depth,
            tab_binding_lookup=tab_binding_lookup,
            dataset_record_lookup=dataset_record_lookup,
        )
    return _render_widget_body_mui(
        node,
        widget_kind=widget_kind,
        depth=depth,
        tab_binding_lookup=tab_binding_lookup,
        dataset_record_lookup=dataset_record_lookup,
    )


def _render_node(
    node: AstNode,
    *,
    depth: int,
    warnings: list[str],
    unsupported_event_inventory: list[UnsupportedUiEventBinding],
    event_wiring_stats: _EventWiringStats,
    event_action_lookup: dict[tuple[str, str, str], str],
    behavior_store_var: str,
    tab_binding_lookup: dict[str, _TabBinding],
    tab_page_lookup: dict[str, tuple[_TabBinding, int]],
    dataset_record_lookup: dict[str, list[dict[str, str]]],
    render_mode: UiRenderMode,
    runtime_visibility_plan: _RuntimeVisibilityCodegenPlan | None,
    is_root: bool = False,
) -> list[str]:
    block_indent = "  " * depth
    conditional_prefix: list[str] = []
    conditional_suffix: list[str] = []
    page_binding = tab_page_lookup.get(node.source.node_path)
    node_depth = depth
    if page_binding is not None:
        node_depth += 1

    indent = "  " * node_depth
    if page_binding is not None:
        tab_binding, page_index = page_binding
        conditional_prefix.extend(
            [
                f"{block_indent}{{{tab_binding.state_var} === {page_index} ? (",
                f"{indent}<>",
            ]
        )
        conditional_suffix.extend(
            [
                f"{indent}</>",
                f"{block_indent}) : null}}",
            ]
        )
    class_token = _to_css_token(node.tag)
    widget_kind = _widget_kind(node.tag)
    if widget_kind == "fallback" and _should_ignore_fallback_node(node):
        widget_kind = "ignored"
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
        event_wiring_stats.total_event_attributes += 1

        action_name = event_action_lookup.get(
            _event_lookup_key(
                node_path=node.source.node_path,
                event_name=attr_lower,
                handler=attr_value,
            )
        )
        if action_name is None:
            warning_message = (
                f"No behavior action binding resolved for event '{attr_name}' "
                f"at {node.source.node_path}; runtime handler not wired."
            )
            _record_unsupported_event_warning(
                warnings=warnings,
                unsupported_event_inventory=unsupported_event_inventory,
                node=node,
                attr_name=attr_name,
                attr_lower=attr_lower,
                handler=attr_value,
                action_name=None,
                reason=UNSUPPORTED_EVENT_REASON_MISSING_BINDING,
                warning_message=warning_message,
            )
            continue

        trace_attrs.append(
            f"data-mi-action-{_to_css_token(attr_lower)}={_to_jsx_string(action_name)}"
        )
        react_event_prop = _EVENT_ATTR_TO_REACT_PROP.get(attr_lower)
        if react_event_prop is None:
            warning_message = (
                f"No React event mapping for '{attr_name}' at {node.source.node_path}; "
                f"action '{action_name}' trace emitted only."
            )
            _record_unsupported_event_warning(
                warnings=warnings,
                unsupported_event_inventory=unsupported_event_inventory,
                node=node,
                attr_name=attr_name,
                attr_lower=attr_lower,
                handler=attr_value,
                action_name=action_name,
                reason=UNSUPPORTED_EVENT_REASON_MISSING_REACT_MAPPING,
                warning_message=warning_message,
            )
            continue

        if (
            runtime_visibility_plan is not None
            and action_name in runtime_visibility_plan.action_wrappers
        ):
            wrapper_name = runtime_visibility_plan.action_wrappers[action_name]
            event_props.append(f"{react_event_prop}={{{wrapper_name}}}")
        else:
            event_props.append(f"{react_event_prop}={{{behavior_store_var}.{action_name}}}")
        event_wiring_stats.runtime_wired_event_props += 1

    base_style = _build_node_style(node, is_root=is_root, widget_kind=widget_kind)
    if (
        runtime_visibility_plan is not None
        and node.source.node_path in runtime_visibility_plan.target_node_paths
        and widget_kind != "ignored"
    ):
        style_attr = _style_attribute_with_runtime_visibility(
            base_style,
            node_path=node.source.node_path,
            visibility_state_var=runtime_visibility_plan.state_var,
        )
    else:
        style_attr = _style_attribute(base_style)
    trace_payload = " ".join(trace_attrs)
    event_payload = " ".join(event_props)
    event_segment = f" {event_payload}" if event_payload else ""
    shell_tag = "div" if render_mode == "strict" else "Box"

    node_lines = [
        f"{indent}{{/* {_source_comment(node.source)} */}}",
        (
            f'{indent}<{shell_tag} className="mi-widget-shell mi-widget-shell-{class_token}" '
            f"data-mi-widget={_to_jsx_string(widget_kind)} "
            f"{trace_payload}{event_segment}{style_attr}>"
        ),
    ]

    node_lines.extend(
        _render_widget_body(
            node,
            widget_kind=widget_kind,
            depth=node_depth + 1,
            tab_binding_lookup=tab_binding_lookup,
            render_mode=render_mode,
            dataset_record_lookup=dataset_record_lookup,
        )
    )
    for child in node.children:
        node_lines.extend(
            _render_node(
                child,
                depth=node_depth + 1,
                warnings=warnings,
                unsupported_event_inventory=unsupported_event_inventory,
                event_wiring_stats=event_wiring_stats,
                event_action_lookup=event_action_lookup,
                behavior_store_var=behavior_store_var,
                tab_binding_lookup=tab_binding_lookup,
                tab_page_lookup=tab_page_lookup,
                dataset_record_lookup=dataset_record_lookup,
                render_mode=render_mode,
                runtime_visibility_plan=runtime_visibility_plan,
            )
        )
    node_lines.append(f"{indent}</{shell_tag}>")
    return [*conditional_prefix, *node_lines, *conditional_suffix]


def _count_nodes(node: AstNode) -> int:
    total = 1
    for child in node.children:
        total += _count_nodes(child)
    return total


def _render_screen_component(
    screen: ScreenIR,
    *,
    input_xml_path: str,
    event_action_bindings: list[BehaviorEventActionBinding],
    wiring_contract: RuntimeWiringContract,
    warnings: list[str],
    unsupported_event_inventory: list[UnsupportedUiEventBinding],
    event_wiring_stats: _EventWiringStats,
    event_action_lookup: dict[tuple[str, str, str], str],
    render_mode: UiRenderMode,
) -> str:
    root = screen.root
    dataset_record_lookup = _build_dataset_record_lookup(screen)
    tab_bindings, tab_binding_lookup, tab_page_lookup = _collect_tab_bindings(root)
    runtime_visibility_plan = _build_runtime_visibility_codegen_plan(
        screen=screen,
        input_xml_path=input_xml_path,
        event_action_bindings=event_action_bindings,
    )
    header_source_file = _escape_comment(root.source.file_path)
    header_source_node = _escape_comment(root.source.node_path)
    behavior_store_var = "behaviorStore"
    has_grid_summary_band = _screen_has_grid_summary_band(root)
    react_import = (
        'import { useState, type JSX } from "react";'
        if tab_bindings or runtime_visibility_plan is not None
        else 'import type { JSX } from "react";'
    )
    import_lines = [react_import]
    if render_mode == "mui":
        mui_import_tokens = [
            "Box",
            "Table",
            "TableBody",
            "TableCell",
            "TableContainer",
            "TableFooter",
            "TableHead",
            "TableRow",
            "Typography",
        ]
        if not has_grid_summary_band:
            mui_import_tokens.remove("TableFooter")
        if tab_bindings:
            mui_import_tokens.extend(["Tab as MuiTab", "Tabs"])
        import_lines.append(f'import {{ {", ".join(mui_import_tokens)} }} from "@mui/material";')
    import_lines.append(
        (
            f'import {{ {wiring_contract.behavior_store_hook_name} }} '
            f'from "{wiring_contract.behavior_store_import_from_screen}";'
        )
    )

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
        *import_lines,
        "",
        f"export default function {wiring_contract.screen_component_name}(): JSX.Element {{",
        f"  const {behavior_store_var} = {wiring_contract.behavior_store_hook_name}();",
    ]
    if tab_bindings:
        lines.append("")
        for tab_binding in tab_bindings:
            lines.append(
                f"  const [{tab_binding.state_var}, {tab_binding.set_state_var}] = useState<number>(0);"
            )
    if runtime_visibility_plan is not None:
        initial_state_payload = {
            key: runtime_visibility_plan.initial_state[key]
            for key in sorted(runtime_visibility_plan.initial_state)
        }
        initial_state_json = json.dumps(initial_state_payload, ensure_ascii=False)
        lines.extend(
            [
                "",
                (
                    f"  const [{runtime_visibility_plan.state_var}, "
                    f"{runtime_visibility_plan.set_state_var}] = useState<Record<string, boolean>>("
                    f"() => ({initial_state_json})"
                    ");"
                ),
                (
                    f"  const {runtime_visibility_plan.apply_patch_fn} = "
                    "(patch: Record<string, boolean>): void => {"
                ),
                f"    {runtime_visibility_plan.set_state_var}((prev) => {{",
                "      let changed = false;",
                "      const next: Record<string, boolean> = { ...prev };",
                "      for (const [nodePath, visible] of Object.entries(patch)) {",
                "        if (next[nodePath] !== visible) {",
                "          next[nodePath] = visible;",
                "          changed = true;",
                "        }",
                "      }",
                "      return changed ? next : prev;",
                "    });",
                "  };",
                "",
            ]
        )
        lines.extend(runtime_visibility_plan.function_lines)
    lines.extend(
        [
            "",
            "  return (",
            (
                '    <section className="mi-generated-screen" '
                f"data-mi-screen-id={_to_jsx_string(screen.screen_id)} "
                f"data-mi-source-node={_to_jsx_string(root.source.node_path)} "
                f"data-mi-source-file={_to_jsx_string(root.source.file_path)}>"
            ),
        ]
    )
    lines.extend(
        _render_node(
            root,
            depth=3,
            warnings=warnings,
            unsupported_event_inventory=unsupported_event_inventory,
            event_wiring_stats=event_wiring_stats,
            event_action_lookup=event_action_lookup,
            behavior_store_var=behavior_store_var,
            tab_binding_lookup=tab_binding_lookup,
            tab_page_lookup=tab_page_lookup,
            dataset_record_lookup=dataset_record_lookup,
            render_mode=render_mode,
            runtime_visibility_plan=runtime_visibility_plan,
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
    mode: UiRenderPolicyMode = "mui",
    auto_risk_threshold: float | None = None,
) -> UiCodegenReport:
    out_root = Path(out_dir).resolve()
    policy_decision = _resolve_render_policy(
        screen=screen,
        requested_mode=mode,
        auto_risk_threshold=auto_risk_threshold,
    )
    wiring_contract = build_runtime_wiring_contract(screen.screen_id)
    tsx_path = out_root / "src" / "screens" / f"{wiring_contract.screen_file_stem}.tsx"
    tsx_path.parent.mkdir(parents=True, exist_ok=True)

    behavior_report = generate_behavior_store_artifacts(
        screen=screen,
        input_xml_path=input_xml_path,
        out_dir=out_root,
    )

    warnings: list[str] = []
    unsupported_event_inventory: list[UnsupportedUiEventBinding] = []
    event_wiring_stats = _EventWiringStats()
    tsx_path.write_text(
        _render_screen_component(
            screen,
            input_xml_path=input_xml_path,
            event_action_bindings=behavior_report.event_action_bindings,
            wiring_contract=wiring_contract,
            warnings=warnings,
            unsupported_event_inventory=unsupported_event_inventory,
            event_wiring_stats=event_wiring_stats,
            event_action_lookup=_build_event_action_lookup(
                behavior_report.event_action_bindings
            ),
            render_mode=policy_decision.resolved_mode,
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
            total_event_attributes=event_wiring_stats.total_event_attributes,
            runtime_wired_event_props=event_wiring_stats.runtime_wired_event_props,
            unsupported_event_bindings=len(unsupported_event_inventory),
        ),
        requested_mode=policy_decision.requested_mode,
        mode=policy_decision.resolved_mode,
        decision_reason=policy_decision.decision_reason,
        risk_score=policy_decision.risk_score,
        auto_risk_threshold=policy_decision.auto_risk_threshold,
        risk_signal_counts=policy_decision.risk_signal_counts,
        risk_signal_scores=policy_decision.risk_signal_scores,
        unsupported_event_inventory=unsupported_event_inventory,
        warnings=warnings,
    )


__all__ = [
    "UnsupportedUiEventBinding",
    "UiCodegenReport",
    "UiCodegenSummary",
    "UiRenderMode",
    "UiRenderPolicyMode",
    "generate_ui_codegen_artifacts",
]
