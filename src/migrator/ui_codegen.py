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
_CONTAINER_TAGS = frozenset(
    {"screen", "contents", "container", "window", "form", "div", "shape", "tab", "tabpage"}
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
    "spin": "spin",
    "treeview": "treeview",
    "webbrowser": "webbrowser",
    "msie": "webbrowser",
    "rexpert": "webbrowser",
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
        "cell",
        "cd",
        "data",
        "script",
        "httpfile",
        "filedialog",
        "file",
        "cylastinput",
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

    if widget_kind == "ignored":
        # Keep deterministic trace nodes in DOM for audit, but never surface them in preview UI.
        style["display"] = "none"

    return style


def _style_attribute(style: dict[str, str]) -> str:
    if not style:
        return ""
    payload = {key: style[key] for key in sorted(style)}
    style_json = json.dumps(payload, ensure_ascii=False)
    return f" style={{{style_json}}}"


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


def _should_ignore_fallback_node(node: AstNode) -> bool:
    path_lower = node.source.node_path.lower()
    return "/record[" in path_lower or "/data[" in path_lower or "/cd[" in path_lower


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


def _render_widget_body(
    node: AstNode,
    *,
    widget_kind: str,
    depth: int,
    tab_binding_lookup: dict[str, _TabBinding],
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

    if widget_kind in {"container", "ignored"}:
        return []

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
                f'{indent}<Typography className="mi-widget mi-widget-static"'
                f'{content_style} variant="body2">{_to_jsx_string(value)}</Typography>'
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
        src_segment = f" src={_to_jsx_string(src.strip())}" if src.strip() else ""
        return [
            (
                f'{indent}<Box className="mi-widget mi-widget-image" component="img"'
                f"{content_style}{src_segment} alt={_to_jsx_string(alt_text)} loading=\"lazy\" />"
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
        column_labels = _grid_column_labels(node, fallback=header_text)
        lines = [
            f'{indent}<TableContainer className="mi-widget mi-widget-grid"{content_style}>',
            f"{indent}  <Table size=\"small\" aria-label={_to_jsx_string(grid_title)}>",
            f"{indent}    <TableHead>",
            f"{indent}      <TableRow>",
        ]
        for label in column_labels:
            lines.append(
                f'{indent}        <TableCell sx={{{{ whiteSpace: "nowrap" }}}}>{_to_jsx_string(label)}</TableCell>'
            )
        lines.extend(
            [
                f"{indent}      </TableRow>",
                f"{indent}    </TableHead>",
                f"{indent}    <TableBody>",
                f"{indent}      <TableRow>",
            ]
        )
        for index, _label in enumerate(column_labels):
            placeholder = "Generated grid placeholder" if index == 0 else ""
            lines.append(
                f'{indent}        <TableCell sx={{{{ whiteSpace: "nowrap" }}}}>{_to_jsx_string(placeholder)}</TableCell>'
            )
        lines.extend(
            [
                f"{indent}      </TableRow>",
                f"{indent}    </TableBody>",
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

        event_props.append(f"{react_event_prop}={{{behavior_store_var}.{action_name}}}")
        event_wiring_stats.runtime_wired_event_props += 1

    style_attr = _style_attribute(
        _build_node_style(node, is_root=is_root, widget_kind=widget_kind)
    )
    trace_payload = " ".join(trace_attrs)
    event_payload = " ".join(event_props)
    event_segment = f" {event_payload}" if event_payload else ""

    node_lines = [
        f"{indent}{{/* {_source_comment(node.source)} */}}",
        (
            f'{indent}<Box className="mi-widget-shell mi-widget-shell-{class_token}" '
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
            )
        )
    node_lines.append(f"{indent}</Box>")
    return [*conditional_prefix, *node_lines, *conditional_suffix]


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
    unsupported_event_inventory: list[UnsupportedUiEventBinding],
    event_wiring_stats: _EventWiringStats,
    event_action_lookup: dict[tuple[str, str, str], str],
) -> str:
    root = screen.root
    tab_bindings, tab_binding_lookup, tab_page_lookup = _collect_tab_bindings(root)
    header_source_file = _escape_comment(root.source.file_path)
    header_source_node = _escape_comment(root.source.node_path)
    behavior_store_var = "behaviorStore"
    react_import = (
        'import { useState, type JSX } from "react";'
        if tab_bindings
        else 'import type { JSX } from "react";'
    )
    mui_import_tokens = [
        "Box",
        "Table",
        "TableBody",
        "TableCell",
        "TableContainer",
        "TableHead",
        "TableRow",
        "Typography",
    ]
    if tab_bindings:
        mui_import_tokens.extend(["Tab as MuiTab", "Tabs"])
    mui_import_line = f'import {{ {", ".join(mui_import_tokens)} }} from "@mui/material";'

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
        react_import,
        mui_import_line,
        (
            f'import {{ {wiring_contract.behavior_store_hook_name} }} '
            f'from "{wiring_contract.behavior_store_import_from_screen}";'
        ),
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
    unsupported_event_inventory: list[UnsupportedUiEventBinding] = []
    event_wiring_stats = _EventWiringStats()
    tsx_path.write_text(
        _render_screen_component(
            screen,
            wiring_contract=wiring_contract,
            warnings=warnings,
            unsupported_event_inventory=unsupported_event_inventory,
            event_wiring_stats=event_wiring_stats,
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
            total_event_attributes=event_wiring_stats.total_event_attributes,
            runtime_wired_event_props=event_wiring_stats.runtime_wired_event_props,
            unsupported_event_bindings=len(unsupported_event_inventory),
        ),
        unsupported_event_inventory=unsupported_event_inventory,
        warnings=warnings,
    )


__all__ = [
    "UnsupportedUiEventBinding",
    "UiCodegenReport",
    "UiCodegenSummary",
    "generate_ui_codegen_artifacts",
]
