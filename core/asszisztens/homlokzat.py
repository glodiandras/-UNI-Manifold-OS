"""Az Asszisztens homlokzata (C30a): egy példány a core élettartamára (`app.asszisztens`), amely a részeket összefogja —
a higiénia-riport háttérszolgáltatását, a linkeletlen említéseket, a heti szokásminta-javaslatot, az elfogadási
statisztikát, a szövegkiegészítést, az önhangoló gyakoriságot és a javaslat-kártya mintatárát (J1–J3). Modellt nem tölt (a kiegészítés modellje a workeren át, `kiegeszites_modell`), a vaultba nem ír. A kapcsoló (10. döntés) mindenhol az Asszisztens-kapcsoló."""
from __future__ import annotations

from datetime import datetime

from .. import vezerlo
from ..higienia import Higienia
from ..modell.aktivitas import AKTIV
from .allapot import Allapot
from .emlites import Emlitesek
from .szokas import Szokasok
from .szolgalat import HigieniaSzolgalat
from .statisztika import Statisztika
from .kiegeszites import Kiegeszites
from .hangolo import Hangolo
from .mintatar import Mintatar


class Asszisztens:
    def __init__(self, cfg, index, tulajdonsagok, tracker, aktivitas, publish=lambda e, **k: None, mikor=datetime.now,
                 indulasi_kesleltetes_mp: float = 0.0):
        self.cfg = cfg
        self.allapot = Allapot(cfg)
        self.hangolo = Hangolo(cfg, self.allapot)                 # J1: önhangoló gyakoriság (fajta × helyzet)
        self.kiegeszites = Kiegeszites(self.allapot, self.kapcsolo, hangolo=self.hangolo)
        self.mintatar = Mintatar(cfg, index, self.allapot, self.hangolo, self.kapcsolo)    # J1/J3: tanult minták, kártya
        self.statisztika = Statisztika(cfg, tracker)
        self.higienia = Higienia(cfg, index, tulajdonsagok)
        self.szolgalat = HigieniaSzolgalat(cfg, index, self.higienia, self.allapot, aktiv=lambda: aktivitas.allapot() == AKTIV,
                                           publish=publish, indulasi_kesleltetes_mp=indulasi_kesleltetes_mp)
        self.emlitesek = Emlitesek(cfg, index)
        self.szokasok = Szokasok(cfg, tracker, self.statisztika, self.allapot, mikor=mikor)

    def kapcsolo(self) -> bool:
        return bool(vezerlo.kapcsolok(self.cfg)["asszisztens"])

    def indit(self) -> None:
        self.szolgalat.indit()

    def leallit(self) -> None:
        self.szolgalat.leallit()

    def ma_szakasz(self) -> dict:
        """A `GET /api/ma` szakasza: csak olvas (a heti javaslatot a Ma oldal külön, `GET /api/asszisztens/szokas`-sal kéri)."""
        return {"kapcsolo": self.kapcsolo(), "higienia": self.szolgalat.ma()}

    def tanult(self) -> dict:
        """A „Mit tanult az asszisztens” lista (J1): a szövegminták, az ismétlődő műveletek, az elutasított javaslatok és a
        hangolás. Minden tétel a `{state}/asszisztens.json`-ban él, egyenként törölhető; a vaultba semmi nem kerül."""
        return {"kapcsolo": self.kapcsolo(), "mintak": self.kiegeszites.mintak()["mintak"], **self.mintatar.lista(),
                "hangolas": self.hangolo.lista()}

    def tanult_torol(self, fajta, kulcs) -> dict:
        """Egy tanult tétel törlése: `fajta` minta | muvelet | elutasitott | hangolas | mind."""
        from ..utvonalak import HttpError
        if fajta == "mind":
            self.kiegeszites.torol()
            self.mintatar.torol_mind()
            self.hangolo.torol_mind()
            return {"ok": True, **self.tanult()}
        if not isinstance(kulcs, str) or not kulcs:
            raise HttpError(400, "a `kulcs` a törlendő tétel azonosítója", kod="asszisztens.homlokzat.kulcs_kell")
        if fajta == "minta":
            ok = self.kiegeszites.torol_minta(kulcs)["ok"]
        elif fajta == "muvelet":
            ok = self.mintatar.torol_muvelet(kulcs)
        elif fajta == "elutasitott":
            ok = self.mintatar.torol_dontes(kulcs)
        elif fajta == "hangolas":
            ok = self.hangolo.torol(kulcs)
        else:
            raise HttpError(400, "a fajta minta, muvelet, elutasitott, hangolas vagy mind lehet", kod="asszisztens.homlokzat.fajta_ertek")
        if not ok:
            raise HttpError(404, "nincs ilyen tanult tétel", kod="asszisztens.homlokzat.nincs_tetel")
        return {"ok": True, **self.tanult()}

    def link_kuszob(self, kuszob: dict) -> dict:
        """A linkjavaslat (C30b) küszöbe a hangolással (J1, 2. fejezet 4. pont): a statisztika küszöbe szigorodik, ha a `link`
        fajta hangolása ritkább vagy néma. A bátrabb hangolás a linkjavaslatot nem gyakorítja (csendesebb marad)."""
        a = self.hangolo.allas("link", "szoveg")
        if a["szint"] == "nema":
            return {"szint": "nema", "szorzo": None}
        if a["szint"] == "ritkabb" and kuszob.get("szint") != "nema":
            return {"szint": "szigoru", "szorzo": max(float(kuszob.get("szorzo") or 1.0), float(a["szorzo"]))}
        return kuszob
