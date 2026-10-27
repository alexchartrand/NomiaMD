"""How the physician is paid for an ER garde sur place, their daily choice (P.G. 1.4): à l'acte,
or option b) — a forfait compensatoire, with the period's services paid at 101 % (0 h–8 h) or
53,2 % (20 h–24 h) — as the seul/premier médecin, the additional authorized physician, or one of
two physicians sharing 0 h–8 h. Which P.G. 1.4 forfaits a shift earns turns on it; it's never
derived, the physician picks it per shift."""

from enum import StrEnum


class GardeOption(StrEnum):
    ACTE = "acte"
    PREMIER = "premier"
    SECOND = "second"
    PARTAGE = "partage"


GARDE_OPTION_LABELS_FR = {
    GardeOption.ACTE: "Rémunération à l'acte",
    GardeOption.PREMIER: "Forfait de garde — seul médecin ou premier médecin",
    GardeOption.SECOND: "Forfait de garde — médecin additionnel (0 h à 8 h)",
    GardeOption.PARTAGE: "Forfait de garde — 0 h à 8 h partagée entre deux médecins",
}
