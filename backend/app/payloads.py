"""Shared JSON shapes for risk (used by HTTP turns and live WebSocket events)."""

from __future__ import annotations

from .conversation.responses import summary
from .risk import Facts, RiskResult


def risk_dict(lang: str, r: RiskResult, facts: Facts) -> dict:
    return {
        "level": r.level.value,
        "score": r.score,
        "signs": r.signs,
        "evidence": r.evidence,
        "missing": r.missing,
        "main_reason": r.main_reason,
        "action": r.action,
        "loss_reported": r.loss_reported,
        "scheme": r.scheme,
        "indicators": facts.indicators(),
        **summary(lang, r),
    }
