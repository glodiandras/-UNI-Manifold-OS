"""Az új jegyzet előtöltése a nézet szűrőiből (10-bases-07): a „New” gomb a *látható*, egyértelmű feltételekből indul.

Tiszta számítás (nem ír, nem olvas fájlt): a globális és a nézet-szűrő **konjunkciójából** (egyetlen kifejezés, `and`-lista)
kigyűjti azokat az utasításokat, amelyekből egy új jegyzet tulajdonsága egyértelműen következik:

- `prop == "érték"` / `note.prop == 3` / `note["prop"] == true` (az érték literál; fordított sorrendben is) → tulajdonság;
- `file.hasTag("x")` / `file.tags.contains("x")` (pontosan egy címke) → címke (`tags` tulajdonság);
- `file.folder == "mappa"` / `file.inFolder("mappa")` → a jegyzet mappája.

Ami nem egyértelmű, kimarad: `or` és `not` ágai (több lehetőség), a nem literál érték, a több argumentumú `hasTag`, és az a
kulcs, amelyre a szűrők két különböző értéket követelnek (`nem_egyertelmu`-ben nevezve). A kanbanoszlop értékével a felület
írja felül a csoportosító tulajdonság előtöltését. Az eredmény a `lekerdez` válasz `fajl.elotoltes` mezője (új végpont nincs).
Az írást a felület végzi, a meglévő biztonságos úton (létrehozás `POST /api/vault/uj`, tulajdonság a nyitott dokumentumon
át): a core itt semmit nem hoz létre.
"""
from __future__ import annotations

from .kifejezes import Binaris, Hivas, Index, KifejezesHiba, Logikai, Nev, Szam, Szoveg, Tag, elemez
from .modell import Bazis, Nezet, szuro_fa

_ELOTAG_NEM_TULAJDONSAG = ("file", "formula", "this", "now")


def _utasitasok(sz) -> list[str]:
    """A szűrőfa konjunktív utasításai (kifejezés-szövegek); az `or` / `not` ágak nem."""
    if sz is None:
        return []
    if sz.fajta == "kif":
        return [sz.szoveg]
    if sz.fajta == "es":
        return [s for g in sz.gyerekek for s in _utasitasok(g)]
    return []


def _literal(c):
    if isinstance(c, Szoveg):
        return True, c.ertek
    if isinstance(c, Logikai):
        return True, c.ertek
    if isinstance(c, Szam):
        return True, c.ertek
    return False, None


def _tulajdonsag_neve(c) -> str | None:
    """A `prop` / `note.prop` / `note["prop"]` csomópont tulajdonságneve, vagy `None`."""
    if isinstance(c, Nev) and c.nev not in _ELOTAG_NEM_TULAJDONSAG:
        return c.nev
    if isinstance(c, Tag) and isinstance(c.obj, Nev) and c.obj.nev == "note":
        return c.nev
    if isinstance(c, Index) and isinstance(c.obj, Nev) and c.obj.nev == "note" and isinstance(c.kulcs, Szoveg):
        return c.kulcs.ertek
    return None


def _file_mezo(c, nev: str) -> bool:
    return isinstance(c, Tag) and isinstance(c.obj, Nev) and c.obj.nev == "file" and c.nev == nev


def _tipus(ertek) -> str:
    return "checkbox" if isinstance(ertek, bool) else "number" if isinstance(ertek, (int, float)) else "text"


def elotoltes(bazis: Bazis, nezet: Nezet) -> dict:
    """`{mappa, tulajdonsagok: [{kulcs, ertek, tipus}], cimkek: [str], nem_egyertelmu: [kulcs]}`."""
    szurok = [bazis.nyers.get("filters"), nezet.nyers.get("filters")]
    szovegek: list[str] = []
    for i, ny in enumerate(szurok):
        fa, _ = szuro_fa(ny, "filters" if i == 0 else "view")
        szovegek += _utasitasok(fa)
    tul: dict[str, object] = {}
    kizart: set[str] = set()
    cimkek: list[str] = []
    mappak: list[str] = []
    for szoveg in szovegek:
        try:
            c = elemez(szoveg)
        except KifejezesHiba:
            continue
        if isinstance(c, Binaris) and c.muvelet == "==":
            for ny, lit in ((c.bal, c.jobb), (c.jobb, c.bal)):
                van, ertek = _literal(lit)
                if not van:
                    continue
                nev = _tulajdonsag_neve(ny)
                if nev is not None:
                    if nev in tul and tul[nev] != ertek:
                        kizart.add(nev)
                    tul.setdefault(nev, ertek)
                elif _file_mezo(ny, "folder") and isinstance(ertek, str):
                    mappak.append(ertek.strip().strip("/"))
                break
        elif isinstance(c, Hivas) and isinstance(c.fn, Tag):
            f, argok = c.fn, c.argok
            if len(argok) != 1 or not isinstance(argok[0], Szoveg):
                continue
            ertek = argok[0].ertek
            if f.nev == "hasTag" and isinstance(f.obj, Nev) and f.obj.nev == "file":
                cimkek.append(ertek.lstrip("#"))
            elif f.nev == "contains" and _file_mezo(f.obj, "tags"):
                cimkek.append(ertek.lstrip("#"))
            elif f.nev == "inFolder" and isinstance(f.obj, Nev) and f.obj.nev == "file":
                mappak.append(ertek.strip().strip("/"))
    # a kizárt (két különböző értéket követelő) kulcs nem töltődik elő
    for k in kizart:
        tul.pop(k, None)
    nem_egyertelmu = sorted(kizart)
    mappak_egyedi = sorted(set(mappak))
    mappa = mappak_egyedi[0] if len(mappak_egyedi) == 1 else None
    if len(mappak_egyedi) > 1:
        nem_egyertelmu.append("file.folder")
    egyedi_cimkek = list(dict.fromkeys(c for c in cimkek if c))
    return {"mappa": mappa,
            "tulajdonsagok": [{"kulcs": k, "ertek": v, "tipus": _tipus(v)} for k, v in tul.items()],
            "cimkek": egyedi_cimkek, "nem_egyertelmu": nem_egyertelmu}
