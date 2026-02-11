from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
import json
from pathlib import Path
import re
from typing import Any
from urllib.parse import urlsplit

from .models import BindingIR, EventIR, ScreenIR, SourceRef, TransactionIR

_NON_ALNUM = re.compile(r"[^0-9A-Za-z]+")
_CAMEL_TOKEN = re.compile(r"[A-Z]+(?=[A-Z][a-z]|[0-9]|$)|[A-Z]?[a-z]+|[0-9]+")
_HANDLER_IDENTIFIER = re.compile(r"[A-Za-z_][A-Za-z0-9_.]*")
_MULTI_SLASH = re.compile(r"/{2,}")

DUPLICATE_ACTION_POLICY = (
    "action_base_name:first_seen_keeps_base;later_duplicates_append_numeric_suffix"
)
DUPLICATE_STATE_POLICY = (
    "state_key_base:first_seen_keeps_base;later_duplicates_append_numeric_suffix"
)


@dataclass(slots=True)
class BehaviorStoreSummary:
    total_bindings: int
    total_events: int
    total_transactions: int
    generated_state_keys: int
    generated_actions: int
    duplicate_state_keys: int
    duplicate_actions: int


@dataclass(slots=True)
class BehaviorStateSpec:
    index: int
    node_id: str | None
    binding_key: str
    binding_value: str
    state_key: str
    base_state_key: str
    duplicate_of_index: int | None = None
    duplicate_of_state_key: str | None = None
    source: SourceRef | None = None


@dataclass(slots=True)
class BehaviorActionSpec:
    index: int
    source_kind: str
    action_name: str
    base_action_name: str
    event_name: str | None = None
    handler: str | None = None
    transaction_id: str | None = None
    endpoint: str | None = None
    method: str | None = None
    duplicate_of_index: int | None = None
    duplicate_of_action_name: str | None = None
    source: SourceRef | None = None


@dataclass(slots=True)
class BehaviorStorePlan:
    states: list[BehaviorStateSpec]
    actions: list[BehaviorActionSpec]
    summary: BehaviorStoreSummary


@dataclass(slots=True)
class BehaviorStoreReport:
    screen_id: str
    input_xml_path: str
    store_file: str
    actions_file: str
    summary: BehaviorStoreSummary
    states: list[BehaviorStateSpec]
    actions: list[BehaviorActionSpec]
    duplicate_action_policy: str = DUPLICATE_ACTION_POLICY
    duplicate_state_policy: str = DUPLICATE_STATE_POLICY
    warnings: list[str] = field(default_factory=list)
    generated_at_utc: str = field(default_factory=lambda: datetime.now(UTC).isoformat())

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _to_file_stem(raw: str) -> str:
    chunks = [chunk.lower() for chunk in _NON_ALNUM.split(raw) if chunk]
    return "-".join(chunks) if chunks else "screen"


def _split_identifier_tokens(raw: str) -> list[str]:
    normalized = _NON_ALNUM.sub(" ", raw).strip()
    if not normalized:
        return []

    tokens: list[str] = []
    for chunk in normalized.split():
        tokens.extend(_CAMEL_TOKEN.findall(chunk))
    return [token for token in tokens if token]


def _to_pascal_identifier(raw: str, fallback: str) -> str:
    tokens = _split_identifier_tokens(raw)
    if not tokens:
        tokens = _split_identifier_tokens(fallback) or [fallback]
    return "".join(token[:1].upper() + token[1:].lower() for token in tokens)


def _to_unique_identifier(base: str, used: set[str]) -> str:
    candidate = base
    suffix = 2
    while candidate in used:
        candidate = f"{base}{suffix}"
        suffix += 1
    used.add(candidate)
    return candidate


def _extract_handler_identifier(handler: str | None) -> str | None:
    if handler is None:
        return None
    match = _HANDLER_IDENTIFIER.search(handler.strip())
    if not match:
        return None
    identifier = match.group(0).split(".")[-1]
    return identifier or None


def _normalize_endpoint_seed(endpoint: str | None) -> str | None:
    if endpoint is None:
        return None
    normalized = endpoint.strip()
    if not normalized:
        return None

    if "::" in normalized and "://" not in normalized:
        namespace, _, remainder = normalized.partition("::")
        namespace = namespace.strip().strip("/")
        remainder = remainder.strip().lstrip("/")
        normalized = "/".join(part for part in (namespace, remainder) if part)

    parsed = urlsplit(normalized)
    if parsed.scheme and parsed.netloc:
        normalized = parsed.path or "/"

    normalized = normalized.replace("\\", "/")
    normalized = normalized.split("?", 1)[0].split("#", 1)[0].strip()
    if not normalized:
        return None
    if not normalized.startswith("/"):
        normalized = f"/{normalized}"
    normalized = _MULTI_SLASH.sub("/", normalized)
    if len(normalized) > 1 and normalized.endswith("/"):
        normalized = normalized.rstrip("/")
    return normalized.strip("/")


def _event_action_base(event: EventIR, *, index: int) -> str:
    handler_identifier = _extract_handler_identifier(event.handler)
    if handler_identifier:
        seed = handler_identifier
    else:
        event_name = event.event_name or "event"
        node_seed = event.node_id or event.node_tag or f"node_{index}"
        seed = f"{event_name}_{node_seed}"
    return f"on{_to_pascal_identifier(seed, fallback=f'event_{index}')}"


def _transaction_action_base(transaction: TransactionIR, *, index: int) -> str:
    seed = transaction.transaction_id or transaction.node_id
    if seed:
        return f"request{_to_pascal_identifier(seed, fallback=f'transaction_{index}')}"

    endpoint_seed = _normalize_endpoint_seed(transaction.endpoint)
    if endpoint_seed:
        method_seed = (transaction.method or "request").strip() or "request"
        combined = f"{method_seed}_{endpoint_seed}"
        return f"request{_to_pascal_identifier(combined, fallback=f'transaction_{index}')}"

    return f"requestTransaction{index}"


def _binding_state_base(binding: BindingIR, *, index: int) -> str:
    seed = binding.binding_value.strip()
    if not seed:
        seed = binding.node_id or binding.binding_key or f"binding_{index}"
    return f"binding{_to_pascal_identifier(seed, fallback=f'binding_{index}')}"


def _plan_state_specs(bindings: list[BindingIR]) -> list[BehaviorStateSpec]:
    states: list[BehaviorStateSpec] = []
    used_state_keys: set[str] = set()
    first_seen_by_base: dict[str, BehaviorStateSpec] = {}

    for index, binding in enumerate(bindings, start=1):
        base_state_key = _binding_state_base(binding, index=index)
        duplicate_of_index: int | None = None
        duplicate_of_state_key: str | None = None

        if base_state_key in first_seen_by_base:
            winner = first_seen_by_base[base_state_key]
            duplicate_of_index = winner.index
            duplicate_of_state_key = winner.state_key

        state_key = _to_unique_identifier(base_state_key, used_state_keys)
        spec = BehaviorStateSpec(
            index=index,
            node_id=binding.node_id,
            binding_key=binding.binding_key,
            binding_value=binding.binding_value,
            state_key=state_key,
            base_state_key=base_state_key,
            duplicate_of_index=duplicate_of_index,
            duplicate_of_state_key=duplicate_of_state_key,
            source=binding.source,
        )
        states.append(spec)
        first_seen_by_base.setdefault(base_state_key, spec)

    return states


def _plan_action_specs(events: list[EventIR], transactions: list[TransactionIR]) -> list[BehaviorActionSpec]:
    actions: list[BehaviorActionSpec] = []
    used_action_names: set[str] = set()
    first_seen_by_base: dict[str, BehaviorActionSpec] = {}
    action_index = 0

    for event in events:
        action_index += 1
        base_action_name = _event_action_base(event, index=action_index)
        duplicate_of_index: int | None = None
        duplicate_of_action_name: str | None = None

        if base_action_name in first_seen_by_base:
            winner = first_seen_by_base[base_action_name]
            duplicate_of_index = winner.index
            duplicate_of_action_name = winner.action_name

        action_name = _to_unique_identifier(base_action_name, used_action_names)
        spec = BehaviorActionSpec(
            index=action_index,
            source_kind="event",
            action_name=action_name,
            base_action_name=base_action_name,
            event_name=event.event_name,
            handler=event.handler,
            duplicate_of_index=duplicate_of_index,
            duplicate_of_action_name=duplicate_of_action_name,
            source=event.source,
        )
        actions.append(spec)
        first_seen_by_base.setdefault(base_action_name, spec)

    for transaction in transactions:
        action_index += 1
        base_action_name = _transaction_action_base(transaction, index=action_index)
        duplicate_of_index: int | None = None
        duplicate_of_action_name: str | None = None

        if base_action_name in first_seen_by_base:
            winner = first_seen_by_base[base_action_name]
            duplicate_of_index = winner.index
            duplicate_of_action_name = winner.action_name

        action_name = _to_unique_identifier(base_action_name, used_action_names)
        spec = BehaviorActionSpec(
            index=action_index,
            source_kind="transaction",
            action_name=action_name,
            base_action_name=base_action_name,
            transaction_id=transaction.transaction_id,
            endpoint=transaction.endpoint,
            method=transaction.method,
            duplicate_of_index=duplicate_of_index,
            duplicate_of_action_name=duplicate_of_action_name,
            source=transaction.source,
        )
        actions.append(spec)
        first_seen_by_base.setdefault(base_action_name, spec)

    return actions


def plan_behavior_store_scaffold(screen: ScreenIR) -> BehaviorStorePlan:
    states = _plan_state_specs(screen.bindings)
    actions = _plan_action_specs(screen.events, screen.transactions)

    summary = BehaviorStoreSummary(
        total_bindings=len(screen.bindings),
        total_events=len(screen.events),
        total_transactions=len(screen.transactions),
        generated_state_keys=len(states),
        generated_actions=len(actions),
        duplicate_state_keys=sum(
            1 for state in states if state.duplicate_of_index is not None
        ),
        duplicate_actions=sum(
            1 for action in actions if action.duplicate_of_index is not None
        ),
    )
    return BehaviorStorePlan(states=states, actions=actions, summary=summary)


def _to_js_string(value: str) -> str:
    return json.dumps(value, ensure_ascii=False)


def _source_literal(source: SourceRef | None) -> str:
    if source is None:
        return "null"
    line_value = "null" if source.line is None else str(source.line)
    return (
        "{ "
        f"filePath: {_to_js_string(source.file_path)}, "
        f"nodePath: {_to_js_string(source.node_path)}, "
        f"line: {line_value} "
        "}"
    )


def _action_anchor_trigger(spec: BehaviorActionSpec) -> str:
    if spec.source_kind == "event":
        event_name = spec.event_name or "event"
        handler = spec.handler or ""
        return f"{event_name}:{handler}".strip(":")

    method = (spec.method or "").strip().upper()
    endpoint = (spec.endpoint or "").strip()
    pieces = [piece for piece in (method, endpoint) if piece]
    if pieces:
        return " ".join(pieces)
    return spec.transaction_id or "transaction"


def _render_actions_module(
    *,
    screen: ScreenIR,
    input_xml_path: str,
    actions: list[BehaviorActionSpec],
) -> str:
    lines = [
        "/* Generated by mifl-migrator gen-behavior-store. */",
        f"/* sourceXmlPath: {input_xml_path} */",
        f"/* duplicateActionPolicy: {DUPLICATE_ACTION_POLICY} */",
        "",
        "export interface ScreenBehaviorActionAnchor {",
        "  name: string;",
        '  sourceKind: "event" | "transaction";',
        "  trigger: string;",
        "  source: { filePath: string; nodePath: string; line: number | null } | null;",
        "  duplicateOfActionName?: string;",
        "}",
        "",
        "export const screenBehaviorActionAnchors: ScreenBehaviorActionAnchor[] = [",
    ]

    for spec in actions:
        lines.extend(
            [
                "  {",
                f"    name: {_to_js_string(spec.action_name)},",
                f"    sourceKind: {_to_js_string(spec.source_kind)},",
                f"    trigger: {_to_js_string(_action_anchor_trigger(spec))},",
                f"    source: {_source_literal(spec.source)},",
            ]
        )
        if spec.duplicate_of_action_name is not None:
            lines.append(
                f"    duplicateOfActionName: {_to_js_string(spec.duplicate_of_action_name)},"
            )
        lines.append("  },")

    lines.extend(["];", "", "export interface ScreenBehaviorActions {"])

    for spec in actions:
        action_type = "() => Promise<void>" if spec.source_kind == "transaction" else "() => void"
        lines.append(f"  {spec.action_name}: {action_type};")

    lines.extend(["}", "", "export function createScreenBehaviorActions(): ScreenBehaviorActions {"])
    lines.append("  return {")
    for spec in actions:
        if spec.source_kind == "transaction":
            lines.extend(
                [
                    f"    {spec.action_name}: async () => {{",
                    f"      // TODO: implement transaction anchor ({spec.action_name}).",
                    "    },",
                ]
            )
        else:
            lines.extend(
                [
                    f"    {spec.action_name}: () => {{",
                    f"      // TODO: implement event anchor ({spec.action_name}).",
                    "    },",
                ]
            )
    lines.extend(["  };", "}", ""])

    if not actions:
        lines = [
            "/* Generated by mifl-migrator gen-behavior-store. */",
            f"/* sourceXmlPath: {input_xml_path} */",
            f"/* duplicateActionPolicy: {DUPLICATE_ACTION_POLICY} */",
            "",
            "export interface ScreenBehaviorActionAnchor {",
            "  name: string;",
            '  sourceKind: "event" | "transaction";',
            "  trigger: string;",
            "  source: { filePath: string; nodePath: string; line: number | null } | null;",
            "  duplicateOfActionName?: string;",
            "}",
            "",
            "export const screenBehaviorActionAnchors: ScreenBehaviorActionAnchor[] = [];",
            "",
            "export interface ScreenBehaviorActions {}",
            "",
            "export function createScreenBehaviorActions(): ScreenBehaviorActions {",
            "  return {};",
            "}",
            "",
        ]

    return "\n".join(lines)


def _render_store_module(
    *,
    screen: ScreenIR,
    input_xml_path: str,
    states: list[BehaviorStateSpec],
    actions_import_stem: str,
) -> str:
    screen_pascal = _to_pascal_identifier(screen.screen_id, fallback="Screen")
    hook_name = f"use{screen_pascal}BehaviorStore"
    lines = [
        "/* Generated by mifl-migrator gen-behavior-store. */",
        f"/* sourceXmlPath: {input_xml_path} */",
        f"/* duplicateStatePolicy: {DUPLICATE_STATE_POLICY} */",
        "",
        'import { create } from "zustand";',
        "import {",
        "  createScreenBehaviorActions,",
        "  type ScreenBehaviorActions,",
        f'}} from "./{actions_import_stem}.actions";',
        "",
        "export interface ScreenBehaviorState {",
    ]

    for state in states:
        lines.append(f"  {state.state_key}: unknown;")

    lines.extend(
        [
            "}",
            "",
            "export type ScreenBehaviorStore = ScreenBehaviorState & ScreenBehaviorActions;",
            "",
            "function createInitialScreenBehaviorState(): ScreenBehaviorState {",
            "  return {",
        ]
    )

    for state in states:
        lines.append(f"    {state.state_key}: null,")

    lines.extend(
        [
            "  };",
            "}",
            "",
            f"export const {hook_name} = create<ScreenBehaviorStore>(() => ({{",
            "  ...createInitialScreenBehaviorState(),",
            "  ...createScreenBehaviorActions(),",
            "}));",
            "",
        ]
    )

    if not states:
        lines = [
            "/* Generated by mifl-migrator gen-behavior-store. */",
            f"/* sourceXmlPath: {input_xml_path} */",
            f"/* duplicateStatePolicy: {DUPLICATE_STATE_POLICY} */",
            "",
            'import { create } from "zustand";',
            "import {",
            "  createScreenBehaviorActions,",
            "  type ScreenBehaviorActions,",
            f'}} from "./{actions_import_stem}.actions";',
            "",
            "export interface ScreenBehaviorState {}",
            "",
            "export type ScreenBehaviorStore = ScreenBehaviorState & ScreenBehaviorActions;",
            "",
            f"export const {hook_name} = create<ScreenBehaviorStore>(() => ({{",
            "  ...createScreenBehaviorActions(),",
            "}));",
            "",
        ]

    return "\n".join(lines)


def _build_warnings(summary: BehaviorStoreSummary) -> list[str]:
    warnings: list[str] = []
    if summary.generated_actions == 0:
        warnings.append("No events or transactions found; generated action scaffold is empty.")
    if summary.generated_state_keys == 0:
        warnings.append("No bindings found; generated state scaffold is empty.")
    if summary.duplicate_actions > 0:
        warnings.append(
            f"Duplicate action base names resolved with suffixing: {summary.duplicate_actions}"
        )
    if summary.duplicate_state_keys > 0:
        warnings.append(
            f"Duplicate state key base names resolved with suffixing: {summary.duplicate_state_keys}"
        )
    return warnings


def generate_behavior_store_artifacts(
    *,
    screen: ScreenIR,
    input_xml_path: str,
    out_dir: str | Path,
) -> BehaviorStoreReport:
    out_root = Path(out_dir).resolve()
    screen_stem = _to_file_stem(screen.screen_id)
    out_behavior_dir = out_root / "src" / "behavior"
    out_behavior_dir.mkdir(parents=True, exist_ok=True)

    actions_file = out_behavior_dir / f"{screen_stem}.actions.ts"
    store_file = out_behavior_dir / f"{screen_stem}.store.ts"

    plan = plan_behavior_store_scaffold(screen)
    source_xml_path = str(Path(input_xml_path).resolve())

    actions_file.write_text(
        _render_actions_module(
            screen=screen,
            input_xml_path=source_xml_path,
            actions=plan.actions,
        ),
        encoding="utf-8",
    )
    store_file.write_text(
        _render_store_module(
            screen=screen,
            input_xml_path=source_xml_path,
            states=plan.states,
            actions_import_stem=screen_stem,
        ),
        encoding="utf-8",
    )

    return BehaviorStoreReport(
        screen_id=screen.screen_id,
        input_xml_path=source_xml_path,
        store_file=str(store_file),
        actions_file=str(actions_file),
        summary=plan.summary,
        states=plan.states,
        actions=plan.actions,
        warnings=_build_warnings(plan.summary),
    )


__all__ = [
    "BehaviorActionSpec",
    "BehaviorStateSpec",
    "BehaviorStorePlan",
    "BehaviorStoreReport",
    "BehaviorStoreSummary",
    "DUPLICATE_ACTION_POLICY",
    "DUPLICATE_STATE_POLICY",
    "generate_behavior_store_artifacts",
    "plan_behavior_store_scaffold",
]
