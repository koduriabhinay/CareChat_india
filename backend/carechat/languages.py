"""Languages CareChat speaks at launch: English plus India's ten most spoken languages.

Each one needs a native-speaker review of the screen text and the fixed
safety messages before it goes live (see the testing plan).
"""

LANGUAGES: dict[str, str] = {
    "en": "English",
    "hi": "Hindi (हिन्दी)",
    "bn": "Bengali (বাংলা)",
    "te": "Telugu (తెలుగు)",
    "mr": "Marathi (मराठी)",
    "ta": "Tamil (தமிழ்)",
    "ur": "Urdu (اردو)",
    "gu": "Gujarati (ગુજરાતી)",
    "kn": "Kannada (ಕನ್ನಡ)",
    "or": "Odia (ଓଡ଼ିଆ)",
    "ml": "Malayalam (മലയാളം)",
}


def language_name(code: str | None) -> str | None:
    """English name of the language for the prompt, e.g. 'Tamil'."""
    if not code or code not in LANGUAGES:
        return None
    return LANGUAGES[code].split(" (")[0]
