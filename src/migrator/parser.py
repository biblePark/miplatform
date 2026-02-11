from __future__ import annotations

from collections import defaultdict
from pathlib import Path
import xml.etree.ElementTree as ET

from .models import (
    AstNode,
    ParseConfig,
    ParseReport,
    ParseStats,
    ScreenIR,
    SourceRef,
    UnknownAttr,
    UnknownTag,
    ValidationGate,
)


class ParseStrictError(RuntimeError):
    """Raised when strict parse gates fail."""


def parse_xml_file(file_path: str | Path, config: ParseConfig | None = None) -> ParseReport:
    cfg = config or ParseConfig()
    source_path = str(Path(file_path).resolve())

    try:
        tree = ET.parse(source_path)
    except ET.ParseError as exc:
        raise ParseStrictError(f"XML parse failure: {exc}") from exc

    root = tree.getroot()
    tag_counts: dict[str, int] = defaultdict(int)
    attr_counts: dict[str, int] = defaultdict(int)
    unknown_tags: list[UnknownTag] = []
    unknown_attrs: list[UnknownAttr] = []
    max_depth = 0

    def walk(elem: ET.Element, node_path: str, depth: int) -> AstNode:
        nonlocal max_depth
        max_depth = max(max_depth, depth)

        tag_counts[elem.tag] += 1
        for attr_name in elem.attrib:
            attr_counts[attr_name] += 1

        if cfg.known_tags is not None and elem.tag not in cfg.known_tags:
            unknown_tags.append(UnknownTag(tag=elem.tag, node_path=node_path))

        if cfg.known_attrs_by_tag is not None:
            allow_attrs = cfg.known_attrs_by_tag.get(elem.tag, cfg.known_attrs_by_tag.get("*"))
            if allow_attrs is not None:
                for attr_name in elem.attrib:
                    if attr_name not in allow_attrs:
                        unknown_attrs.append(
                            UnknownAttr(tag=elem.tag, attr=attr_name, node_path=node_path)
                        )

        child_indices: dict[str, int] = defaultdict(int)
        children: list[AstNode] = []
        for child in list(elem):
            child_indices[child.tag] += 1
            child_path = f"{node_path}/{child.tag}[{child_indices[child.tag]}]"
            children.append(walk(child, child_path, depth + 1))

        line = getattr(elem, "sourceline", None)
        text = (elem.text or "").strip() if cfg.capture_text else None
        if text == "":
            text = None

        return AstNode(
            tag=elem.tag,
            attributes=dict(elem.attrib),
            text=text,
            source=SourceRef(file_path=source_path, node_path=node_path, line=line),
            children=children,
        )

    root_path = f"/{root.tag}[1]"
    ast_root = walk(root, root_path, 1)

    stats = ParseStats(
        total_nodes=sum(tag_counts.values()),
        max_depth=max_depth,
        tag_counts=dict(sorted(tag_counts.items())),
        attr_counts=dict(sorted(attr_counts.items())),
        unknown_tags=unknown_tags,
        unknown_attrs=unknown_attrs,
    )

    gates = [
        ValidationGate(
            name="unknown_tag_count",
            passed=len(unknown_tags) == 0,
            value=len(unknown_tags),
            expected=0,
            message="All tags are recognized by parser profile.",
        ),
        ValidationGate(
            name="unknown_attr_count",
            passed=len(unknown_attrs) == 0,
            value=len(unknown_attrs),
            expected=0,
            message="All attributes are recognized by parser profile.",
        ),
    ]

    errors: list[str] = []
    warnings: list[str] = []
    if unknown_tags:
        warnings.append(f"Unknown tags found: {len(unknown_tags)}")
    if unknown_attrs:
        warnings.append(f"Unknown attrs found: {len(unknown_attrs)}")

    if cfg.strict:
        failed = [gate for gate in gates if not gate.passed]
        if failed:
            gate_names = ", ".join(gate.name for gate in failed)
            raise ParseStrictError(f"Strict parse failed for gates: {gate_names}")

    screen_id = Path(source_path).stem
    screen = ScreenIR(screen_id=screen_id, root=ast_root)
    return ParseReport(screen=screen, stats=stats, gates=gates, errors=errors, warnings=warnings)

