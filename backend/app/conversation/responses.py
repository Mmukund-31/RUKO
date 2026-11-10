"""Localized spoken text for RUKO.

Hand-written templates for Telugu (te), Hindi (hi), Hinglish (hi-en, Latin
script) and English (en). Other languages fall back to English text, which is
spoken with language=en-IN (see `speech_language`). The helpline number is
written as words so Timbre reads it digit by digit, not as a year.
"""

from __future__ import annotations

from ..risk.engine import Level, RiskResult
from .context_text import ACK, EXTRA, QV, TIPV, VERIFY

TEMPLATE_LANGS = ("te", "hi", "hi-en", "en")


def text_language(lang: str) -> str:
    return lang if lang in TEMPLATE_LANGS else "en"


def speech_language(lang: str) -> str:
    return text_language(lang)


T: dict[str, dict[str, str]] = {
    "en": {
        "ack": "Okay, I'm here with you.",
        "empty": "I didn't catch that. Please tell me what the caller is saying.",
        "q_otp": "Did the caller ask you to share an OTP?",
        "q_money": "Are they asking you to pay or transfer any money?",
        "q_remote": "Did they ask you to install an app, click a link, or share your screen?",
        "q_credential": "Did they ask for your PIN, CVV or password?",
        "q_threat": "Did they threaten you with arrest, a case, or blocking your account?",
        "q_secrecy": "Did they tell you not to tell your family or anyone else?",
        "q_urgency": "Are they pressuring you to act right now?",
        "tip_authority": "Ask for their full name, department and reference number. But don't trust that alone.",
        "tip_threat": "Real police and banks do not arrest people or block accounts over a phone call.",
        "tip_urgency": "Take your time. Pressure to act fast is a common warning sign.",
        "tip_money": "Don't send any money during this call.",
        "tip_secrecy": "Genuine officials never ask you to hide things from your family.",
        "tip_identity": "Never share your full Aadhaar or PAN details on a call you didn't make.",
        "lvl_HIGH_RISK": "This call is high risk. It shows strong signs of a scam.",
        "lvl_SUSPICIOUS": "This call looks suspicious. Please verify it before you do anything.",
        "lvl_INSUFFICIENT_INFORMATION": "I don't have enough information to judge this call yet, and I can't confirm the caller is genuine.",
        "because": "Warning signs: {signs}.",
        "and": " and ",
        "s_otp": "they asked for an OTP",
        "s_credential": "they asked for your PIN or password",
        "s_remote": "they want you to install an app or share your screen",
        "s_money": "they want money",
        "s_threat": "they made threats",
        "s_urgency": "they are rushing you",
        "s_authority": "they claim to be officials",
        "s_secrecy": "they asked you to keep it secret",
        "a_no_otp": "Do not share any OTP, PIN or password. Banks never ask for these on a call. End the call and call your bank on the number printed on your card.",
        "a_no_remote": "Do not install any app or share your screen. End the call. If you already installed something, uninstall it and tell your bank.",
        "a_no_money": "Do not transfer any money while they are pressuring you.",
        "police_money": "Real police never ask for money over a call.",
        "a_verify": "Don't share personal details or make payments on this call. Ask for their name, department and reference number, then end the call and verify using the official number from the website or your passbook.",
        "a_verify_soft": "To be safe, don't share OTPs, PINs or payments. If you're unsure, end the call and call the organisation back on its official number.",
        "a_report_now": "Call the cyber fraud helpline, one nine three zero, right now, and tell your bank immediately. You can also report at cybercrime dot gov dot in.",
        "helpline": "If you have already lost money or shared an OTP, call one nine three zero immediately.",
    },
    "hi-en": {
        "ack": "Theek hai, main aapke saath hoon.",
        "empty": "Mujhe sunai nahi diya. Bataiye, caller kya keh raha hai?",
        "q_otp": "Kya caller ne aapse OTP maanga?",
        "q_money": "Kya woh aapse koi paise bhejne ya pay karne ko keh rahe hain?",
        "q_remote": "Kya unhone koi app install karne, link click karne ya screen share karne ko kaha?",
        "q_credential": "Kya unhone aapka PIN, CVV ya password maanga?",
        "q_threat": "Kya unhone arrest, case ya account block karne ki dhamki di?",
        "q_secrecy": "Kya unhone kaha ki yeh baat family ya kisi aur ko mat batana?",
        "q_urgency": "Kya woh aap par abhi turant kuch karne ka pressure daal rahe hain?",
        "tip_authority": "Unka poora naam, department aur reference number poochiye. Lekin sirf uspar bharosa mat kijiye.",
        "tip_threat": "Asli police ya bank phone par arrest ya account block nahi karte.",
        "tip_urgency": "Jaldi mat kijiye. Jaldi karne ka pressure ek warning sign hai.",
        "tip_money": "Is call par koi paise mat bhejiye.",
        "tip_secrecy": "Asli officials kabhi family se baat chhupane ko nahi kehte.",
        "tip_identity": "Kisi anjaan call par apna poora Aadhaar ya PAN mat bataiye.",
        "lvl_HIGH_RISK": "Yeh call high risk hai. Ismein fraud ke strong signs hain.",
        "lvl_SUSPICIOUS": "Yeh call suspicious lag rahi hai. Kuch bhi karne se pehle verify kijiye.",
        "lvl_INSUFFICIENT_INFORMATION": "Is call ko judge karne ke liye abhi poori jaankari nahi hai. Main confirm nahi kar sakti ki caller genuine hai.",
        "because": "Warning signs: {signs}.",
        "and": " aur ",
        "s_otp": "OTP maanga gaya",
        "s_credential": "PIN ya password maanga gaya",
        "s_remote": "app install ya screen share karne ko kaha",
        "s_money": "paise maange ja rahe hain",
        "s_threat": "dhamki di gayi",
        "s_urgency": "jaldi karne ka pressure hai",
        "s_authority": "woh khud ko official bata rahe hain",
        "s_secrecy": "baat chhupane ko kaha",
        "a_no_otp": "Koi bhi OTP, PIN ya password mat bataiye. Bank phone par yeh kabhi nahi maangte. Call kaatiye aur apne card par likhe number par bank ko call kijiye.",
        "a_no_remote": "Koi app install mat kijiye aur screen share mat kijiye. Call kaatiye. Agar kuch install kar liya hai, toh use hata dijiye aur bank ko bataiye.",
        "a_no_money": "Pressure mein ek bhi paisa mat bhejiye.",
        "police_money": "Asli police phone par paise nahi maangti.",
        "a_verify": "Is call par personal details mat dijiye aur koi payment mat kijiye. Unka naam, department aur reference number poochiye, phir call kaatkar official website ya passbook wale number par khud call kijiye.",
        "a_verify_soft": "Safe rehne ke liye OTP, PIN ya paise mat dijiye. Shak ho toh call kaatiye aur company ke official number par khud call kijiye.",
        "a_report_now": "Abhi turant cyber fraud helpline ek nau teen shoonya par call kijiye, aur apne bank ko bhi turant bataiye. Aap cybercrime dot gov dot in par bhi report kar sakte hain.",
        "helpline": "Agar paise chale gaye hain ya OTP de diya hai, toh turant ek nau teen shoonya par call kijiye.",
    },
    "hi": {
        "ack": "ठीक है, मैं आपके साथ हूँ।",
        "empty": "मुझे सुनाई नहीं दिया। बताइए, कॉलर क्या कह रहा है?",
        "q_otp": "क्या कॉलर ने आपसे OTP माँगा?",
        "q_money": "क्या वे आपसे कोई पैसे भेजने या भरने को कह रहे हैं?",
        "q_remote": "क्या उन्होंने कोई ऐप इंस्टॉल करने, लिंक पर क्लिक करने या स्क्रीन शेयर करने को कहा?",
        "q_credential": "क्या उन्होंने आपका PIN, CVV या पासवर्ड माँगा?",
        "q_threat": "क्या उन्होंने गिरफ़्तारी, केस या अकाउंट बंद करने की धमकी दी?",
        "q_secrecy": "क्या उन्होंने कहा कि यह बात परिवार या किसी और को मत बताना?",
        "q_urgency": "क्या वे आप पर अभी तुरंत कुछ करने का दबाव डाल रहे हैं?",
        "tip_authority": "उनका पूरा नाम, विभाग और रेफ़रेंस नंबर पूछिए। लेकिन सिर्फ़ उस पर भरोसा मत कीजिए।",
        "tip_threat": "असली पुलिस या बैंक फ़ोन पर गिरफ़्तारी या अकाउंट बंद नहीं करते।",
        "tip_urgency": "जल्दबाज़ी मत कीजिए। जल्दी करने का दबाव धोखे का आम संकेत है।",
        "tip_money": "इस कॉल पर कोई पैसे मत भेजिए।",
        "tip_secrecy": "असली अधिकारी कभी परिवार से बात छुपाने को नहीं कहते।",
        "tip_identity": "किसी अनजान कॉल पर अपना पूरा आधार या पैन मत बताइए।",
        "lvl_HIGH_RISK": "यह कॉल बहुत जोखिम भरी है। इसमें धोखाधड़ी के मज़बूत संकेत हैं।",
        "lvl_SUSPICIOUS": "यह कॉल संदिग्ध लगती है। कुछ भी करने से पहले इसकी जाँच कीजिए।",
        "lvl_INSUFFICIENT_INFORMATION": "इस कॉल को परखने के लिए अभी पूरी जानकारी नहीं है, और मैं पक्का नहीं कह सकती कि कॉलर असली है।",
        "because": "चेतावनी के संकेत: {signs}।",
        "and": " और ",
        "s_otp": "OTP माँगा गया",
        "s_credential": "PIN या पासवर्ड माँगा गया",
        "s_remote": "ऐप इंस्टॉल या स्क्रीन शेयर करने को कहा",
        "s_money": "पैसे माँगे जा रहे हैं",
        "s_threat": "धमकी दी गई",
        "s_urgency": "जल्दबाज़ी का दबाव है",
        "s_authority": "वे ख़ुद को अधिकारी बता रहे हैं",
        "s_secrecy": "बात छुपाने को कहा",
        "a_no_otp": "कोई भी OTP, PIN या पासवर्ड मत बताइए। बैंक फ़ोन पर ये कभी नहीं माँगते। कॉल काटिए और अपने कार्ड पर लिखे नंबर पर बैंक को फ़ोन कीजिए।",
        "a_no_remote": "कोई ऐप इंस्टॉल मत कीजिए और स्क्रीन शेयर मत कीजिए। कॉल काटिए। अगर कुछ इंस्टॉल कर लिया है, तो उसे हटाइए और बैंक को बताइए।",
        "a_no_money": "दबाव में एक भी पैसा मत भेजिए।",
        "police_money": "असली पुलिस फ़ोन पर पैसे नहीं माँगती।",
        "a_verify": "इस कॉल पर निजी जानकारी मत दीजिए और कोई भुगतान मत कीजिए। उनका नाम, विभाग और रेफ़रेंस नंबर पूछिए, फिर कॉल काटकर आधिकारिक वेबसाइट या पासबुक वाले नंबर पर ख़ुद फ़ोन कीजिए।",
        "a_verify_soft": "सुरक्षित रहने के लिए OTP, PIN या पैसे मत दीजिए। शक हो तो कॉल काटिए और संस्था के आधिकारिक नंबर पर ख़ुद फ़ोन कीजिए।",
        "a_report_now": "अभी तुरंत साइबर फ़्रॉड हेल्पलाइन एक नौ तीन शून्य पर फ़ोन कीजिए, और अपने बैंक को भी तुरंत बताइए। आप साइबरक्राइम डॉट जीओवी डॉट इन पर भी शिकायत कर सकते हैं।",
        "helpline": "अगर पैसे चले गए हैं या OTP दे दिया है, तो तुरंत एक नौ तीन शून्य पर फ़ोन कीजिए।",
    },
    "te": {
        "ack": "సరే, నేను మీతోనే ఉన్నాను.",
        "empty": "నాకు వినిపించలేదు. కాలర్ ఏమంటున్నారో చెప్పండి.",
        "q_otp": "కాలర్ మిమ్మల్ని OTP చెప్పమని అడిగారా?",
        "q_money": "వాళ్ళు మిమ్మల్ని ఏమైనా డబ్బు కట్టమని లేదా పంపమని అడుగుతున్నారా?",
        "q_remote": "ఏదైనా యాప్ ఇన్‌స్టాల్ చేయమని, లింక్ క్లిక్ చేయమని లేదా స్క్రీన్ షేర్ చేయమని అడిగారా?",
        "q_credential": "మీ PIN, CVV లేదా పాస్‌వర్డ్ అడిగారా?",
        "q_threat": "అరెస్ట్ చేస్తామని, కేసు పెడతామని లేదా అకౌంట్ బ్లాక్ చేస్తామని బెదిరించారా?",
        "q_secrecy": "ఈ విషయం మీ కుటుంబానికి లేదా ఎవరికీ చెప్పొద్దని అన్నారా?",
        "q_urgency": "ఇప్పుడే వెంటనే చేయాలని ఒత్తిడి చేస్తున్నారా?",
        "tip_authority": "వారి పూర్తి పేరు, విభాగం, రిఫరెన్స్ నంబర్ అడగండి. కానీ దాన్ని మాత్రమే నమ్మకండి.",
        "tip_threat": "నిజమైన పోలీసులు లేదా బ్యాంకులు ఫోన్‌లో అరెస్ట్ చేయరు, అకౌంట్ బ్లాక్ చేయరు.",
        "tip_urgency": "తొందరపడకండి. త్వరగా చేయమని ఒత్తిడి చేయడం మోసానికి సాధారణ సంకేతం.",
        "tip_money": "ఈ కాల్‌లో ఒక్క రూపాయి కూడా పంపకండి.",
        "tip_secrecy": "నిజమైన అధికారులు కుటుంబం నుండి విషయం దాచమని ఎప్పుడూ చెప్పరు.",
        "tip_identity": "మీరు చేయని కాల్‌లో మీ పూర్తి ఆధార్ లేదా పాన్ వివరాలు చెప్పకండి.",
        "lvl_HIGH_RISK": "ఈ కాల్ చాలా ప్రమాదకరంగా ఉంది. ఇందులో మోసానికి బలమైన సంకేతాలు ఉన్నాయి.",
        "lvl_SUSPICIOUS": "ఈ కాల్ అనుమానాస్పదంగా ఉంది. ఏదైనా చేసే ముందు నిర్ధారించుకోండి.",
        "lvl_INSUFFICIENT_INFORMATION": "ఈ కాల్ గురించి నిర్ణయించడానికి ఇంకా సరిపడా సమాచారం లేదు. కాలర్ నిజమైనవారని నేను నిర్ధారించలేను.",
        "because": "హెచ్చరిక సంకేతాలు: {signs}.",
        "and": ", ",
        "s_otp": "OTP అడిగారు",
        "s_credential": "PIN లేదా పాస్‌వర్డ్ అడిగారు",
        "s_remote": "యాప్ ఇన్‌స్టాల్ లేదా స్క్రీన్ షేర్ అడిగారు",
        "s_money": "డబ్బు అడుగుతున్నారు",
        "s_threat": "బెదిరిస్తున్నారు",
        "s_urgency": "తొందర పెడుతున్నారు",
        "s_authority": "అధికారులమని చెప్పుకుంటున్నారు",
        "s_secrecy": "రహస్యంగా ఉంచమన్నారు",
        "a_no_otp": "ఏ OTP, PIN లేదా పాస్‌వర్డ్ చెప్పకండి. బ్యాంకులు ఫోన్‌లో ఇవి ఎప్పుడూ అడగవు. కాల్ కట్ చేసి, మీ కార్డు మీద ఉన్న నంబర్‌కి మీ బ్యాంకుకు ఫోన్ చేయండి.",
        "a_no_remote": "ఏ యాప్ ఇన్‌స్టాల్ చేయకండి, స్క్రీన్ షేర్ చేయకండి. కాల్ కట్ చేయండి. ఇప్పటికే ఏదైనా ఇన్‌స్టాల్ చేసి ఉంటే, దాన్ని తీసేసి మీ బ్యాంకుకు చెప్పండి.",
        "a_no_money": "వాళ్ళు ఒత్తిడి చేస్తున్నప్పుడు ఒక్క రూపాయి కూడా పంపకండి.",
        "police_money": "నిజమైన పోలీసులు ఫోన్‌లో డబ్బు అడగరు.",
        "a_verify": "ఈ కాల్‌లో వ్యక్తిగత వివరాలు చెప్పకండి, డబ్బు కట్టకండి. వారి పేరు, విభాగం, రిఫరెన్స్ నంబర్ అడగండి. తర్వాత కాల్ కట్ చేసి, అధికారిక వెబ్‌సైట్ లేదా పాస్‌బుక్‌లో ఉన్న నంబర్‌కి మీరే ఫోన్ చేయండి.",
        "a_verify_soft": "జాగ్రత్తగా ఉండటానికి OTP, PIN చెప్పకండి, డబ్బు కట్టకండి. అనుమానంగా ఉంటే, కాల్ కట్ చేసి ఆ సంస్థ అధికారిక నంబర్‌కి మీరే ఫోన్ చేయండి.",
        "a_report_now": "వెంటనే సైబర్ మోసం హెల్ప్‌లైన్ ఒకటి తొమ్మిది మూడు సున్నా కి ఫోన్ చేయండి, మీ బ్యాంకుకు కూడా వెంటనే చెప్పండి. సైబర్‌క్రైమ్ డాట్ గవ్ డాట్ ఇన్ లో కూడా ఫిర్యాదు చేయవచ్చు.",
        "helpline": "ఇప్పటికే డబ్బు పోయినా లేదా OTP చెప్పేసినా, వెంటనే ఒకటి తొమ్మిది మూడు సున్నా కి ఫోన్ చేయండి.",
    },
}


SHORT = {
    "en": {"a_verify_short": "Don't share personal details or make any payment on this call.",
           "a_soft_short": "To be safe, don't share OTPs, PINs or payments."},
    "hi-en": {"a_verify_short": "Is call par personal details mat dijiye aur koi payment mat kijiye.",
              "a_soft_short": "Safe rehne ke liye OTP, PIN ya paise mat dijiye."},
    "hi": {"a_verify_short": "इस कॉल पर निजी जानकारी मत दीजिए और कोई भुगतान मत कीजिए।",
           "a_soft_short": "सुरक्षित रहने के लिए OTP, PIN या पैसे मत दीजिए।"},
    "te": {"a_verify_short": "ఈ కాల్‌లో వ్యక్తిగత వివరాలు చెప్పకండి, డబ్బు కట్టకండి.",
           "a_soft_short": "జాగ్రత్తగా ఉండటానికి OTP, PIN చెప్పకండి, డబ్బు కట్టకండి."},
}


def t(lang: str, key: str) -> str:
    tl = text_language(lang)
    return EXTRA[tl].get(key) or SHORT[tl].get(key) or T[tl][key]


def question(lang: str, slot: str, scheme: str = "general") -> str:
    return QV[text_language(lang)].get((scheme, slot)) or t(lang, f"q_{slot}")


def ack(lang: str, scheme: str) -> str | None:
    return ACK[text_language(lang)].get(scheme)


def verify(lang: str, scheme: str) -> str:
    return VERIFY[text_language(lang)][scheme if scheme in VERIFY["en"] else "general"]


def tip_for(lang: str, newly: list[str], already_tipped: set[str], scheme: str = "general") -> tuple[str | None, str | None]:
    """At most one short tip per turn, for the most relevant newly found sign."""
    for slot in ("id_request", "money", "threat", "lure", "secrecy", "urgency", "authority", "identity"):
        if slot in newly and slot not in already_tipped:
            return slot, TIPV[text_language(lang)].get((scheme, slot)) or t(lang, f"tip_{slot}")
    return None, None


REASON_NONE = {
    "en": "No clear warning signs yet, but the caller is not verified.",
    "hi-en": "Abhi tak koi saaf warning sign nahi, lekin caller verified nahi hai.",
    "hi": "अभी तक कोई साफ़ चेतावनी संकेत नहीं, लेकिन कॉलर की पुष्टि नहीं हुई है।",
    "te": "ఇప్పటివరకు స్పష్టమైన హెచ్చరిక సంకేతాలు లేవు, కానీ కాలర్ నిర్ధారించబడలేదు.",
}

# Verification advice that would only repeat the HIGH-risk action text.
# no_money always appends how to verify (its own text only says "don't pay").
_REDUNDANT_VERIFY = {("no_otp", "card_block"), ("no_otp", "bank"), ("no_otp", "general")}


def _signs_text(lang: str, signs: list[str]) -> str:
    names = [t(lang, f"s_{s}") for s in signs[:3]]
    joined = names[0] if len(names) == 1 else ", ".join(names[:-1]) + t(lang, "and") + names[-1]
    return t(lang, "because").format(signs=joined)


def action_text(lang: str, r: RiskResult) -> str:
    """What to do, tailored to the recognised scam pattern."""
    if r.action == "report_now":
        return t(lang, "a_report_now")
    if r.level is Level.HIGH:
        text = t(lang, f"a_{r.action}")
        if r.action == "no_money" and "authority" in r.signs:
            text += " " + t(lang, "police_money")
        if r.action != "no_remote" and (r.action, r.scheme) not in _REDUNDANT_VERIFY:
            text += " " + verify(lang, r.scheme)
        return text
    if r.scheme == "general":
        return t(lang, "a_verify" if r.level is Level.SUSPICIOUS else "a_verify_soft")
    lead = t(lang, "a_verify_short" if r.level is Level.SUSPICIOUS else "a_soft_short")
    return f"{lead} {verify(lang, r.scheme)}"


def summary(lang: str, r: RiskResult) -> dict[str, str]:
    """Short texts for the assessment screen (the full answer is spoken)."""
    return {
        "level_text": t(lang, f"lvl_{r.level.value}").split(".")[0].split("।")[0],
        "reason_text": _signs_text(lang, r.signs) if r.signs else REASON_NONE[text_language(lang)],
        "action_text": action_text(lang, r),
    }


def headline(lang: str, r: RiskResult) -> str:
    """Level sentence; for HIGH/SUSPICIOUS only the first sentence (the signs follow)."""
    full = t(lang, f"lvl_{r.level.value}")
    if r.level is Level.INSUFFICIENT:
        return full
    for stop in (". ", "। "):
        if stop in full:
            return full.split(stop)[0] + stop.strip()
    return full


def final_text(lang: str, r: RiskResult) -> str:
    parts: list[str] = []
    if r.loss_reported:
        parts.append(t(lang, "a_report_now"))
    parts.append(headline(lang, r))
    if r.signs:
        parts.append(_signs_text(lang, r.signs))
    if not r.loss_reported:
        parts.append(action_text(lang, r))
        if r.level is Level.HIGH:
            parts.append(t(lang, "helpline"))
        elif r.main_reason == "identity":
            parts.append(t(lang, "tip_identity"))
    return " ".join(parts)


def status_text(lang: str, r: RiskResult) -> str:
    """Interim verdict, for "is this real?" / "what should I do?" mid-conversation."""
    parts = [headline(lang, r)]
    if r.signs:
        parts.append(_signs_text(lang, r.signs))
    parts.append(action_text(lang, r))
    return " ".join(parts)
