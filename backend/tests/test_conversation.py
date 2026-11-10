"""Demo scenarios A-D run through the real conversation pipeline (text path)."""

from app.conversation import Session, handle_turn
from app.risk import Level


def run(*turns, lang="auto"):
    s = Session()
    outs = [handle_turn(s, t, lang) for t in turns]
    return s, outs


def test_scenario_a_otp_scam_is_high_and_final_immediately():
    s, (o,) = run("Caller says he is from SBI and is asking for the OTP I just received")
    assert o.risk.level is Level.HIGH
    assert o.done and o.followup is None
    assert "OTP" in o.reply and "one nine three zero" in o.reply


def test_scenario_b_digital_arrest():
    s, (o,) = run("A police officer says I am under digital arrest and must transfer money now")
    assert o.risk.level is Level.HIGH
    assert {"authority", "threat", "money"} <= set(o.risk.signs)
    assert o.risk.action == "no_money"
    assert "Do not transfer" in o.reply


def test_scenario_c_kyc_asks_followups_then_insufficient_when_all_no():
    s, outs = run("They say my KYC needs to be updated", "no", "no", "no")
    first = outs[0]
    assert first.risk.level is Level.INSUFFICIENT
    assert first.followup == "otp"  # identity topic asks about OTP first
    assert [o.followup for o in outs[:3]] == ["otp", "remote", "money"]
    final = outs[-1]
    assert final.done and final.risk.level is Level.INSUFFICIENT
    assert "Aadhaar" in final.reply  # identity tip in the final answer


def test_scenario_c_kyc_with_payment_becomes_high():
    s, outs = run("They say my KYC needs to be updated", "no", "yes, they want a fee paid today itself")
    assert outs[-1].risk.level in (Level.SUSPICIOUS, Level.HIGH)
    assert "money" in outs[-1].risk.signs


def test_scenario_c_kyc_with_urgent_fee_is_high():
    s, outs = run("KYC update call", "no", "yes, they want a fee immediately")
    assert outs[-1].risk.level is Level.HIGH
    assert outs[-1].done


def test_scenario_d_unclear_call_asks_followup():
    s, (o,) = run("Someone called about a service issue with my connection")
    assert o.risk.level is Level.INSUFFICIENT
    assert o.followup is not None and not o.done
    assert o.reply.endswith("?")


def test_followups_never_repeat_and_are_capped():
    s, outs = run("Someone called me", "not sure", "maybe", "hmm", "ok")
    asked = [o.followup for o in outs if o.followup]
    assert len(asked) == len(set(asked)) <= 3
    assert outs[-1].done


def test_yes_answer_fills_last_question_slot():
    s, outs = run("Call about my bank account", "haan")
    assert outs[0].followup == "otp"
    assert outs[1].risk.level is Level.HIGH


def test_telugu_conversation_stays_in_telugu():
    s, outs = run("బ్యాంక్ నుండి కాల్ వచ్చింది", "లేదు", "అవును")
    assert all(o.language == "te" for o in outs)
    assert outs[0].reply.endswith("?")
    assert outs[-1].risk.level is Level.HIGH  # credential/otp asked -> yes


def test_hinglish_reply_is_latin_script():
    s, (o,) = run("bank wale bol rahe hain account block ho jayega")
    assert o.language == "hi-en"
    assert o.reply.isascii()


def test_explicit_language_choice_wins():
    s, (o,) = run("Caller wants my OTP", lang="te")
    assert o.language == "te"
    assert "OTP" in o.reply


def test_short_answer_keeps_session_language():
    s, outs = run("कॉलर बैंक से है", "yes")
    assert outs[1].language == "hi"


def test_empty_text_prompts_again_without_changing_state():
    s, (o,) = run("   ")
    assert not o.done and "didn't catch" in o.reply


def test_loss_reported_gives_helpline_first():
    s, (o,) = run("I already sent money to the caller")
    assert o.done
    assert o.reply.startswith("Call the cyber fraud helpline")


def test_unsupported_template_language_falls_back_to_english_text():
    s, (o,) = run("Caller wants my OTP", lang="kn")
    assert o.language == "kn"
    assert "Do not share any OTP" in o.reply


def test_police_line_only_when_authority_claimed():
    _, (o,) = run("Police officer says pay a fine immediately")
    assert "Real police never ask for money" in o.reply
    _, outs = run("KYC update call", "no", "yes, they want a fee immediately")
    assert "police" not in outs[-1].reply.lower()


def test_sign_list_joins_naturally():
    _, (o,) = run("पुलिस वाला कह रहा है तुरंत पैसे भेजो वरना गिरफ़्तार")
    listed = o.reply.split("चेतावनी के संकेत:")[1].split("।")[0]
    assert listed.count(" और ") == 1 and listed.count(",") == 1
