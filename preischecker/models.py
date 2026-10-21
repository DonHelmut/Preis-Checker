from __future__ import annotations

from dataclasses import asdict, dataclass, field


@dataclass
class StromAngebot:
    anbieter: str
    tarif: str = ""
    arbeitspreis_ct: float | None = None
    grundpreis_monat: float | None = None
    jahrespreis_angezeigt: float | None = None  # wie vom Portal angezeigt
    bonus: float = 0.0
    laufzeit_monate: int | None = None
    preisgarantie_monate: int | None = None
    oekostrom: bool = False
    quelle: str = ""
    rohtext: str = field(default="", repr=False)

    def jahreskosten(self, verbrauch_kwh: float, bonus_einrechnen: bool = False) -> float | None:
        """Kosten im ersten Jahr. Ohne Bonus = dauerhafte Kosten."""
        if self.arbeitspreis_ct is not None and self.grundpreis_monat is not None:
            kosten = verbrauch_kwh * self.arbeitspreis_ct / 100 + 12 * self.grundpreis_monat
        elif self.jahrespreis_angezeigt is not None:
            # Portalpreis enthält den Bonus meist schon
            kosten = self.jahrespreis_angezeigt + self.bonus
        else:
            return None
        if bonus_einrechnen:
            kosten -= self.bonus
        return round(kosten, 2)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class InternetAngebot:
    anbieter: str
    tarif: str = ""
    download_mbit: int | None = None
    preis_monat_start: float | None = None   # Aktionspreis
    aktion_monate: int = 0                   # so lange gilt der Aktionspreis
    preis_monat_regulaer: float | None = None
    durchschnitt_monat_angezeigt: float | None = None
    anschlussgebuehr: float = 0.0
    bonus: float = 0.0
    laufzeit_monate: int = 24
    quelle: str = ""
    rohtext: str = field(default="", repr=False)

    def durchschnitt_monat(self, bonus_einrechnen: bool = True) -> float | None:
        """Effektiver Monatspreis über die Mindestlaufzeit."""
        lz = self.laufzeit_monate or 24
        regulaer = self.preis_monat_regulaer or self.preis_monat_start
        if regulaer is not None:
            start = self.preis_monat_start if self.preis_monat_start is not None else regulaer
            aktion = min(self.aktion_monate, lz)
            summe = aktion * start + (lz - aktion) * regulaer + self.anschlussgebuehr
            if bonus_einrechnen:
                summe -= self.bonus
            return round(summe / lz, 2)
        if self.durchschnitt_monat_angezeigt is not None:
            wert = self.durchschnitt_monat_angezeigt
            if not bonus_einrechnen:
                wert += self.bonus / lz
            return round(wert, 2)
        return None

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class ProduktAngebot:
    name: str
    preis: float
    shop: str
    url: str = ""
    lieferbar: bool | None = None  # None = unbekannt
    rohtext: str = field(default="", repr=False)

    def to_dict(self) -> dict:
        return asdict(self)
