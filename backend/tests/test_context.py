"""Context awareness: scam patterns, tailored replies, compound questions, user questions."""

from app.conversation import Session, handle_turn
from app.risk import Level


def run(*turns, lang="auto"):
    s = Session()
    return s, [handle_turn(s, t, lang) for t in turns]


def test_card_block_gets_card_specific_ack_and_question_not_police():
    s, (o,) = run("Credit card block call")
    assert o.risk.scheme == "card_block"
    assert o.reply.startswith("Calls saying your card or account will be blocked")
    assert "CVV" in o.reply and "police" not in o.reply.lower()
    assert o.risk.level is Level.SUSPICIOUS  # a block threat alone


def test_card_block_in_telugu_when_telugu_chosen():
    s, (o,) = run("Credit card block call", lang="te")
    assert o.language == "te" and "కార్డ్" in o.reply and "CVV" in o.reply


def test_no_to_compound_question_clears_both_slots():
    s, outs = run("They say my account will be blocked", "no")
    f = s.facts
    assert f.slots["otp"].value is False and f.slots["credential"].value is False
    assert outs[1].followup == "remote"


def test_yes_to_compound_question_is_high():
    s, outs = run("card block call", "haan")
    assert outs[1].risk.level is Level.HIGH and outs[1].done


def test_id_request_is_a_sign_but_mention_is_not():
    _, (o,) = run("The caller is asking for my Aadhaar number")
    assert "id_request" in o.risk.signs and o.risk.level is Level.SUSPICIOUS
    _, (o,) = run("The caller mentioned my Aadhaar card")
    assert o.risk.level is Level.INSUFFICIENT


def test_id_request_with_pressure_is_high():
    _, (o,) = run("They want my Aadhaar number immediately or my SIM will be blocked")
    assert o.risk.level is Level.HIGH and o.risk.action == "no_id"


def test_prize_with_fee_is_high_advance_fee():
    _, (o,) = run("You have won a lottery, pay 5000 tax to claim it")
    assert o.risk.level is Level.HIGH and o.risk.scheme == "prize"
    assert "lottery you never entered" in o.reply


def test_prize_alone_asks_about_fee():
    _, (o,) = run("They say I won a lucky draw prize")
    assert o.risk.scheme == "prize" and o.followup == "money"
    assert "fee or tax" in o.reply


def test_police_followups_are_police_specific():
    _, (o,) = run("Someone from CBI called about a case")
    assert o.risk.scheme == "police" and o.followup == "money"
    assert "'safe' account" in o.reply


def test_is_this_real_mid_conversation():
    s, outs = run("KYC update call", "is this real?")
    o = outs[1]
    assert o.reply.startswith("I can't confirm who the caller is")
    assert "KYC" in o.reply  # scheme-specific verification advice
    assert o.followup is not None and not o.done


def test_what_should_i_do_in_telugu():
    _, outs = run("బ్యాంక్ నుండి కాల్ వచ్చింది, కార్డ్ బ్లాక్ అవుతుందంట", "ఏం చేయాలి")
    assert outs[1].reply.startswith("మీరు ఇలా చేయండి")


def test_after_final_nothing_new_gives_short_reply():
    s, outs = run("They want my OTP", "ok")
    assert outs[0].done
    assert len(outs[1].reply) < len(outs[0].reply) / 2


def test_after_final_new_info_updates_assessment():
    s, outs = run("KYC call", "no", "no", "no", "now they say I must install AnyDesk")
    assert outs[3].risk.level is Level.INSUFFICIENT
    assert outs[4].risk.level is Level.HIGH and "Do not install" in outs[4].reply


def test_utility_threat_tip_is_utility_specific():
    s, outs = run("Electricity office called", "they said power will be disconnected tonight")
    assert outs[0].risk.scheme == "utility"
    assert "police" not in " ".join(o.reply for o in outs).lower()


def test_yes_with_a_statement_does_not_fill_the_asked_slot():
    s, outs = run("నా KYC అప్డేట్ చేయాలని కాల్ వచ్చింది", "లేదు", "అవును, వెంటనే ఫీజు కట్టమంటున్నారు")
    assert outs[1].followup == "remote"
    assert s.facts.slots["remote"].value is None  # the "yes" was about the fee
    assert outs[2].risk.level is Level.HIGH and "money" in outs[2].risk.signs


def test_final_reply_is_short_enough_to_speak():
    for text in ("पुलिस वाला कह रहा है कि मैं डिजिटल अरेस्ट में हूँ और तुरंत पैसे भेजो",
                 "SBI se call hai, woh OTP maang rahe hain", "They want my OTP and told me to install AnyDesk"):
        _, (o,) = run(text)
        assert o.done and len(o.reply.split()) < 75, (len(o.reply.split()), o.reply)
        assert o.reply.count("कॉल काटिए") <= 1
