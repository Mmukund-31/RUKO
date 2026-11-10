"""Deterministic, explainable scam-risk assessment.

Pure functions only: no I/O, no language-specific text. The conversation
layer turns a RiskResult into spoken words.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum

from .indicators import CONTEXT, SCHEME_ORDER, SIGNS, Hit


class Level(str, Enum):
    HIGH = "HIGH_RISK"
    SUSPICIOUS = "SUSPICIOUS"
    INSUFFICIENT = "INSUFFICIENT_INFORMATION"


# Weights are used to rank which sign to explain first, and as a supporting
# score. The level itself comes from the explicit rules in `assess`.
WEIGHTS = {
    "otp": 5,
    "credential": 5,
    "remote": 5,
    "money": 3,
    "threat": 2,
    "secrecy": 2,
    "authority": 1,
    "urgency": 1,
    "lure": 2,
    "id_request": 2,
}

# Slots that most change the outcome. "missing" lists which of these are unknown.
KEY_SLOTS = ("otp", "money", "remote", "credential")


SEVERITY = {5: "critical", 3: "high", 2: "medium", 1: "low"}

# Evidence strength: what the caller said (heard by Prisma) is stronger than the
# user's description of it, which is stronger than a bare "yes" to our question.
STRENGTH = {"CALLER": "direct", "USER": "reported", "ANSWER": "answer"}

EXPLAIN = {
    "otp": "Asking for an OTP: banks and officials never need it on a call.",
    "credential": "Asking for a PIN, CVV, password or card details.",
    "remote": "Asking to install an app, click a link or share the screen.",
    "money": "Asking for a payment, fine, fee or transfer.",
    "threat": "Threatening arrest, a case, or blocking an account or service.",
    "urgency": "Pressure to act immediately.",
    "authority": "Claiming to be police, government, court or a bank official.",
    "secrecy": "Asking to keep it secret or stay on the line.",
    "lure": "Offering a prize, job or unusually high returns.",
    "id_request": "Asking for Aadhaar, PAN, date of birth or account details.",
}


@dataclass
class Evidence:
    indicator: str
    speaker: str  # "CALLER" | "USER"
    text: str
    ts: float
    strength: str  # "direct" | "reported" | "answer"


@dataclass
class Slot:
    value: bool | None = None  # True present, False explicitly absent, None unknown
    evidence: list[str] = field(default_factory=list)
    records: list[Evidence] = field(default_factory=list)


@dataclass
class Facts:
    slots: dict[str, Slot] = field(default_factory=lambda: {s: Slot() for s in (*SIGNS, *CONTEXT)})
    schemes: list[str] = field(default_factory=list)  # scam patterns recognised so far

    def add_schemes(self, found: list[str]) -> list[str]:
        new = [x for x in found if x not in self.schemes]
        self.schemes.extend(new)
        return new

    @property
    def scheme(self) -> str:
        """Most specific recognised pattern (police beats card_block beats kyc ...)."""
        for k in SCHEME_ORDER:
            if k in self.schemes:
                return k
        if self.present("authority"):
            return "police"
        if self.present("org"):
            return "bank"
        return "general"

    def apply_hits(self, hits: list[Hit], speaker: str = "USER", ts: float | None = None) -> list[str]:
        """Merge matcher hits. A positive mention wins over a negative one in the
        same turn; a later explicit statement overrides an earlier one.
        Returns the slots that newly became True."""
        newly: list[str] = []
        by_slot: dict[str, list[Hit]] = {}
        for h in hits:
            by_slot.setdefault(h.slot, []).append(h)
        for slot, hs in by_slot.items():
            positive = [h for h in hs if not h.negated]
            s = self.slots[slot]
            if positive:
                if s.value is not True:
                    newly.append(slot)
                s.value = True
                for h in positive:
                    if h.evidence not in s.evidence:
                        s.evidence.append(h.evidence)
                        s.records.append(Evidence(slot, speaker, h.evidence, ts or time.time(), STRENGTH[speaker]))
            elif s.value is None:
                s.value = False
        return newly

    def set(self, slot: str, value: bool | None, evidence: str | None = None) -> bool:
        s = self.slots[slot]
        became_true = value is True and s.value is not True
        if value is not None:
            s.value = value
        if evidence and value and evidence not in s.evidence:
            s.evidence.append(evidence)
            s.records.append(Evidence(slot, "USER", evidence, time.time(), STRENGTH["ANSWER"]))
        return became_true

    def indicators(self) -> list[dict]:
        """Explainable view of every present warning sign, strongest first."""
        out = []
        for slot in SIGNS:
            s = self.slots[slot]
            if s.value is not True:
                continue
            recs = s.records
            strength = "direct" if any(r.strength == "direct" for r in recs) else (recs[0].strength if recs else "reported")
            out.append({
                "indicator": slot,
                "severity": SEVERITY[WEIGHTS[slot]],
                "strength": strength,
                "explanation": EXPLAIN[slot],
                "evidence": [{"speaker": r.speaker, "text": r.text, "ts": r.ts, "strength": r.strength} for r in recs[-3:]],
            })
        out.sort(key=lambda d: -WEIGHTS[d["indicator"]])
        return out

    def present(self, slot: str) -> bool:
        return self.slots[slot].value is True

    def unknown(self, slot: str) -> bool:
        return self.slots[slot].value is None


@dataclass
class RiskResult:
    level: Level
    score: int
    signs: list[str]  # present warning signs, most important first
    evidence: list[str]
    missing: list[str]
    main_reason: str | None  # top sign, or a context reason
    action: str  # action key, rendered by responses.py
    loss_reported: bool
    scheme: str  # recognised scam pattern, or "general"


def assess(f: Facts) -> RiskResult:
    p = f.present
    signs = sorted((s for s in SIGNS if p(s)), key=lambda s: -WEIGHTS[s])
    score = sum(WEIGHTS[s] for s in signs)
    pressure = p("threat") or p("urgency") or p("authority") or p("secrecy")

    if (
        p("otp")
        or p("credential")
        or p("remote")
        or (p("money") and (pressure or p("lure")))  # pressure, or an advance fee for a "prize"/"job"/"returns"
        or (p("id_request") and pressure)
        or (p("threat") and p("authority") and p("secrecy"))
    ):
        level = Level.HIGH
    elif signs:
        level = Level.SUSPICIOUS
    else:
        level = Level.INSUFFICIENT

    if p("lost"):
        action = "report_now"
    elif level is Level.HIGH:
        # Act on what the caller is trying to get, not on the loudest sign.
        action = next(
            (a for slot, a in (("otp", "no_otp"), ("credential", "no_otp"), ("remote", "no_remote"),
                               ("money", "no_money"), ("id_request", "no_id")) if p(slot)),
            "no_money",
        )
    elif level is Level.SUSPICIOUS:
        action = "verify"
    else:
        action = "verify_soft"

    evidence: list[str] = []
    for s in signs:
        for e in f.slots[s].evidence:
            if e not in evidence:
                evidence.append(e)

    return RiskResult(
        level=level,
        score=score,
        signs=signs,
        evidence=evidence[:5],
        missing=[s for s in KEY_SLOTS if f.unknown(s)],
        main_reason=signs[0] if signs else ("identity" if p("identity") else None),
        action=action,
        loss_reported=p("lost"),
        scheme=f.scheme,
    )


# Follow-up priority per scam pattern: ask what most changes the assessment.
FOLLOWUP_ORDER = {
    "police": ("money", "secrecy", "remote", "otp"),
    "card_block": ("otp", "remote", "money"),
    "bank": ("otp", "remote", "money"),
    "kyc": ("otp", "remote", "money", "id_request"),
    "prize": ("money", "otp", "credential"),
    "investment": ("money", "remote", "urgency"),
    "refund": ("money", "remote", "otp"),
    "job": ("money", "remote", "otp"),
    "delivery": ("money", "otp", "threat"),
    "utility": ("money", "remote", "otp"),
    "general": ("otp", "money", "remote", "threat", "secrecy"),
}

# Some questions ask about two things at once ("card number, CVV or OTP?").
# A "no" clears both slots; a "yes" sets the first.
COVERS = {("card_block", "otp"): ("credential",), ("bank", "otp"): ("credential",), ("kyc", "otp"): ("credential",)}


def covered(scheme: str, slot: str) -> tuple[str, ...]:
    return COVERS.get((scheme, slot), ())


def next_followup(f: Facts, asked: list[str]) -> str | None:
    for slot in FOLLOWUP_ORDER[f.scheme]:
        if slot in asked or not f.unknown(slot):
            continue
        return slot
    return None
