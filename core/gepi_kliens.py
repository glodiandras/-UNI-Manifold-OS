"""Kliens a gépi írás szolgáltatásához (C16.5) — a láncok és a feladat-lépések ezen át írnak a vaultba.

A lépés-folyamat közvetlenül soha nem ír a vaultba: a core `POST /api/gepi-iras` végpontját hívja, tételenként.
A core címe a `MOS_CORE_URL` (a feladatsor adja a lépéseknek); csak standard könyvtár, ML-függőség nélkül.

    from core import gepi_kliens as gepi
    kor = gepi.uj_kor("KARTYA")
    gepi.ir(kor, tetel="M03/Mértani sorozat.md", forras="mos-kartya", uzenet="kártyák: Mértani sorozat",
            modell=gepi.modell_jel(valasz), muveletek=[        # valasz: a worker chat-válasza; determinisztikus írásnál modell=None
        gepi.uj("M03/Mértani sorozat — kártyák.md", szoveg, osztaly="kartya"),   # a H1 a fájlnév (L33)
        gepi.beszuras("M03/Mértani sorozat.md", "Gyakorlás", "![[Mértani sorozat — kártyák]]", letrehoz=True)])

Egy `ir` = egy tétel = egy gépi commit (visszavonható). A 409 `nyitott` (a felhasználó épp szerkeszti a fájlt) és
`foglalt` (kör-zár) választ a `varakozas_mp` határidőig újrapróbálja; az ugyanazzal a (kör, tétel) párral megismételt
kérés nem ír kétszer. Próbamód (D9): `proba=True` vagy `MOS_PROBA=1` — az írás a vault APFS-klónjára megy. A `modell` kulcs
kötelező (C29.8, T043): AI-funkciónál a worker válaszából (`modell_jel`), determinisztikus írásnál kifejezetten `None`; a worker
`proba: true` jelzésű modelljének kimenete élesben nem írható.
"""
from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request

from . import frame, lepes_kapu


class GepiHiba(RuntimeError):
    """A core elutasította az írást. `kod`: HTTP-státusz; `adat`: a válasz (`utkozes`, `nyitott`, `foglalt`,
    `sema` + `problemak`, `kalibralatlan`, `pillanat_hiba`)."""

    def __init__(self, kod: int, uzenet: str, adat: dict | None = None):
        super().__init__(uzenet)
        self.kod, self.adat = kod, adat or {}


def core_url() -> str:
    u = os.environ.get("MOS_CORE_URL")
    if not u:
        raise GepiHiba(503, "nincs MOS_CORE_URL: a lépést a core feladatsora indítja")
    return u


def uj_kor(elotag: str) -> str:
    """Új kör-azonosító (L12): `<ELŐTAG>-ÉÉÉÉHHNN-ÓÓPPMM`."""
    return frame.new_id(elotag)


def uj(ut: str, tartalom: str, osztaly: str | None = None) -> dict:
    """Új fájl; `.md`-nél az `osztaly` a sémaosztály (`normal` vagy a vault-séma egy kivételosztálya)."""
    m = {"tipus": "uj", "ut": ut, "tartalom": tartalom}
    if osztaly is not None:
        m["osztaly"] = osztaly
    return m


def csere(ut: str, tartalom: str, alap: str) -> dict:
    """Teljes csere; `alap`: az olvasott változat sha1-e (`olvas(ut)["hash"]`)."""
    return {"tipus": "csere", "ut": ut, "tartalom": tartalom, "alap": alap}


def beszuras(ut: str, szakasz: str, szoveg: str, hova: str = "vege", letrehoz: bool = False,
             alap: str | None = None) -> dict:
    """Szöveg egy megnevezett szakasz (fejezet) alá; `letrehoz`: ha nincs ilyen szakasz, a fájl végére kerül."""
    m = {"tipus": "beszuras", "ut": ut, "szakasz": szakasz, "szoveg": szoveg, "hova": hova, "letrehoz": letrehoz}
    if alap is not None:
        m["alap"] = alap
    return m


def _keres(ut: str, body: dict | None = None, url: str | None = None, timeout: float = 60) -> dict:
    data = None if body is None else json.dumps(body, ensure_ascii=False).encode("utf-8")
    # a lépés-folyamat hitelesítője a feladatsor által adott lépés-token (T137: csak a gépi írást és a tiszta számolókat éri el, a felületi
    # API-titkot a lépés nem kapja); a lépésen kívüli hívó (kézi próba, teszt) a `MOS_API_TITOK`-ot használja (35. döntés)
    fejlec = {"X-Manifold": os.environ.get(lepes_kapu.KORNYEZETI_VALTOZO) or os.environ.get("MOS_API_TITOK", ""),
              "Content-Type": "application/json"}
    req = urllib.request.Request((url or core_url()).rstrip("/") + ut, data=data,
                                 method="POST" if body is not None else "GET", headers=fejlec)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:
        try:
            adat = json.loads(e.read() or b"{}")
        except ValueError:
            adat = {}
        finally:
            e.close()
        raise GepiHiba(e.code, adat.get("hiba") or str(e), adat) from None
    except (urllib.error.URLError, OSError) as e:
        raise GepiHiba(503, f"a core nem érhető el: {e}") from None


def olvas(ut: str, url: str | None = None) -> dict:
    """Egy szöveges vault-fájl a core-ból: `{ut, tartalom, hash, …}` — a `hash` a `csere` alapja."""
    return _keres("/api/vault/fajl?ut=" + urllib.parse.quote(ut, safe=""), url=url)


def atirat(ut: str, url: str | None = None) -> dict:
    """Egy videó/hang átirata a core olvasó végpontjából (C26b): `{ut, vtt, nyelv, gepi, leiro, cuek: [{k, v, szoveg}], figyelmeztetes}`.
    Csak olvas (a lépés-token az olvasó végpontokat engedi); a melléklet-mappa szabálya a core-é (`core/atirat.py`, L44)."""
    return _keres("/api/media/atirat?ut=" + urllib.parse.quote(ut, safe=""), url=url)


def modell_jel(valasz: dict) -> dict:
    """A gépi írás `modell` mezője a worker chat-válaszából (D9, C29.8): a router feladata, a modell neve és a próba-jelzés (a worker
    `proba: true`-t ad, ha a modell kifejezett kérésre futott). A lánc ezt adja át az `ir`-nak, kézzel nem gépeli."""
    try:
        feladat, modell = valasz["feladat"], valasz["modell"]
    except (KeyError, TypeError):
        raise ValueError("nem worker-válasz: hiányzik a feladat vagy a modell") from None
    if not isinstance(feladat, str) or not feladat or not isinstance(modell, str) or not modell:
        raise ValueError("a worker válaszában nincs router-feladat vagy modellnév (a feladatot a kérésben meg kell nevezni)")
    return {"feladat": feladat, "modell": modell, "proba": bool(valasz.get("proba"))}


def ir(kor: str, tetel: str, forras: str, muveletek: list[dict], uzenet: str | None = None,
       proba: bool | None = None, *, modell: dict | None, dontes: str | None = None,
       varakozas_mp: float = 30, url: str | None = None, esemeny: dict | None = None) -> dict:
    """Egy tétel írása. → `{ok, kor, tetel, sha, utak, hash, valtozas, ismetles, proba}`; hiba: `GepiHiba`.

    `modell` (kötelező kulcsszó, D9): AI-funkció kimenetére `modell_jel(worker_valasz)`, determinisztikus írásra kifejezetten `None`
    (a `null` mindig elmegy a kéréssel: a core a hiányzó kulcsot elutasítja). `esemeny` (C20b): a tétel tracker-eseménye
    (`{tipus, ut, adat}`, a `gepi_iras.ESEMENYEK` fehérlistája), amelyet a core a sikeres, nem próba commit után rögzít."""
    body = {"kor": kor, "tetel": tetel, "forras": forras, "muveletek": muveletek, "modell": modell,
            "proba": os.environ.get("MOS_PROBA") == "1" if proba is None else proba}
    if esemeny is not None:
        body["esemeny"] = esemeny
    for kulcs, v in (("uzenet", uzenet), ("dontes", dontes), ("feladat", os.environ.get("MOS_FELADAT"))):
        if v:
            body[kulcs] = v
    hatarido = time.monotonic() + varakozas_mp
    while True:
        try:
            return _keres("/api/gepi-iras", body, url)
        except GepiHiba as e:
            if e.kod != 409 or not (e.adat.get("nyitott") or e.adat.get("foglalt")) or time.monotonic() >= hatarido:
                raise
        time.sleep(1.0)
