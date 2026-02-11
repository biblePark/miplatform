from __future__ import annotations

from dataclasses import dataclass
import re

_NON_ALNUM = re.compile(r"[^0-9A-Za-z]+")
_CAMEL_TOKEN = re.compile(r"[A-Z]+(?=[A-Z][a-z]|[0-9]|$)|[A-Z]?[a-z]+|[0-9]+")


def _split_identifier_tokens(raw: str) -> list[str]:
    normalized = _NON_ALNUM.sub(" ", raw).strip()
    if not normalized:
        return []

    tokens: list[str] = []
    for chunk in normalized.split():
        tokens.extend(_CAMEL_TOKEN.findall(chunk))
    return [token for token in tokens if token]


def to_pascal_identifier(raw: str, *, fallback: str) -> str:
    tokens = _split_identifier_tokens(raw)
    if not tokens:
        tokens = _split_identifier_tokens(fallback) or [fallback]
    return "".join(token[:1].upper() + token[1:].lower() for token in tokens)


def to_file_stem(raw: str) -> str:
    chunks = [chunk.lower() for chunk in _NON_ALNUM.split(raw) if chunk]
    return "-".join(chunks) if chunks else "screen"


def to_component_name(raw: str) -> str:
    chunks = [chunk for chunk in _NON_ALNUM.split(raw) if chunk]
    if not chunks:
        return "GeneratedScreen"

    component = "".join(chunk[:1].upper() + chunk[1:] for chunk in chunks)
    if component[0].isdigit():
        component = f"Screen{component}"
    if component.lower().endswith("screen"):
        return component
    return f"{component}Screen"


@dataclass(slots=True)
class RuntimeWiringContract:
    screen_id: str
    screen_file_stem: str
    screen_component_name: str
    behavior_store_hook_name: str
    behavior_store_import_from_screen: str
    behavior_store_file_name: str
    behavior_actions_file_name: str
    behavior_actions_import_from_store: str


def build_runtime_wiring_contract(screen_id: str) -> RuntimeWiringContract:
    stem = to_file_stem(screen_id)
    screen_pascal = to_pascal_identifier(screen_id, fallback="Screen")
    return RuntimeWiringContract(
        screen_id=screen_id,
        screen_file_stem=stem,
        screen_component_name=to_component_name(screen_id),
        behavior_store_hook_name=f"use{screen_pascal}BehaviorStore",
        behavior_store_import_from_screen=f"../behavior/{stem}.store",
        behavior_store_file_name=f"{stem}.store.ts",
        behavior_actions_file_name=f"{stem}.actions.ts",
        behavior_actions_import_from_store=f"./{stem}.actions",
    )


__all__ = [
    "RuntimeWiringContract",
    "build_runtime_wiring_contract",
    "to_component_name",
    "to_file_stem",
    "to_pascal_identifier",
]
