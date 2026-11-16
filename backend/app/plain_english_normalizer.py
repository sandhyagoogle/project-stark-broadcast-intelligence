"""
Plain-English Normalizer for Project Stark / CourtVision Rules.
Delegates to the canonical `rule_engine.sanitize_and_enrich_rule` pipeline so every
rule is NCAA-accurate, Title-Cased, free of em/en dashes and raw enum codes, and
includes a concise `plain_english_tip` for viewers unfamiliar with basketball without
polluting `trigger_condition` with repetitive inline boilerplate.
"""

from __future__ import annotations

from typing import Any

from .services.rule_engine import sanitize_and_enrich_rule


def normalize_rule_for_non_basketball_viewers(rule: dict[str, Any]) -> dict[str, Any]:
    """Return a sanitized, plain-English rule dictionary ready for UI, LLM, and SKILL.md export."""
    return sanitize_and_enrich_rule(rule)
