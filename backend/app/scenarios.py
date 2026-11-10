"""Synthetic demo callers. All names, numbers and lines are fictional.

Each caller has a short escalating script. Every line is spoken with Gnani
Timbre (generated on first request, then cached in backend/.cache/caller/),
so the simulated call itself is real Timbre output.
"""

SCENARIOS = {
    "A": {
        "title": "Card block + OTP",
        "caller": "SBI Card Services",
        "number": "+91 98XXX X0101",
        "language": "hi-en",
        "voice": "Avinash",
        "lines": [
            "Namaste sir, main SBI credit card department se Rahul bol raha hoon.",
            "Aapke card par ek suspicious transaction hua hai, isliye aaj raat aapka card block ho jayega.",
            "Block rokne ke liye card verify karna hoga. Card ke peeche wala CVV number bataiye.",
            "Aapke phone par abhi ek OTP aaya hoga. Jaldi bataiye, warna card band ho jayega.",
            "Sir, aap line par hain? Time bahut kam hai, OTP bata dijiye.",
        ],
    },
    "B": {
        "title": "Digital arrest",
        "caller": "Unknown",
        "number": "+91 70XXX X0202",
        "language": "hi",
        "voice": "Yashraj",
        "lines": [
            "मैं मुंबई क्राइम ब्रांच से इंस्पेक्टर विक्रम बोल रहा हूँ।",
            "आपके नाम से भेजे गए एक पार्सल में ग़ैरक़ानूनी सामान मिला है। आपके ख़िलाफ़ केस दर्ज हो गया है।",
            "आप अभी से डिजिटल अरेस्ट में हैं। कॉल मत काटिए और किसी को कुछ मत बताइए।",
            "केस बंद करने के लिए आपको तुरंत एक सुरक्षित खाते में पैसे ट्रांसफर करने होंगे।",
            "आप सुन रहे हैं? अगर पैसे नहीं भेजे, तो पुलिस आपके घर आ जाएगी।",
        ],
    },
    "C": {
        "title": "KYC update",
        "caller": "+91 80XXX X0303",
        "number": "+91 80XXX X0303",
        "language": "en",
        "voice": "Prakash",
        "lines": [
            "Hello, I'm calling from your mobile network's KYC department.",
            "Your KYC verification is pending, and your SIM may be deactivated within twenty-four hours.",
            "It's a simple process. I just need to confirm a few details with you.",
            "Can you please tell me your date of birth and the name on your Aadhaar card?",
            "Are you still there? This will only take two minutes.",
        ],
    },
    "D": {
        "title": "Unclear service call",
        "caller": "+91 90XXX X0404",
        "number": "+91 90XXX X0404",
        "language": "te",
        "voice": "Devansh",
        "lines": [
            "నమస్కారం సార్, మీ ఇంటర్నెట్ సర్వీస్ సెంటర్ నుండి కాల్ చేస్తున్నాం.",
            "మీ ఏరియాలో కనెక్షన్ సమస్య ఉందని మాకు కంప్లైంట్ వచ్చింది.",
            "మీ ఇంట్లో ఇంటర్నెట్ సరిగ్గా పనిచేస్తుందా సార్?",
            "సరే సార్, మా టెక్నీషియన్ వివరాలు మీకు త్వరలో మెసేజ్ చేస్తాం.",
            "సార్, మీరు లైన్‌లో ఉన్నారా?",
        ],
    },
}
