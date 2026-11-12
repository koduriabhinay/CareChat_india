"""Languages a user can choose for answers: English plus India's 22 scheduled languages.

Ordered roughly by number of speakers so the most used appear first.
Answer quality is lower in some less-resourced languages (for example
Bodo, Santali, Dogri, Manipuri); evaluate each before promising it.
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
    "pa": "Punjabi (ਪੰਜਾਬੀ)",
    "as": "Assamese (অসমীয়া)",
    "mai": "Maithili (मैथिली)",
    "sat": "Santali (ᱥᱟᱱᱛᱟᱲᱤ)",
    "ks": "Kashmiri (کٲشُر)",
    "ne": "Nepali (नेपाली)",
    "sd": "Sindhi (سنڌي)",
    "kok": "Konkani (कोंकणी)",
    "doi": "Dogri (डोगरी)",
    "mni": "Manipuri (ꯃꯩꯇꯩꯂꯣꯟ)",
    "brx": "Bodo (बड़ो)",
    "sa": "Sanskrit (संस्कृतम्)",
}


def language_name(code: str | None) -> str | None:
    """English name of the language for the prompt, e.g. 'Tamil'."""
    if not code or code not in LANGUAGES:
        return None
    return LANGUAGES[code].split(" (")[0]
