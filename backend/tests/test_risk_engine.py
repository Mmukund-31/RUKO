import pytest

from app.risk import Facts, Level, assess, find_hits
from app.risk.indicators import answer_polarity, detect_language


def facts_from(*texts: str) -> Facts:
    f = Facts()
    for t in texts:
        f.apply_hits(find_hits(t))
    return f


def level(*texts: str) -> Level:
    return assess(facts_from(*texts)).level


# --- context, not keywords -------------------------------------------------

def test_aadhaar_mention_alone_is_not_high_risk():
    assert level("The caller mentioned my Aadhaar card") is Level.INSUFFICIENT


def test_bank_mention_alone_is_not_a_warning_sign():
    assert level("Someone from my bank called about my account") is Level.INSUFFICIENT


@pytest.mark.parametrize(
    "text",
    [
        "Caller is asking me to share the OTP",
        "Bank se call hai, OTP maang rahe hain",
        "వాళ్ళు OTP అడుగుతున్నారు",
        "कॉलर ओटीपी माँग रहा है",
    ],
)
def test_otp_request_is_high_risk_in_each_language(text):
    r = assess(facts_from(text))
    assert r.level is Level.HIGH
    assert r.signs[0] == "otp"
    assert r.action == "no_otp"


@pytest.mark.parametrize(
    "text",
    [
        "They did not ask for any OTP",
        "OTP nahi maanga",
        "OTP adagaledu",
        "OTP అడగలేదు",
        "ओटीपी नहीं माँगा",
    ],
)
def test_negated_otp_is_not_a_sign(text):
    f = facts_from(text)
    assert f.slots["otp"].value is False
    assert assess(f).level is Level.INSUFFICIENT


def test_secrecy_phrase_is_not_read_as_negation_of_itself():
    f = facts_from("He said don't tell your family")
    assert f.slots["secrecy"].value is True


def test_money_with_pressure_is_high():
    assert level("Police officer says pay 50000 rupees fine") is Level.HIGH


def test_money_without_pressure_is_suspicious():
    assert level("They want me to pay a processing fee") is Level.SUSPICIOUS


def test_threat_alone_is_suspicious():
    assert level("He said my account will be blocked") is Level.SUSPICIOUS


def test_threat_authority_secrecy_combination_is_high():
    assert level("Police said I will be arrested and told me not to tell anyone") is Level.HIGH


def test_remote_access_is_high():
    r = assess(facts_from("They asked me to install AnyDesk"))
    assert r.level is Level.HIGH and r.action == "no_remote"


def test_loss_reported_triggers_report_action():
    r = assess(facts_from("I already shared the OTP with them"))
    assert r.loss_reported and r.action == "report_now"


def test_clause_split_keeps_negation_local():
    f = facts_from("They didn't threaten me, but they asked for my OTP")
    assert f.slots["threat"].value is False
    assert f.slots["otp"].value is True


def test_later_positive_overrides_earlier_negative():
    f = facts_from("No OTP asked", "now they are asking OTP")
    assert f.slots["otp"].value is True


def test_result_has_structured_fields():
    r = assess(facts_from("Caller from CBI says pay immediately"))
    assert r.level is Level.HIGH
    assert set(r.signs) >= {"money", "authority", "urgency"}
    assert r.evidence and r.score > 0
    assert "otp" in r.missing


@pytest.mark.parametrize(
    "text,expected",
    [("yes", True), ("haan", True), ("avunu", True), ("అవును", True), ("no", False), ("ledu", False),
     ("లేదు", False), ("nahi", False), ("I don't know", None), ("pata nahi", None)],
)
def test_answer_polarity(text, expected):
    assert answer_polarity(text) is expected


@pytest.mark.parametrize(
    "text,lang",
    [("కాలర్ OTP అడుగుతున్నారు", "te"), ("कॉलर पैसे माँग रहा है", "hi"),
     ("bank wale OTP maang rahe hain", "hi-en"), ("vallu OTP adugutunnaru andi", "te"),
     ("The caller wants my bank details", "en"), ("ok", None)],
)
def test_detect_language(text, lang):
    assert detect_language(text) == lang
