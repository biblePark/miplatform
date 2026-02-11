from __future__ import annotations

from collections import defaultdict
from pathlib import Path
import xml.etree.ElementTree as ET

from .models import (
    AstNode,
    BindingIR,
    DatasetColumnIR,
    DatasetIR,
    DatasetRecordIR,
    EventIR,
    ParseConfig,
    ParseReport,
    ParseStats,
    ScreenIR,
    ScriptBlockIR,
    SourceRef,
    TransactionIR,
    UnknownAttr,
    UnknownTag,
    ValidationGate,
)
from .validator import (
    canonical_gate_message,
    compute_canonical_hash_pair,
    compute_roundtrip_mismatches,
    diff_gate_message,
)


class ParseStrictError(RuntimeError):
    """Raised when strict parse gates fail."""


def _iter_nodes(root: AstNode):
    yield root
    for child in root.children:
        yield from _iter_nodes(child)


def _iter_dataset_record_nodes(root_dataset: AstNode):
    def walk(node: AstNode):
        for child in node.children:
            if child.tag == "Dataset" and child is not root_dataset:
                continue
            if child.tag == "record":
                yield child
            yield from walk(child)

    yield from walk(root_dataset)


def _extract_dataset(dataset_node: AstNode) -> DatasetIR:
    columns: list[DatasetColumnIR] = []
    records: list[DatasetRecordIR] = []

    for child in dataset_node.children:
        if child.tag != "colinfo":
            continue
        for column_node in child.children:
            if column_node.tag != "column":
                continue
            columns.append(
                DatasetColumnIR(
                    column_id=column_node.attributes.get("id"),
                    data_type=column_node.attributes.get("type"),
                    attributes=dict(column_node.attributes),
                    source=column_node.source,
                )
            )

    for record_node in _iter_dataset_record_nodes(dataset_node):
        records.append(
            DatasetRecordIR(
                values=dict(record_node.attributes),
                source=record_node.source,
            )
        )

    return DatasetIR(
        dataset_id=dataset_node.attributes.get("id"),
        attributes=dict(dataset_node.attributes),
        columns=columns,
        records=records,
        source=dataset_node.source,
    )


def _is_transaction_node(node: AstNode) -> bool:
    tag_name = node.tag.lower()
    attr_keys = {key.lower() for key in node.attributes}

    if tag_name in {"transaction", "service", "request", "submit"}:
        return True

    if any(
        key.startswith("transaction")
        or key in {"serviceid", "svcid", "serviceurl", "httpmethod"}
        for key in attr_keys
    ):
        return True

    return False


def _extract_transaction(node: AstNode) -> TransactionIR:
    attrs = node.attributes
    return TransactionIR(
        node_tag=node.tag,
        node_id=attrs.get("id"),
        transaction_id=(
            attrs.get("transactionid")
            or attrs.get("serviceid")
            or attrs.get("svcid")
            or attrs.get("id")
            or attrs.get("name")
        ),
        endpoint=attrs.get("url") or attrs.get("endpoint") or attrs.get("serviceurl"),
        method=attrs.get("method") or attrs.get("httpmethod"),
        source=node.source,
    )


def _is_script_node(node: AstNode) -> bool:
    tag_name = node.tag.lower()
    attr_keys = {key.lower() for key in node.attributes}

    if tag_name in {"script", "function", "handler"}:
        return True

    script_like_keys = {"script", "scriptbody", "expression", "expr", "functionbody"}
    if script_like_keys.intersection(attr_keys):
        return True

    return False


def _extract_script(node: AstNode) -> ScriptBlockIR:
    attrs = node.attributes
    body = (
        node.text
        or attrs.get("script")
        or attrs.get("scriptbody")
        or attrs.get("expression")
        or attrs.get("expr")
        or attrs.get("functionbody")
        or ""
    )
    return ScriptBlockIR(
        node_tag=node.tag,
        node_id=attrs.get("id"),
        script_name=attrs.get("name") or attrs.get("id") or attrs.get("function"),
        body=body,
        source=node.source,
    )


def _extract_entities(
    ast_root: AstNode,
) -> tuple[
    list[DatasetIR],
    list[BindingIR],
    list[EventIR],
    list[TransactionIR],
    list[ScriptBlockIR],
    int,
    int,
    int,
    int,
    int,
]:
    datasets: list[DatasetIR] = []
    bindings: list[BindingIR] = []
    events: list[EventIR] = []
    transactions: list[TransactionIR] = []
    scripts: list[ScriptBlockIR] = []
    dataset_nodes_found = 0
    binding_points_found = 0
    event_points_found = 0
    transaction_points_found = 0
    script_points_found = 0

    for node in _iter_nodes(ast_root):
        node_id = node.attributes.get("id")

        if node.tag == "Dataset":
            dataset_nodes_found += 1
            datasets.append(_extract_dataset(node))

        for attr_key, attr_value in node.attributes.items():
            if attr_key.startswith("bind"):
                binding_points_found += 1
                bindings.append(
                    BindingIR(
                        node_tag=node.tag,
                        node_id=node_id,
                        binding_key=attr_key,
                        binding_value=attr_value,
                        source=node.source,
                    )
                )

            if attr_key.startswith("on") and len(attr_key) > 2:
                event_points_found += 1
                events.append(
                    EventIR(
                        node_tag=node.tag,
                        node_id=node_id,
                        event_name=attr_key,
                        handler=attr_value,
                        source=node.source,
                    )
                )

        if node.tag.lower() == "event":
            event_points_found += 1
            events.append(
                EventIR(
                    node_tag=node.tag,
                    node_id=node_id,
                    event_name=node.attributes.get("name", "event"),
                    handler=node.attributes.get("handler")
                    or node.attributes.get("function")
                    or node.attributes.get("script")
                    or "",
                    source=node.source,
                )
            )

        if _is_transaction_node(node):
            transaction_points_found += 1
            transactions.append(_extract_transaction(node))

        if _is_script_node(node):
            script_points_found += 1
            scripts.append(_extract_script(node))

    return (
        datasets,
        bindings,
        events,
        transactions,
        scripts,
        dataset_nodes_found,
        binding_points_found,
        event_points_found,
        transaction_points_found,
        script_points_found,
    )


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

    (
        datasets,
        bindings,
        events,
        transactions,
        scripts,
        dataset_nodes_found,
        binding_points_found,
        event_points_found,
        transaction_points_found,
        script_points_found,
    ) = _extract_entities(ast_root)

    if cfg.enable_roundtrip_gate:
        mismatches_all = compute_roundtrip_mismatches(
            root, ast_root, include_text=cfg.capture_text
        )
        roundtrip_diff = len(mismatches_all)
        mismatch_limit = max(0, cfg.roundtrip_mismatch_limit)
        mismatches = mismatches_all[:mismatch_limit] if mismatch_limit else []
        mismatch_truncated = max(0, roundtrip_diff - len(mismatches))
        canonical_source_hash, canonical_ast_hash = compute_canonical_hash_pair(
            root, ast_root, include_text=cfg.capture_text
        )
        canonical_mismatch = canonical_source_hash != canonical_ast_hash
    else:
        mismatches = []
        mismatch_truncated = 0
        roundtrip_diff = 0
        canonical_source_hash = None
        canonical_ast_hash = None
        canonical_mismatch = False

    stats = ParseStats(
        total_nodes=sum(tag_counts.values()),
        max_depth=max_depth,
        tag_counts=dict(sorted(tag_counts.items())),
        attr_counts=dict(sorted(attr_counts.items())),
        unknown_tags=unknown_tags,
        unknown_attrs=unknown_attrs,
        roundtrip_mismatches=mismatches,
        canonical_source_hash=canonical_source_hash,
        canonical_ast_hash=canonical_ast_hash,
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
        ValidationGate(
            name="roundtrip_structural_diff",
            passed=roundtrip_diff == 0,
            value=roundtrip_diff,
            expected=0,
            message=diff_gate_message(roundtrip_diff)
            if cfg.enable_roundtrip_gate
            else "Roundtrip gates disabled by config.",
        ),
        ValidationGate(
            name="canonical_roundtrip_hash_match",
            passed=not canonical_mismatch,
            value=1 if canonical_mismatch else 0,
            expected=0,
            message=canonical_gate_message(not canonical_mismatch)
            if cfg.enable_roundtrip_gate
            else "Roundtrip gates disabled by config.",
        ),
        ValidationGate(
            name="dataset_extraction_coverage",
            passed=len(datasets) == dataset_nodes_found,
            value=len(datasets),
            expected=dataset_nodes_found,
            message="All Dataset nodes are represented in IR.",
        ),
        ValidationGate(
            name="binding_extraction_coverage",
            passed=len(bindings) == binding_points_found,
            value=len(bindings),
            expected=binding_points_found,
            message="All binding attributes are represented in IR.",
        ),
        ValidationGate(
            name="event_extraction_coverage",
            passed=len(events) == event_points_found,
            value=len(events),
            expected=event_points_found,
            message="All event points are represented in IR.",
        ),
        ValidationGate(
            name="transaction_extraction_coverage",
            passed=len(transactions) == transaction_points_found,
            value=len(transactions),
            expected=transaction_points_found,
            message="All transaction points are represented in IR.",
        ),
        ValidationGate(
            name="script_extraction_coverage",
            passed=len(scripts) == script_points_found,
            value=len(scripts),
            expected=script_points_found,
            message="All script points are represented in IR.",
        ),
    ]

    errors: list[str] = []
    warnings: list[str] = []
    if unknown_tags:
        warnings.append(f"Unknown tags found: {len(unknown_tags)}")
    if unknown_attrs:
        warnings.append(f"Unknown attrs found: {len(unknown_attrs)}")
    if roundtrip_diff:
        warnings.append(diff_gate_message(roundtrip_diff))
    if mismatch_truncated:
        warnings.append(
            f"Roundtrip mismatch details truncated by {mismatch_truncated} entries."
        )
    if canonical_mismatch:
        warnings.append(canonical_gate_message(False))

    if cfg.strict:
        failed = [gate for gate in gates if not gate.passed]
        if failed:
            gate_names = ", ".join(gate.name for gate in failed)
            raise ParseStrictError(f"Strict parse failed for gates: {gate_names}")

    screen_id = Path(source_path).stem
    screen = ScreenIR(
        screen_id=screen_id,
        root=ast_root,
        datasets=datasets,
        bindings=bindings,
        events=events,
        transactions=transactions,
        scripts=scripts,
    )
    return ParseReport(screen=screen, stats=stats, gates=gates, errors=errors, warnings=warnings)
