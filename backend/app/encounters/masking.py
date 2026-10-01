"""How a patient shows in the inbox list: given name and surname initial, NAM with its
birth-date digits hidden. Pure string logic."""


def mask_name(full_name: str) -> str:
    """"Roch Desjardins" -> "Roch D."; a single-word name is kept as is."""
    parts = full_name.split()
    if not parts:
        return full_name
    given, *rest = parts
    return " ".join([given, *(f"{part[0]}." for part in rest)])


def mask_nam(nam: str | None) -> str | None:
    """"DESR81021001" -> "DESR ******01": the letters and sequence number tell two patients
    apart, the six digits between them are the birth date."""
    if nam is None:
        return None
    return f"{nam[:4]} {'*' * (len(nam) - 6)}{nam[-2:]}"
