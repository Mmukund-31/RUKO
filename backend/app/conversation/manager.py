"""Conversation manager: one turn in, one short spoken reply out.

Flow per turn: language resolution -> slot extraction (matcher hits, or a
yes/no answer to the last question) -> risk assessment -> either one follow-up
question (with at most one tip) or the final assessment.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field

from ..risk import (
    Facts, Level, RiskResult, answer_polarity, assess, covered, detect_intent, detect_language, detect_schemes,
    find_hits, next_followup,
)
from ..risk.indicators import SIGNS
from . import responses as R

MAX_FOLLOWUPS = 3
SHORT_ANSWER_WORDS = 6


@dataclass
class Turn:
    role: str  # "user" | "ruko"
    text: str
    source: str = "text"  # "text" | "voice" | "ruko"


@dataclass
class TranscriptRecord:
    speaker: str  # "CALLER" | "USER"
    text: str
    ts: float
    language: str | None = None
    final: bool = True
    segment_id: str | None = None


@dataclass
class Session:
    id: str = field(default_factory=lambda: uuid.uuid4().hex)
    created: float = field(default_factory=time.time)
    touched: float = field(default_factory=time.time)
    language: str | None = None  # resolved language for replies
    facts: Facts = field(default_factory=Facts)
    asked: list[str] = field(default_factory=list)
    tipped: set[str] = field(default_factory=set)
    acked: set[str] = field(default_factory=set)
    asked_scheme: dict[str, str] = field(default_factory=dict)
    history: list[Turn] = field(default_factory=list)
    done: bool = False
    # V2 live call: separate transcript log + alert state
    transcripts: list[TranscriptRecord] = field(default_factory=list)
    preferred_language: str = "auto"
    alerted: set[str] = field(default_factory=set)
    last_alert_ts: float = float("-inf")
    last_alert_critical: bool = False
    last_level: str | None = None
    voice_alerts: bool = True

    @property
    def last_question(self) -> str | None:
        return self.asked[-1] if self.asked else None

    def user_text(self) -> str:
        return " ".join(t.text for t in self.history if t.role == "user")


@dataclass
class TurnOutcome:
    reply: str
    language: str
    risk: RiskResult
    followup: str | None
    done: bool


def resolve_language(session: Session, choice: str, text: str, stt_detected: str | None) -> str:
    """Explicit choice wins. With 'auto', use Prisma's detected language (or
    script detection for typed text) and keep the session language for short
    answers like 'yes'/'ledu' that carry little signal."""
    if choice and choice != "auto":
        return choice
    if stt_detected:
        detected: str | None = stt_detected.split("-")[0]
        if detected == "hi":
            latin = sum(c.isascii() and c.isalpha() for c in text)
            letters = sum(c.isalpha() for c in text) or 1
            detected = "hi-en" if latin / letters > 0.6 else "hi"
    else:
        detected = detect_language(text)
    short = len(text.split()) <= SHORT_ANSWER_WORDS
    if session.language and short and detected in (None, "en"):
        return session.language
    return detected or session.language or "en"


def handle_turn(
    session: Session, text: str, choice: str = "auto", stt_detected: str | None = None, source: str = "text"
) -> TurnOutcome:
    session.touched = time.time()
    text = (text or "").strip()
    lang = resolve_language(session, choice, text, stt_detected)
    session.language = lang

    if not text:
        risk = assess(session.facts)
        reply = R.t(lang, "empty")
        session.history.append(Turn("ruko", reply, "ruko"))
        return TurnOutcome(reply, lang, risk, session.last_question, session.done)

    session.history.append(Turn("user", text, source))
    session.transcripts.append(TranscriptRecord("USER", text, time.time(), lang))
    f = session.facts

    hits = find_hits(text)
    new_schemes = f.add_schemes(detect_schemes(text))
    newly = f.apply_hits(hits, "USER")
    intent = detect_intent(text)

    # A short reply to our last question fills that slot when it didn't
    # mention the slot explicitly ("yes", "haan", "ledu", "no they didn't").
    q = session.last_question
    if q and not intent:
        also = covered(session.asked_scheme.get(q, "general"), q)
        stated_other_sign = any(h.slot in SIGNS and not h.negated for h in hits)
        # "Yes, they want a fee" answers with a statement: trust the statement, not the bare "yes".
        if (
            not any(h.slot == q or h.slot in also for h in hits)
            and not stated_other_sign
            and (len(text.split()) <= SHORT_ANSWER_WORDS or not hits)
        ):
            pol = answer_polarity(text)
            if pol is not None and f.set(q, pol, f"{q}: {text[:80]}"):
                newly.append(q)
            if pol is False:
                for c in also:
                    f.set(c, False)

    risk = assess(f)
    scheme = f.scheme
    was_done = session.done

    # Decide: final assessment, or one more question.
    followup = None
    if not (risk.level is Level.HIGH or risk.loss_reported):
        if len(session.asked) < MAX_FOLLOWUPS:
            followup = next_followup(f, session.asked)
    if followup:
        session.asked.append(followup)
        session.asked_scheme[followup] = scheme
    question = R.question(lang, followup, scheme) if followup else None

    if intent:
        # "Is this real?" / "What should I do?" -> current verdict, then keep going.
        reply = " ".join(p for p in (R.t(lang, intent), R.status_text(lang, risk), question) if p)
        session.done = followup is None
    elif was_done and not newly and not new_schemes:
        # Nothing new after the assessment: don't repeat the whole verdict.
        reply = " ".join(p for p in (R.t(lang, f"lvl_{risk.level.value}"), question or R.t(lang, "more")) if p)
    elif followup is None:
        session.done = True
        reply = R.final_text(lang, risk)
    else:
        # Lead with what we understood (the scam pattern), else one relevant tip.
        lead = None
        if new_schemes and scheme not in session.acked and R.ack(lang, scheme):
            lead = R.ack(lang, scheme)
            session.acked.add(scheme)
            session.tipped.update(s for s in newly if s in ("threat", "lure"))  # the ack already covers these
        if lead is None:
            tip_slot, lead = R.tip_for(lang, newly, session.tipped, scheme)
            if tip_slot:
                session.tipped.add(tip_slot)
        if lead is None and len(session.history) <= 1:
            lead = R.t(lang, "ack")
        reply = " ".join(p for p in (lead, question) if p)

    session.history.append(Turn("ruko", reply, "ruko"))
    return TurnOutcome(reply, lang, risk, followup, session.done)


# ---------------------------------------------------------------- V2: caller speech

@dataclass
class CallerOutcome:
    record: TranscriptRecord
    newly: list[str]
    risk: RiskResult
    level_changed: bool


DEDUPE_WINDOW_S = 5.0


def handle_caller_statement(
    session: Session, text: str, language: str | None = None, segment_id: str | None = None, now: float | None = None
) -> CallerOutcome | None:
    """A FINAL caller transcript from Prisma realtime. Returns None for duplicates/empty."""
    now = now or time.time()
    text = (text or "").strip()
    if not text:
        return None
    for r in reversed(session.transcripts[-20:]):
        if r.speaker != "CALLER":
            continue
        if segment_id and r.segment_id == segment_id:
            return None
        if r.text == text and now - r.ts < DEDUPE_WINDOW_S:
            return None
    rec = TranscriptRecord("CALLER", text, now, language, True, segment_id)
    session.transcripts.append(rec)
    session.touched = now
    f = session.facts
    f.add_schemes(detect_schemes(text))
    # "We have sent an OTP" from the caller is not the USER reporting a loss: only the user can report that.
    hits = [h for h in find_hits(text) if h.slot != "lost"]
    newly = f.apply_hits(hits, "CALLER", now)
    risk = assess(f)
    changed = risk.level.value != session.last_level
    session.last_level = risk.level.value
    return CallerOutcome(rec, newly, risk, changed)


ALERT_COOLDOWN_S = 10.0
CRITICAL_COOLDOWN_S = 4.0
# Signs worth interrupting for, most severe first. authority/urgency alone never speak.
ALERT_ORDER = ("otp", "credential", "remote", "money", "id_request", "secrecy", "lure", "threat")
CRITICAL = ("otp", "credential", "remote")


def alert_language(session: Session, caller_lang: str | None) -> str:
    if session.preferred_language and session.preferred_language != "auto":
        return session.preferred_language
    if session.language:
        return session.language
    if caller_lang:
        return caller_lang.split("-")[0]
    return "en"


def decide_alert(session: Session, out: CallerOutcome, now: float | None = None) -> tuple[str | None, str | None]:
    """At most one short spoken alert per caller statement, deduplicated and throttled.
    Returns (indicator, text) or (None, None). Unspoken signs stay pending."""
    from .context_text import ALERTS

    now = now or time.time()
    pending = [s for s in ALERT_ORDER if session.facts.present(s) and s not in session.alerted]
    needs_high = out.risk.level is Level.HIGH and "high" not in session.alerted
    if not pending and not needs_high:
        return None, None
    sign = pending[0] if pending else None
    critical = sign in CRITICAL
    since = now - session.last_alert_ts
    limit = CRITICAL_COOLDOWN_S if (critical and not session.last_alert_critical) else ALERT_COOLDOWN_S
    if since < limit:
        return None, None
    tl = R.text_language(alert_language(session, out.record.language))
    parts = []
    if sign:
        parts.append(ALERTS[tl][sign])
        session.alerted.update(pending)  # one alert covers everything pending at once
    if needs_high:
        parts.append(ALERTS[tl]["high"])
        session.alerted.add("high")
    session.last_alert_ts = now
    session.last_alert_critical = critical
    return sign or "high", " ".join(parts)
