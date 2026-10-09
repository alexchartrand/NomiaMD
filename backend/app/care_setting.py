"""Where an encounter took place, in the manual's own places of service. An administrative
fact like registration or age: it comes from the note's source (an Epic encounter, a
schedule entry) or the physician picks it — never from the note text or the LLM, since a
note rarely states it and « urgence » in one is as often an urgent call-out to a ward or a
CHSLD as a visit at the emergency department.

Top-level because both the intake context (which records it) and ramq_codes (which
retrieves with it) read it, and the intake context never imports ramq_codes."""

from enum import StrEnum


class CareSetting(StrEnum):
    CABINET = "cabinet"
    DOMICILE = "domicile"
    URGENCE = "urgence"
    HOSPITALISATION = "hospitalisation"
    CHSLD = "chsld"


# How the billing_codes prompt states it (see app/ramq_codes/task.py).
CARE_SETTING_LABELS_FR = {
    CareSetting.CABINET: "cabinet privé, GMF ou CLSC",
    CareSetting.DOMICILE: "à domicile",
    CareSetting.URGENCE: "service d'urgence d'un centre hospitalier ou d'un CLSC du réseau de garde",
    CareSetting.HOSPITALISATION: "patient admis en centre hospitalier (soins de courte durée)",
    CareSetting.CHSLD: "CHSLD (soins de longue durée)",
}


def parse_care_setting(raw: object) -> CareSetting | None:
    """A stored or received value; anything else (absent, unknown) is None — unknown, never
    guessed."""
    try:
        return CareSetting(raw)
    except (ValueError, TypeError):
        return None
