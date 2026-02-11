from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
import json
from pathlib import Path
import re
from typing import Any
from urllib.parse import urlsplit

from .models import ScreenIR, SourceRef, TransactionIR

MAPPING_STATUS_SUCCESS = "success"
MAPPING_STATUS_FAILURE = "failure"
MAPPING_STATUS_UNSUPPORTED = "unsupported"

SUPPORTED_HTTP_METHODS = {"GET", "POST", "PUT", "PATCH", "DELETE"}
_NON_ALNUM = re.compile(r"[^0-9A-Za-z]+")
_MULTI_SLASH = re.compile(r"/{2,}")
DUPLICATE_ROUTE_POLICY = "route_key(method, normalized_endpoint):first_seen_wins"


@dataclass(slots=True)
class ApiMappingSummary:
    total_transactions: int
    mapped_success: int
    mapped_failure: int
    unsupported: int


@dataclass(slots=True)
class TransactionApiMapping:
    index: int
    transaction_id: str | None
    node_id: str | None
    endpoint: str | None
    method: str | None
    status: str
    reason: str | None
    route_method: str | None = None
    route_path: str | None = None
    service_function: str | None = None
    duplicate_of_index: int | None = None
    duplicate_of_transaction_id: str | None = None
    source: SourceRef | None = None


@dataclass(slots=True)
class ApiMappingPlan:
    results: list[TransactionApiMapping]
    summary: ApiMappingSummary


@dataclass(slots=True)
class ApiMappingReport:
    screen_id: str
    input_xml_path: str
    route_file: str
    service_file: str
    summary: ApiMappingSummary
    results: list[TransactionApiMapping]
    duplicate_policy: str = DUPLICATE_ROUTE_POLICY
    warnings: list[str] = field(default_factory=list)
    generated_at_utc: str = field(default_factory=lambda: datetime.now(UTC).isoformat())

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _normalize_method(method: str | None) -> str | None:
    if method is None:
        return None
    normalized = method.strip().upper()
    return normalized or None


def _normalize_script_endpoint(endpoint: str) -> str:
    normalized = endpoint.strip()

    if "::" in normalized and "://" not in normalized:
        namespace, _, remainder = normalized.partition("::")
        namespace = namespace.strip().strip("/")
        remainder = remainder.strip().lstrip("/")
        normalized = "/".join(part for part in (namespace, remainder) if part)

    parsed = urlsplit(normalized)
    if parsed.scheme and parsed.netloc:
        normalized = parsed.path or "/"

    return normalized


def _normalize_endpoint(endpoint: str | None, *, node_tag: str | None = None) -> str | None:
    if endpoint is None:
        return None
    normalized = endpoint.strip()
    if not normalized:
        return None

    if (node_tag or "").lower() == "scripttransactioncall":
        normalized = _normalize_script_endpoint(normalized)

    normalized = normalized.replace("\\", "/")
    normalized = normalized.split("?", 1)[0].split("#", 1)[0].strip()
    if not normalized:
        return None
    if not normalized.startswith("/"):
        normalized = f"/{normalized}"
    normalized = _MULTI_SLASH.sub("/", normalized)
    if len(normalized) > 1 and normalized.endswith("/"):
        normalized = normalized.rstrip("/")
    return normalized


def _to_js_identifier(raw: str, fallback: str) -> str:
    chunks = [chunk for chunk in _NON_ALNUM.split(raw) if chunk]
    if not chunks:
        chunks = [fallback]

    head = chunks[0].lower()
    tail = "".join(chunk[:1].upper() + chunk[1:].lower() for chunk in chunks[1:])
    ident = f"{head}{tail}"
    if not ident:
        ident = fallback
    if ident[0].isdigit():
        ident = f"tx{ident}"
    return ident


def _allocate_unique_identifier(base: str, used: set[str]) -> str:
    candidate = base
    suffix = 2
    while candidate in used:
        candidate = f"{base}{suffix}"
        suffix += 1
    used.add(candidate)
    return candidate


def _service_name_seed(
    transaction: TransactionIR,
    *,
    index: int,
    method: str,
    endpoint: str,
) -> str:
    base_id = transaction.transaction_id or transaction.node_id
    if transaction.node_tag == "ScriptTransactionCall":
        endpoint_seed = endpoint.lstrip("/") or f"transaction_{index}"
        if base_id:
            return f"{base_id}_{method}_{endpoint_seed}"
        return f"{method}_{endpoint_seed}"
    return base_id or f"transaction_{index}"


def _render_route_stub(service_stem: str, mapped: list[TransactionApiMapping]) -> str:
    lines = [
        '"use strict";',
        "",
        'const express = require("express");',
        f'const service = require("../services/{service_stem}.service");',
        "",
        "const router = express.Router();",
        "",
    ]

    if not mapped:
        lines.append("// No transactions were eligible for automatic route mapping.")
        lines.append("")
    else:
        for item in mapped:
            tx_label = item.transaction_id or item.node_id or f"transaction_{item.index}"
            lines.extend(
                [
                    f"// Source transaction: {tx_label}",
                    f"router.{item.route_method}({json.dumps(item.route_path)}, async (req, res, next) => {{",
                    "  try {",
                    f"    const payload = await service.{item.service_function}(req);",
                    "    res.json(payload);",
                    "  } catch (error) {",
                    "    next(error);",
                    "  }",
                    "});",
                    "",
                ]
            )

    lines.extend(["module.exports = router;", ""])
    return "\n".join(lines)


def _render_service_stub(mapped: list[TransactionApiMapping]) -> str:
    lines = ['"use strict";', ""]

    if not mapped:
        lines.extend(
            [
                "// No mapped transactions. Add handlers after manual mapping decisions.",
                "",
                "module.exports = {};",
                "",
            ]
        )
        return "\n".join(lines)

    for item in mapped:
        tx_label = item.transaction_id or item.node_id or f"transaction_{item.index}"
        lines.extend(
            [
                f"async function {item.service_function}(req) {{",
                f"  // TODO: Implement integration for transaction {tx_label}.",
                "  return {",
                "    ok: false,",
                '    message: "TODO: implement service handler",',
                f"    transactionId: {json.dumps(tx_label)},",
                "  };",
                "}",
                "",
            ]
        )

    exported = ", ".join(item.service_function for item in mapped if item.service_function)
    lines.extend([f"module.exports = {{ {exported} }};", ""])
    return "\n".join(lines)


def _to_file_stem(raw: str) -> str:
    chunks = [chunk.lower() for chunk in _NON_ALNUM.split(raw) if chunk]
    return "-".join(chunks) if chunks else "screen"


def _build_warning_messages(summary: ApiMappingSummary) -> list[str]:
    warnings: list[str] = []
    if summary.mapped_failure:
        warnings.append(f"Mapping failures: {summary.mapped_failure}")
    if summary.unsupported:
        warnings.append(f"Unsupported transaction mappings: {summary.unsupported}")
    return warnings


def plan_transaction_api_mapping(transactions: list[TransactionIR]) -> ApiMappingPlan:
    results: list[TransactionApiMapping] = []
    used_route_keys: dict[tuple[str, str], TransactionApiMapping] = {}
    used_service_functions: set[str] = set()
    mapped_success = 0
    mapped_failure = 0
    unsupported = 0

    for index, transaction in enumerate(transactions, start=1):
        method = _normalize_method(transaction.method)
        endpoint = _normalize_endpoint(transaction.endpoint, node_tag=transaction.node_tag)

        if endpoint is None:
            mapped_failure += 1
            results.append(
                TransactionApiMapping(
                    index=index,
                    transaction_id=transaction.transaction_id,
                    node_id=transaction.node_id,
                    endpoint=endpoint,
                    method=method,
                    status=MAPPING_STATUS_FAILURE,
                    reason="missing_endpoint",
                    source=transaction.source,
                )
            )
            continue

        if method is None:
            mapped_failure += 1
            results.append(
                TransactionApiMapping(
                    index=index,
                    transaction_id=transaction.transaction_id,
                    node_id=transaction.node_id,
                    endpoint=endpoint,
                    method=method,
                    status=MAPPING_STATUS_FAILURE,
                    reason="missing_method",
                    source=transaction.source,
                )
            )
            continue

        if method not in SUPPORTED_HTTP_METHODS:
            unsupported += 1
            results.append(
                TransactionApiMapping(
                    index=index,
                    transaction_id=transaction.transaction_id,
                    node_id=transaction.node_id,
                    endpoint=endpoint,
                    method=method,
                    status=MAPPING_STATUS_UNSUPPORTED,
                    reason=f"unsupported_http_method:{method}",
                    source=transaction.source,
                )
            )
            continue

        route_key = (method, endpoint)
        if route_key in used_route_keys:
            winner = used_route_keys[route_key]
            mapped_failure += 1
            results.append(
                TransactionApiMapping(
                    index=index,
                    transaction_id=transaction.transaction_id,
                    node_id=transaction.node_id,
                    endpoint=endpoint,
                    method=method,
                    status=MAPPING_STATUS_FAILURE,
                    reason=f"duplicate_route:{method}:{endpoint}",
                    route_method=method.lower(),
                    route_path=endpoint,
                    duplicate_of_index=winner.index,
                    duplicate_of_transaction_id=winner.transaction_id,
                    source=transaction.source,
                )
            )
            continue

        raw_function_name = _service_name_seed(
            transaction,
            index=index,
            method=method,
            endpoint=endpoint,
        )
        service_function = _allocate_unique_identifier(
            _to_js_identifier(raw_function_name, fallback=f"transaction{index}"),
            used_service_functions,
        )

        mapped_success += 1
        mapping = TransactionApiMapping(
            index=index,
            transaction_id=transaction.transaction_id,
            node_id=transaction.node_id,
            endpoint=endpoint,
            method=method,
            status=MAPPING_STATUS_SUCCESS,
            reason=None,
            route_method=method.lower(),
            route_path=endpoint,
            service_function=service_function,
            source=transaction.source,
        )
        results.append(mapping)
        used_route_keys[route_key] = mapping

    summary = ApiMappingSummary(
        total_transactions=len(transactions),
        mapped_success=mapped_success,
        mapped_failure=mapped_failure,
        unsupported=unsupported,
    )
    return ApiMappingPlan(results=results, summary=summary)


def generate_api_mapping_artifacts(
    *,
    screen: ScreenIR,
    input_xml_path: str,
    out_dir: str | Path,
) -> ApiMappingReport:
    plan = plan_transaction_api_mapping(screen.transactions)
    mapped = [item for item in plan.results if item.status == MAPPING_STATUS_SUCCESS]

    out_root = Path(out_dir).resolve()
    screen_stem = _to_file_stem(screen.screen_id)
    route_file = out_root / "src" / "routes" / f"{screen_stem}.routes.js"
    service_file = out_root / "src" / "services" / f"{screen_stem}.service.js"

    route_file.parent.mkdir(parents=True, exist_ok=True)
    service_file.parent.mkdir(parents=True, exist_ok=True)
    route_file.write_text(_render_route_stub(screen_stem, mapped), encoding="utf-8")
    service_file.write_text(_render_service_stub(mapped), encoding="utf-8")

    return ApiMappingReport(
        screen_id=screen.screen_id,
        input_xml_path=str(Path(input_xml_path).resolve()),
        route_file=str(route_file),
        service_file=str(service_file),
        summary=plan.summary,
        results=plan.results,
        warnings=_build_warning_messages(plan.summary),
    )
