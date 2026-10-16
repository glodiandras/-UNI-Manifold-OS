"""A füzetlánc céljai: a vault tárgyi fejezetei és elméleti jegyzetei (L48), csak olvasva.

A katalógus alakja az `ocr_kezi/katalogus.json`-é (`{"fejezetek": [{kod, nev, targy}], "jegyzetek": [{ut, cim, cimsorok, szavak}]}`),
és ugyanaz az építője (`modulok/eval/ocr_kezi/epit_katalogus.py`): a mérés a fagyasztott, a lánc az élő vaultból épített példányt
használja, ugyanazzal a szóalapú rangsorolóval (BM25, cím ×4, címsorok ×2 — a legacy `fuzet.index` mezősúlyai, az `ocr_kezi`
bírója). Cél csak a tárgyi fejezetmappa elmélet-almappájának (alap: `Elmélet/`, `[fuzet] elmelet_mappa`), `^\\d+ - ` nevű jegyzete;
a füzet-szakasz (alap: `## Füzet`, `[fuzet] szakasz`) a szavak közé nem kerül (a korábbi kötések nem befolyásolhatják az új döntést).
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

MODULOK = Path(__file__).resolve().parent.parent
if str(MODULOK / "eval") not in sys.path:
    sys.path.insert(0, str(MODULOK / "eval"))
from kozos import bm25  # noqa: E402

from . import kep  # noqa: E402

CIM_SULY, CIMSOR_SULY = 4, 2
FAGYASZTOTT = MODULOK / "eval" / "ocr_kezi" / "katalogus.json"
ALAP_ELMELET_MAPPA = "Elmélet"          # a `[fuzet] elmelet_mappa` alapja: a tárgyi fejezetmappa tananyag-almappája
# a tantárgy-betűk nevei nem a kódban élnek: a `[pdf.nevek]` (betű → nevek, az első a kanonikus) és a `[pdf.tags]` adja őket
_epito = None


def _epit_modul():
    global _epito
    if _epito is None:
        spec = importlib.util.spec_from_file_location("mos_fuzet_epit_katalogus", MODULOK / "eval" / "ocr_kezi" / "epit_katalogus.py")
        _epito = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(_epito)
    return _epito


def tokenek(szoveg: str) -> list[str]:
    """A rangsoroló szavai (az `ocr_kezi.tokenek`): hajtott, legfeljebb 6 betűs szóelők, 3 betűtől."""
    return _epit_modul().tokenek(szoveg)


class Katalogus:
    def __init__(self, adat: dict):
        self.fejezetek: list[dict] = adat["fejezetek"]
        self.jegyzetek: list[dict] = adat["jegyzetek"]
        self.nevek: dict = {}                       # `[pdf.nevek]` (a `vaultbol` tölti): a modszer a tantárgy betűjét ebből ismeri fel
        self.fej = {f["kod"]: f for f in self.fejezetek}
        self.cim = {j["ut"]: j["cim"] for j in self.jegyzetek}
        self._biro = None
        self._szokincs = None

    @classmethod
    def fagyasztott(cls) -> "Katalogus":
        return cls(json.loads(FAGYASZTOTT.read_text(encoding="utf-8")))

    @classmethod
    def vaultbol(cls, vault: str | Path, elmelet_mappa: str | None = None, szakasz: str | None = None,
                 cimkek: dict | None = None, nevek: dict | None = None) -> "Katalogus":
        """Az élő vaultból. A fejezetet adó betűk: a `nevek` (`[pdf.nevek]`: betű → nevek, az első a kanonikus név), majd a `cimkek`
        (`[pdf.tags]`: betű → címke) azon betűi, amelyeknek nincs neve."""
        em = _epit_modul()
        targyak = {str(b): l[0].strip() for b, l in (nevek or {}).items()
                   if len(str(b)) == 1 and isinstance(l, (list, tuple)) and l and isinstance(l[0], str) and l[0].strip()}
        for b, c in (cimkek or {}).items():
            if isinstance(c, str) and c.strip() and len(str(b)) == 1 and str(b) not in targyak:
                targyak[str(b)] = c.strip()
        k = cls(em.epit(Path(vault), elmelet_mappa=elmelet_mappa or ALAP_ELMELET_MAPPA, szakasz=szakasz or "Füzet", targyak=targyak))
        k.nevek = dict(nevek or {})
        return k

    def biro(self) -> bm25.Bm25:
        if self._biro is None:
            b = bm25.Bm25()
            for j in self.jegyzetek:
                szavak = dict(j["szavak"])
                for t in tokenek(j["cim"]):
                    szavak[t] = szavak.get(t, 0) + CIM_SULY
                for t in tokenek(" ".join(j["cimsorok"])):
                    szavak[t] = szavak.get(t, 0) + CIMSOR_SULY
                b.hozzaad(j["ut"], szavak)
            self._biro = b
        return self._biro

    def rangsor(self, szoveg: str, betuk: set[str] | None = None) -> list[tuple[str, float]]:
        """A jegyzetek szóalapú rangsora; `betuk`: csak ezeknek a tantárgyaknak (az út első betűje) a jegyzetei."""
        return [(ut, p) for ut, p in self.biro().rangsor(tokenek(szoveg)) if not betuk or ut[0] in betuk]

    def cel_e(self, ut: str) -> bool:
        return ut in self.cim

    def szokincs(self) -> set[str]:
        """Az olvashatóság szókincse (`kep.olvashatosag`): a jegyzetek szavainak és címeinek 5 betűs, hajtott előtagjai."""
        if self._szokincs is None:
            s: set[str] = set()
            for j in self.jegyzetek:
                s.update(w[:5] for w in j["szavak"] if len(w) >= 4)
                s.update(kep.tovek(j["cim"] + " " + " ".join(j["cimsorok"])))
            self._szokincs = s
        return self._szokincs

    def fejezetlista(self) -> str:
        """A képes hívás fejezetlistája, tantárgyanként csoportosítva (`[Tantárgy]`, `kód – cím`)."""
        sorok, targy = [], None
        for f in self.fejezetek:
            if f["targy"] != targy:
                targy = f["targy"]
                sorok.append(f"[{targy}]")
            sorok.append(f"{f['kod']} – {f['nev']}")
        return "\n".join(sorok)
