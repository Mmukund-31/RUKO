"""Multilingual warning-sign lexicons and a clause-level matcher with negation.

Covers English, romanised Hindi/Hinglish, romanised Telugu, Devanagari and
Telugu script. Prisma `codemix` output keeps English words (OTP, PIN, bank,
police...) in Latin script, so mixed transcripts match both pattern sets.

Latin patterns use word boundaries. Indic-script patterns are substring
matches, because Python's `\\b` is unreliable inside Indic words (vowel signs
are not word characters).
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# Slots that are warning signs, plus context-only slots.
SIGNS = ("otp", "credential", "remote", "money", "threat", "urgency", "authority", "secrecy", "lure", "id_request")
CONTEXT = ("identity", "org", "lost")

_LATIN: dict[str, str] = {
    "otp": r"\b(otp|o\.t\.p|one[- ]time[- ]password|verification code|6[- ]digit code|sms code)\b",
    "credential": r"\b(pin|upi pin|atm pin|m-?pin|cvv|password|passcode|net ?banking (login|password|details)|card number|card details|login details)\b",
    "remote": r"\b(any ?desk|team ?viewer|quick ?support|rust ?desk|airdroid|screen ?share|share (your |my |the )?screen|screen sharing|install(ed|ing)?|download (an |the |this )?app|apk|app download|click (on )?(the |this |a )?link|link (pe|par|pai|meeda) click)\b",
    "money": r"(₹|\b(transfer|send (the |some )?money|pay|paying|payment|deposit|fine|penalty|rupees|rs\.?|inr|upi|gpay|google pay|phone ?pe|paytm|paisa|paise|paisey|dabbulu|dabbu|amount|refund|security deposit|processing fee|fees?|charges|invest|investment|returns|lakh|thousand|bitcoin|crypto|gift card)\b)",
    "threat": r"\b(threat(en|ened|ening|s)?|arrest(ed)?|jail|police case|fir|case (will be|against|filed|registered)|legal action|warrant|block(ed)?|suspend(ed)?|freeze|frozen|deactivat\w*|seize[d]?|digital arrest|cancel(led)?|giraftar|giraftaar|dhamki|band ho|block ho|case kar|bedirinch\w*)\b",
    "urgency": r"\b(immediately|right now|right away|urgent(ly)?|within (\d+|one|two|five|ten|thirty) (minutes?|mins?|hours?)|today itself|by today|by tonight|tonight|before (today|tonight|evening)|(blocked|suspended|deactivated|closed|cancell?ed|disconnected) (today|tonight)|within (24|twenty[- ]four) hours|aaj hi|aaj raat|last chance|hurry|quickly|asap|turant|jaldi|foran|fauran|abhi ke abhi|ventane|ippude|twaraga|tondaraga)\b",
    "authority": r"\b(police|cbi|enforcement directorate|customs|rbi|reserve bank|income tax|cyber ?cell|crime branch|narcotics|ncb|trai|government|govt|officer|inspector|judge|court|sarkari|adhikari|(bank |card )?(security|fraud|risk|verification|kyc) (department|team|cell|division)|head office|bank (manager|official|officer))\b",
    "secrecy": r"\b(don'?t tell|do not tell|not to tell|keep (it|this) (a )?secret|secret|confidential|don'?t inform|tell no ?one|stay on (the )?(call|line)|don'?t (cut|disconnect|hang up)|mat batana|mat batao|kisi ko mat|kisi ko na|kisiko mat|cheppakandi|cheppoddu|cheppakudadhu|evvariki cheppa\w*)\b",
    "identity": r"\b(aadhaa?r|adhaa?r|pan( card| number)?|kyc|e-?kyc|voter id|passport|date of birth|dob|bank details|account number)\b",
    "lure": r"\b(lottery|prize|you (have )?won|winner|lucky draw|jackpot|reward points?|gift voucher|kbc|guaranteed returns?|double (your |the )?money|high returns?|daily profit|work from home|part[- ]time job|inaam|inam|lottery lagi)\b",
    "org": r"\b(bank|sbi|hdfc|icici|axis|kotak|credit card|debit card|atm|account|customer care|customer support|service|telecom|electricity|courier|fedex|delivery|sim)\b",
    "lost": r"(\b(i|we|maine|nenu|already)\b.{0,30}\b(shared|gave|given|sent|paid|transferred|told (them|him|her) (the )?(otp|pin))\b|\b(de diya|de diye|bhej diya|bhej diye|bata diya|cheppesa\w*|ichesa\w*|pampesa\w*|pampanu|kattesa\w*)\b)",
}

_INDIC: dict[str, str] = {
    "otp": r"(ओटीपी|ఓటీపీ|ఓటిపి)",
    "credential": r"(पिन|पासवर्ड|सीवीवी|పిన్|పాస్‌వర్డ్|పాస్వర్డ్|సీవీవీ)",
    "remote": r"(ऐप डाउनलोड|इंस्टॉल|स्क्रीन शेयर|लिंक पर क्लिक|ఇన్‌స్టాల్|ఇన్స్టాల్|స్క్రీన్ షేర్|లింక్|ఎనీడెస్క్|యాప్ డౌన్‌లోడ్|యాప్ డౌన్లోడ్)",
    "money": r"(पैसे|पैसा|रुपये|रुपए|ट्रांसफर|भेजो|भेजिए|भेजने|जुर्माना|फीस|भुगतान|निवेश|డబ్బు|రూపాయ|ట్రాన్స్‌ఫర్|ట్రాన్స్ఫర్|పంపండి|పంపమని|కట్టమని|కట్టండి|ఫైన్|జరిమానా|ఫీజు|పెట్టుబడి)",
    "threat": r"(गिरफ्तार|गिरफ़्तार|जेल|केस|बंद हो|बंद कर|ब्लॉक|धमकी|वारंट|अरेस्ट|అరెస్ట్|అరెస్టు|జైలు|కేసు|బ్లాక్|బెదిరి|వారెంట్|ఆపేస్తా|క్లోజ్ చేస్తా)",
    "urgency": r"(तुरंत|जल्दी|फ़ौरन|फौरन|अभी के अभी|आज ही|आज रात|ఈ రోజే|ఈరోజే|ఈ రాత్రి|వెంటనే|ఇప్పుడే|త్వరగా|అర్జెంట్|తొందర)",
    "authority": r"(पुलिस|सीबीआई|अधिकारी|इंस्पेक्टर|सरकार|आरबीआई|कस्टम|कोर्ट|పోలీస్|పోలీసు|సీబీఐ|అధికారి|ఇన్స్పెక్టర్|ప్రభుత్వ|ఆర్బీఐ|కస్టమ్స్|కోర్టు)",
    "secrecy": r"(मत बताना|मत बताओ|किसी को मत|किसी को न|गुप्त|कॉल मत काट|చెప్పొద్దు|చెప్పకండి|చెప్పకూడదు|ఎవరికీ చెప్ప|రహస్యం|కట్ చేయొద్దు)",
    "identity": r"(आधार|पैन कार्ड|केवाईसी|जन्म तिथि|खाता नंबर|ఆధార్|పాన్ కార్డ్|కేవైసీ|పుట్టిన తేదీ|అకౌంట్ నంబర్)",
    "lure": r"(इनाम|लॉटरी|मुनाफ़ा|मुनाफा|पैसे डबल|घर बैठे|బహుమతి|లాటరీ|గెలిచారు|లాభం|డబుల్|ఇంటి నుండి పని)",
    "org": r"(बैंक|खाता|अकाउंट|బ్యాంక్|బ్యాంకు|అకౌంట్|ఖాతా)",
    "lost": r"(दे दिया|दे दिए|भेज दिया|भेज दिए|बता दिया|చెప్పేశా|చెప్పేసా|ఇచ్చేశా|ఇచ్చేసా|పంపేశా|పంపాను|కట్టేశా)",
}

_DERIVED = ("id_request",)  # computed from identity + a request verb, no lexicon of its own
_PATTERNS = {
    slot: re.compile(_LATIN[slot] + "|" + _INDIC[slot], re.IGNORECASE)
    for slot in (*SIGNS, *CONTEXT)
    if slot not in _DERIVED
}

# "asking / share / tell / send" in English, Hinglish, Telugu (romanised + script) and Hindi.
_REQUEST = re.compile(
    r"\b(ask(s|ing|ed)?|share|send|tell|give|want(s|ing|ed)?|confirm|verify|chahiye|maang\w*|mang\w*|batao|bataiye|bhejo|dijiye|adug\w*|adig\w*|cheppa?mani|cheppandi|pampa?mani|ivvandi|ivvamani)\b"
    r"|माँग|मांग|बताओ|बताइए|भेजो|चाहिए|दीजिए|पूछ|అడుగు|అడిగ|చెప్పమ|పంపమ|ఇవ్వమ|ఇవ్వండి",
    re.IGNORECASE,
)

# Scam patterns, most specific first. Used for context: acknowledgement, tailored
# tips, question order and verification advice. A scheme alone is never a verdict.
SCHEME_ORDER = ("police", "card_block", "kyc", "prize", "investment", "refund", "job", "delivery", "utility")
_SCHEMES = {
    "police": r"\b(police|cbi|crime branch|customs|narcotics|ncb|digital arrest|arrest warrant|cyber ?cell|enforcement directorate|court notice)\b"
    r"|पुलिस|सीबीआई|क्राइम ब्रांच|डिजिटल अरेस्ट|పోలీస్|పోలీసు|సీబీఐ|డిజిటల్ అరెస్ట్",
    "card_block": r"\b(card|account|khata|a/c)\b.{0,50}\b(block\w*|suspend\w*|freez\w*|frozen|deactivat\w*|band|clos\w*)\b"
    r"|\b(block\w*|suspend\w*|freez\w*|deactivat\w*)\b.{0,30}\b(card|account)\b"
    r"|(कार्ड|खाता|अकाउंट|card|account).{0,40}(ब्लॉक|बंद)|(కార్డ్|కార్డు|అకౌంట్|ఖాతా|card|account).{0,40}(బ్లాక్|ఆపేస్తా|క్లోజ్)",
    "kyc": r"\b(kyc|e-?kyc|re-?kyc)\b|केवाईसी|కేవైసీ|\bupdate\b.{0,30}\b(aadhaa?r|pan)\b",
    "prize": r"\b(lottery|prize|you (have )?won|winner|lucky draw|jackpot|kbc|gift voucher|reward)\b|इनाम|लॉटरी|బహుమతి|లాటరీ|గెలిచారు",
    "investment": r"\b(invest\w*|trading|stock tips?|crypto|bitcoin|guaranteed returns?|double (your |the )?money|high returns?|daily profit)\b"
    r"|निवेश|मुनाफ़ा|मुनाफा|पैसे डबल|పెట్టుబడి|లాభం|డబుల్",
    "refund": r"\b(refund|sent (by )?mistake|wrong(ly)? (sent|transfer\w*)|galti se|return the money)\b|रिफंड|गलती से|ग़लती से|రీఫండ్|పొరపాటున",
    "job": r"\b(job offer|work from home|part[- ]time (job|work)|online job|task (job|based)|like (videos|youtube)|naukri)\b|नौकरी|घर बैठे|ఉద్యోగం|ఇంటి నుండి పని",
    "delivery": r"\b(courier|parcel|fedex|dhl|blue ?dart|package|delivery)\b|पार्सल|कूरियर|కొరియర్|పార్సెల్",
    "utility": r"\b(electricity|power (cut|bill|connection)|bijli|light bill|current bill|disconnect\w*|sim\b.{0,25}\b(block\w*|deactivat\w*|verification|band)|trai|5g upgrade)\b"
    r"|बिजली|सिम|కరెంట్|విద్యుత్|సిమ్",
}
_SCHEME_PATTERNS = {k: re.compile(v, re.IGNORECASE) for k, v in _SCHEMES.items()}


def detect_schemes(text: str) -> list[str]:
    return [k for k in SCHEME_ORDER if _SCHEME_PATTERNS[k].search(text)]


_GENUINE_Q = re.compile(
    r"\b(is (it|this|he|she|the caller|this call) (real|genuine|fake|a scam|true|legit)|real or fake|genuine or|asli hai|nakli|sach hai|nijama|nijamena|nijamenaa)\b"
    r"|असली है|नकली|सच है|నిజమేనా|నిజమా",
    re.IGNORECASE,
)
_ADVICE_Q = re.compile(
    r"\b(what (should|do|can) i (do|say)|what to (do|say)|how (do|can|should) i (check|verify)|kya karu|kya karoon|kya karun|kya bolu|kya karna chahiye|em cheyali|emi cheyali|ela check|em cheppali)\b"
    r"|क्या करूँ|क्या करूं|क्या करना|क्या बोलूँ|ఏం చేయాలి|ఏమి చేయాలి|ఏం చెప్పాలి",
    re.IGNORECASE,
)


def detect_intent(text: str) -> str | None:
    """The user asking RUKO a question rather than describing the call."""
    if _GENUINE_Q.search(text):
        return "genuine"
    if _ADVICE_Q.search(text):
        return "advice"
    return None

_NEGATION = re.compile(
    r"\b(not|never|didn'?t|did not|haven'?t|hasn'?t|won'?t|don'?t|no|nahi|nahin|nai|ledu|ledhu|kaadu|kadu|\w+aledu|\w+aledhu)\b"
    r"|नहीं|नही|లేదు|కాదు|లేదండి",
    re.IGNORECASE,
)
_CLAUSE_SPLIT = re.compile(
    r"[.;!?|।\n,]+|\b(but|however|though|lekin|magar|par|kani|kaani)\b|लेकिन|मगर|కానీ|కాని", re.IGNORECASE
)

YES = re.compile(
    r"\b(yes|yeah|yep|yup|haan|han|haa|ji haan|ji|avunu|avnu|aunu|asked|correct|right|sure|true)\b|हाँ|हां|जी|అవును|అడిగారు|అన్నారు",
    re.IGNORECASE,
)
UNSURE = re.compile(
    r"\b(don'?t know|not sure|no idea|pata nahi|pata nahin|maloom nahi|teliyadu|teliyadhu)\b|पता नहीं|मालूम नहीं|తెలియదు",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class Hit:
    slot: str
    negated: bool
    evidence: str  # the clause the match came from (trimmed)


def _clauses(text: str) -> list[str]:
    parts = _CLAUSE_SPLIT.split(text)
    return [p.strip() for p in parts if p and p.strip() and not _CLAUSE_SPLIT.fullmatch(p.strip())]


NEG_BEFORE = 6  # words before the match ("did not ask for OTP", "never ask for your OTP or PIN")
NEG_AFTER = 3  # words after the match (Hindi/Telugu verb-final: "OTP nahi maanga", "OTP adagaledu")


def _is_negated(clause: str, start: int, end: int) -> bool:
    # Secrecy phrases ("don't tell", "mat batana") contain negation words of
    # their own; blank them out so they never negate a neighbouring sign.
    masked = _PATTERNS["secrecy"].sub(lambda m: " " * len(m.group(0)), clause)
    before = masked[:start].split()[-NEG_BEFORE:]
    after = masked[end:].split()[:NEG_AFTER]
    return bool(_NEGATION.search(" ".join(before + after)))


def find_hits(text: str) -> list[Hit]:
    """Return every slot mentioned in `text`, with negation judged in a small
    word window around the match inside its clause."""
    hits: list[Hit] = []
    for clause in _clauses(text):
        for slot, pat in _PATTERNS.items():
            m = pat.search(clause)
            if not m:
                continue
            if slot == "secrecy":
                rest = clause[: m.start()].split()[-NEG_BEFORE:]
                negated = bool(_NEGATION.search(" ".join(rest)))
            else:
                negated = _is_negated(clause, m.start(), m.end())
            hits.append(Hit(slot, negated, clause[:160]))
            # Being asked FOR an ID number is a warning sign; merely mentioning it is not.
            if slot == "identity" and not re.search(r"kyc|केवाईसी|కేవైసీ", m.group(0), re.I) and _REQUEST.search(clause):
                hits.append(Hit("id_request", negated, clause[:160]))
    return hits


def answer_polarity(text: str) -> bool | None:
    """Interpret a short reply to a yes/no follow-up. None = unclear."""
    if UNSURE.search(text):
        return None
    yes = bool(YES.search(text))
    no = bool(_NEGATION.search(text))
    if yes and not no:
        return True
    if no and not yes:
        return False
    return None


_TELUGU = re.compile(r"[ఀ-౿]")
_DEVANAGARI = re.compile(r"[ऀ-ॿ]")
_KANNADA = re.compile(r"[ಀ-೿]")
_TAMIL = re.compile(r"[஀-௿]")
_MALAYALAM = re.compile(r"[ഀ-ൿ]")
_BENGALI = re.compile(r"[ঀ-৿]")
_GUJARATI = re.compile(r"[઀-૿]")
_GURMUKHI = re.compile(r"[਀-੿]")
_HINGLISH = re.compile(
    r"\b(hai|hain|nahi|nahin|kya|mujhe|mera|meri|mere|aap|aapka|paise|bol|bola|raha|rahe|rahi|kar|karo|keh|kaha|maanga|manga|batao|chahiye|abhi|woh|wo|unhone|haan)\b",
    re.IGNORECASE,
)
_TENGLISH = re.compile(
    r"\b(ledu|ledhu|cheppu|cheppandi|adigaru|adugutunnaru|naku|nenu|andi|chestha|chesthanu|chesaru|vallu|ani|antunnaru|dabbulu|avunu|enti|emi)\b",
    re.IGNORECASE,
)


def detect_language(text: str) -> str | None:
    """Best-effort script/lexicon detection for typed text. None = no signal."""
    if _TELUGU.search(text):
        return "te"
    if _DEVANAGARI.search(text):
        return "hi"
    for pat, code in (
        (_KANNADA, "kn"),
        (_TAMIL, "ta"),
        (_MALAYALAM, "ml"),
        (_BENGALI, "bn"),
        (_GUJARATI, "gu"),
        (_GURMUKHI, "pa"),
    ):
        if pat.search(text):
            return code
    te = len(_TENGLISH.findall(text))
    hi = len(_HINGLISH.findall(text))
    if te > hi and te >= 1:
        return "te"
    if hi >= 1:
        return "hi-en"
    if re.search(r"[A-Za-z]{2,}", text) and len(text.split()) >= 3:
        return "en"
    return None
