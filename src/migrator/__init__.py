"""MIPLATFORM migrator core package."""

from .models import ParseConfig, ParseReport
from .parser import ParseStrictError, parse_xml_file
from .validator import (
    compute_canonical_hash_pair,
    compute_roundtrip_mismatches,
    compute_roundtrip_structural_diff,
)

__all__ = [
    "ParseConfig",
    "ParseReport",
    "ParseStrictError",
    "compute_canonical_hash_pair",
    "compute_roundtrip_mismatches",
    "compute_roundtrip_structural_diff",
    "parse_xml_file",
]
