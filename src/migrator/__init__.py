"""MIPLATFORM migrator core package."""

from .models import ParseConfig, ParseReport
from .parser import ParseStrictError, parse_xml_file
from .preview_manifest import (
    ManifestContractError,
    ScreenManifestEntry,
    ScreensManifest,
    load_screens_manifest,
    load_screens_manifest_file,
)
from .ui_codegen import (
    UnsupportedUiEventBinding,
    UiCodegenReport,
    UiCodegenSummary,
    generate_ui_codegen_artifacts,
)
from .behavior_store_codegen import (
    BehaviorEventActionBinding,
    BehaviorStorePlan,
    BehaviorStoreReport,
    BehaviorStoreSummary,
    generate_behavior_store_artifacts,
    plan_behavior_store_scaffold,
    plan_event_action_bindings,
)
from .fidelity_audit import (
    FidelityAuditReport,
    FidelityAuditStrictError,
    FidelityAuditSummary,
    FidelityGeneratedNodeInventory,
    FidelityPositionStyleCoverageRisk,
    FidelitySourceNodeInventory,
    enforce_fidelity_audit_strict,
    generate_fidelity_audit_report,
)
from .preview_sync import (
    GeneratedScreenEntry,
    PreviewSyncReport,
    sync_preview_host,
)
from .runtime_wiring import RuntimeWiringContract, build_runtime_wiring_contract
from .validator import (
    compute_canonical_hash_pair,
    compute_roundtrip_mismatches,
    compute_roundtrip_structural_diff,
)

__all__ = [
    "ParseConfig",
    "ParseReport",
    "ParseStrictError",
    "ManifestContractError",
    "GeneratedScreenEntry",
    "PreviewSyncReport",
    "ScreenManifestEntry",
    "ScreensManifest",
    "BehaviorEventActionBinding",
    "BehaviorStorePlan",
    "BehaviorStoreReport",
    "BehaviorStoreSummary",
    "FidelityAuditReport",
    "FidelityAuditStrictError",
    "FidelityAuditSummary",
    "FidelityGeneratedNodeInventory",
    "FidelityPositionStyleCoverageRisk",
    "FidelitySourceNodeInventory",
    "RuntimeWiringContract",
    "UnsupportedUiEventBinding",
    "UiCodegenReport",
    "UiCodegenSummary",
    "build_runtime_wiring_contract",
    "compute_canonical_hash_pair",
    "compute_roundtrip_mismatches",
    "compute_roundtrip_structural_diff",
    "enforce_fidelity_audit_strict",
    "generate_behavior_store_artifacts",
    "generate_fidelity_audit_report",
    "generate_ui_codegen_artifacts",
    "load_screens_manifest",
    "load_screens_manifest_file",
    "parse_xml_file",
    "plan_behavior_store_scaffold",
    "plan_event_action_bindings",
    "sync_preview_host",
]
