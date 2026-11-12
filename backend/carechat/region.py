"""Launch-region details: emergency numbers and the fixed safety messages.

India is the launch region. Set CARECHAT_REGION=US to switch.
Numbers must be re-checked with official sources before launch.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Region:
    code: str
    emergency_number: str  # general emergency line
    crisis_number: str  # mental health crisis line
    crisis_line_name: str
    emergency_message: str
    self_harm_message: str
    unavailable_message: str
    disclaimer: str
    # Fixed messages in other languages: code -> (emergency, self_harm, unavailable).
    # Each must be written or checked by a native speaker before launch.
    translations: dict[str, tuple[str, str, str]] = field(default_factory=dict)

    def messages(self, language: str | None) -> tuple[str, str, str]:
        if language and language in self.translations:
            return self.translations[language]
        return (self.emergency_message, self.self_harm_message, self.unavailable_message)


INDIA = Region(
    code="IN",
    emergency_number="112",
    crisis_number="14416",
    crisis_line_name="Tele-MANAS",
    emergency_message=(
        "Your message mentions symptoms that can be a medical emergency. "
        "Please call 112 (or 108 for an ambulance) now, or go to the nearest hospital emergency department. "
        "Don't wait for an online answer. If you're not sure whether it's an emergency, call anyway. "
        "CareChat can't help with emergencies."
    ),
    self_harm_message=(
        "It sounds like you may be going through something really painful, and you don't have to face it alone. "
        "You can call Tele-MANAS on 14416 (or 1-800-891-4416), free and available 24 hours a day, "
        "to talk to a trained counsellor in your language. "
        "If you are in immediate danger, please call 112 now."
    ),
    unavailable_message=(
        "CareChat can't check messages for safety right now, so it can't answer. "
        "If this might be an emergency, call 112. Otherwise, please try again in a few minutes."
    ),
    disclaimer=(
        "CareChat is for education only and is not medical advice. "
        "It can't diagnose or treat. In an emergency, call 112."
    ),
    translations={
        # Draft Hindi: needs review by a native speaker before launch.
        "hi": (
            "आपके संदेश में ऐसे लक्षण बताए गए हैं जो मेडिकल इमरजेंसी हो सकते हैं। "
            "कृपया अभी 112 पर कॉल करें (एम्बुलेंस के लिए 108), या नज़दीकी अस्पताल के इमरजेंसी विभाग में जाएं। "
            "ऑनलाइन जवाब का इंतज़ार न करें। अगर आपको यकीन नहीं है कि यह इमरजेंसी है, तब भी कॉल करें। "
            "CareChat इमरजेंसी में मदद नहीं कर सकता।",
            "ऐसा लगता है कि आप बहुत मुश्किल दौर से गुज़र रहे हैं, और आपको इसका सामना अकेले नहीं करना है। "
            "आप Tele-MANAS को 14416 (या 1-800-891-4416) पर कॉल कर सकते हैं। यह मुफ़्त है, 24 घंटे उपलब्ध है, "
            "और आप अपनी भाषा में प्रशिक्षित काउंसलर से बात कर सकते हैं। "
            "अगर आप तुरंत खतरे में हैं, तो कृपया अभी 112 पर कॉल करें।",
            "CareChat अभी सुरक्षा के लिए संदेशों की जाँच नहीं कर पा रहा है, इसलिए जवाब नहीं दे सकता। "
            "अगर यह इमरजेंसी हो सकती है, तो 112 पर कॉल करें। वरना कुछ मिनट बाद फिर कोशिश करें।",
        ),
    },
)

US = Region(
    code="US",
    emergency_number="911",
    crisis_number="988",
    crisis_line_name="988 Suicide & Crisis Lifeline",
    emergency_message=(
        "Your message mentions symptoms that can be a medical emergency. "
        "Please call 911 now, or go to the nearest emergency room. "
        "Don't wait for an online answer. If you're not sure whether it's an emergency, call 911 anyway. "
        "CareChat can't help with emergencies."
    ),
    self_harm_message=(
        "It sounds like you may be going through something really painful, and you don't have to face it alone. "
        "You can call or text 988 to reach the Suicide & Crisis Lifeline at any time. "
        "If you are in immediate danger, please call 911 now."
    ),
    unavailable_message=(
        "CareChat can't check messages for safety right now, so it can't answer. "
        "If this might be an emergency, call 911. Otherwise, please try again in a few minutes."
    ),
    disclaimer=(
        "CareChat is for education only and is not medical advice. "
        "It can't diagnose or treat. In an emergency, call 911."
    ),
)

REGIONS = {r.code: r for r in (INDIA, US)}


def get_region(code: str) -> Region:
    try:
        return REGIONS[code.upper()]
    except KeyError:
        raise ValueError(f"Unknown CARECHAT_REGION {code!r}; use one of {sorted(REGIONS)}") from None
