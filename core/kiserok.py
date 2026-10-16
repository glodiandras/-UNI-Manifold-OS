"""A vault gépi (kísérő-) mappái és a séma feloldása: **egyetlen forrás** (F3-DESIGN §7.2, §8).

A kísérőjegyzetek (kártya, kvíz, összefoglaló, füzetfotó, videó) mappáinak neve a munkatér konvenciója: a `[vault] kisero_elotag`
(alap: `ALAP_ELOTAG`) és a fajtánként egy utótag adja (`Manifold - Cards`, `Manifold - Quizzes`, …). A fajta saját kulcsa
(`[kartya] mappa`, `[kviz] mappa`, `[osszefoglalas] mappa`, `[fuzet] cel_mappa`, `[video] vault_mappa` / `[media] video_mappa`)
csak akkor számít, ha a szállított alaptól (`Manifold - Cards`, …) eltér: az alap értékű (vagy üres) kulcs „az előtagból képzett
alap”. Így az előtag átírása az automatikát, a hasonló jegyzeteket, a gépi írás célmappáit és a sémaosztályokat együtt viszi;
senki nem tart külön listát. (A kulcsok alapértéke nem üres, hogy a közvetlenül konfigot olvasó kód sosem kap üres mappanevet.)

Importmentes (csak a szabványos könyvtár): a doctor és a modulok is használják. A `cfg` bármely `section(*kulcsok)`-ot adó objektum
lehet, vagy `None` (ilyenkor az alapértékek)."""
from __future__ import annotations

import json
import re
import unicodedata
from pathlib import Path

ALAP_ELOTAG = "Manifold - "

# fajta → (az alapnév utótagja, [(szakasz, kulcs)] a kifejezett felülírás helyei, elsőbbségi sorrendben)
FAJTAK: dict[str, tuple[str, tuple[tuple[str, str], ...]]] = {
    "kartya": ("Cards", (("kartya", "mappa"),)),
    "kviz": ("Quizzes", (("kviz", "mappa"),)),
    "osszefoglalas": ("Summaries", (("osszefoglalas", "mappa"),)),
    "fuzet": ("Photos", (("fuzet", "cel_mappa"),)),
    "video": ("Videos", (("video", "vault_mappa"), ("media", "video_mappa"))),
}


def nfc(s: str) -> str:
    return unicodedata.normalize("NFC", s)


def _szakasz(cfg, *kulcsok: str) -> dict:
    if cfg is None:
        return {}
    try:
        s = cfg.section(*kulcsok)
    except Exception:  # noqa: BLE001 — hiányzó vagy hibás szakasz: az alap
        return {}
    return s if isinstance(s, dict) else {}


def kisero_elotag(cfg) -> str:
    """A kísérőjegyzet-mappák névelőtagja (NFC): `[vault] kisero_elotag`, hiányában vagy üresen `ALAP_ELOTAG`."""
    v = _szakasz(cfg, "vault").get("kisero_elotag")
    return nfc(v) if isinstance(v, str) and v else ALAP_ELOTAG


def alap_mappa(fajta: str, elotag: str = ALAP_ELOTAG) -> str:
    """Egy fajta kísérőmappája kifejezett kulcs nélkül: `<előtag><Utótag>` (pl. `Manifold - Cards`)."""
    return nfc(elotag) + FAJTAK[fajta][0]


def kisero_mappa(cfg, fajta: str) -> str:
    """Egy fajta kísérőmappájának vault-relatív neve (NFC, záró perjel nélkül): a fajta kifejezett kulcsa, ha nem üres és eltér a
    szállított alaptól (`alap_mappa(fajta)`), különben `alap_mappa(fajta, kisero_elotag(cfg))`."""
    if fajta not in FAJTAK:
        raise KeyError(f"ismeretlen kísérő-fajta: {fajta}")
    szallitott = alap_mappa(fajta)
    for szakasz, kulcs in FAJTAK[fajta][1]:
        v = _szakasz(cfg, szakasz).get(kulcs)
        if isinstance(v, str) and v.strip("/ ").strip():
            v = nfc(v).strip("/")
            if v != szallitott:
                return v
    return alap_mappa(fajta, kisero_elotag(cfg))


def kisero_mappak(cfg) -> dict[str, str]:
    """Minden fajta kísérőmappája: `{fajta: név}`."""
    return {f: kisero_mappa(cfg, f) for f in FAJTAK}


def kisero_ut(rp: str, elotag: str) -> bool:
    """Kísérő-e az út: egyetlen útvonal-eleme `elotag`-gal kezdődik (NFC-összevetés)."""
    elotag = nfc(elotag)
    return any(nfc(r).startswith(elotag) for r in rp.replace("\\", "/").split("/") if r)


def tartalmi_elotaggal(rp: str, elotag: str) -> bool:
    """Tartalmi `.md`: nem kísérőjegyzet (egyetlen útvonal-elem sem kezdődik az `elotag`-gal), nem rejtett mappa."""
    reszek = [nfc(r) for r in rp.replace("\\", "/").split("/")]
    elotag = nfc(elotag)
    return rp.lower().endswith(".md") and not any(r.startswith(elotag) or r.startswith(".") for r in reszek)


def tartalmi_ut(cfg, rp: str) -> bool:
    """Tartalmi `.md` a munkatér kísérő-előtagja szerint (lásd `tartalmi_elotaggal`)."""
    return tartalmi_elotaggal(rp, kisero_elotag(cfg))


def tema_minta_alap(cfg) -> str:
    """A téma-mappa semleges alapmintája (a `[video] tema_minta` üres): a vault minden látható gyökérmappája, kivéve az `_`-sal kezdődőt
    (sablonmappa) és a kísérőmappákat. Csoport nincs: nincs tárgy-betű és nincs sorszám-konvenció."""
    return r"^(?!" + re.escape(kisero_elotag(cfg)) + r")[^._].*$"


_YAML_BIZTOS = re.compile(r"[^\W_][\w .\-]*")
_YAML_FOGLALT = frozenset({"true", "false", "null", "yes", "no", "on", "off", "y", "n", "~"})
_YAML_SZAM = re.compile(r"[-+]?(\d[\d_.,]*|\.\d+)([eE][-+]?\d+)?|0[xob][0-9a-fA-F_]+")


def yaml_cimke(tag: str) -> str:
    """Egy címke YAML-listaelemként a frontmatterbe (`Tags:\n  - <ez>`): a megszokott címke (betű / szám / szóköz / pont / kötőjel;
    nincs kettőspont, `#`, `[`, `{`, idézőjel, újsor) nyersen, minden más — a szóközzel szegélyezett, a YAML számára foglalt
    (`true`, `null`, szám) és minden vezérlőkaraktert vagy különleges jelet tartalmazó — JSON-idézőjeles (az érvényes YAML kettős
    idézőjeles szöveg, egyetlen sorban). A `[pdf.tags]` címkéi a munkatér (megbízhatatlan) beállításából jönnek: az újsoros
    érték (`a\nStatus: done`) új kulcsot hamisítana a frontmatterbe."""
    if _YAML_BIZTOS.fullmatch(tag) and tag == tag.strip() and tag.casefold() not in _YAML_FOGLALT and not _YAML_SZAM.fullmatch(tag):
        return tag
    ki = json.dumps(tag, ensure_ascii=False)
    for c in ("\x85", "\u2028", "\u2029"):             # a YAML 1.1 sortörésnek veszi: kiírva (a JSON nem escape-eli)
        ki = ki.replace(c, f"\\u{ord(c):04x}")
    return ki


def subject_of(cfg, rp: str) -> str | None:
    """A jegyzet tantárgy-címkéje a legfelső mappa első betűjéből (`[pdf.tags]`: betű → címke, az egyetlen térkép), vagy None.
    A gyökérben álló jegyzetnek nincs tantárgya."""
    if "/" not in rp:
        return None
    terkep = {str(k): str(v) for k, v in _szakasz(cfg, "pdf", "tags").items()}
    elso = nfc(rp.split("/", 1)[0])
    return terkep.get(elso[:1].upper()) if elso else None


# ------------------------------------------------------------------ a séma feloldása

def _presetnevek(cfg) -> list[str]:
    """A megnevezett presetek sorrendben: előbb a munkatéré (a legspecifikusabb), utána a telepítésé."""
    ki: list[str] = []
    for szakasz in ("workspace", "telepites"):
        for nev in _szakasz(cfg, szakasz).get("presetek") or []:
            if isinstance(nev, str) and nev not in ki:
                ki.append(nev)
    return ki


def sema_fajlok(cfg) -> list[Path]:
    """A vault-séma jelöltjei a feloldási lánc sorrendjében (a létező fájlok): (1) a `[sema] vault` fájl (a termékben
    `{workspace}/schema.json` — megbízhatatlan, a vault utazik); (2) a megnevezett presetek `<nev>.schema.json`-jai; (3) a szállított
    semleges `[sema] alap`. A betöltő az első ÉRVÉNYEST használja (`sema_hibak`): egy hibás munkatér-séma nem kapcsolja ki a presetét
    vagy az alapot, és nem dob kivételt."""
    ki: list[Path] = []
    if cfg is None:
        return ki
    s = _szakasz(cfg, "sema")

    def fel(nyers) -> Path | None:
        try:
            return Path(cfg.expand(nyers))
        except Exception:  # noqa: BLE001 — feloldatlan kulcs (nincs munkatér): a lánc folytatódik
            return None

    for nyers in (s.get("vault"),):
        p = fel(nyers) if nyers else None
        if p is not None and p.is_file():
            ki.append(p)
    for nev in _presetnevek(cfg):
        p = Path(cfg.root) / "config" / "presets" / f"{nev}.schema.json"
        if p.is_file():
            ki.append(p)
    p = fel(s["alap"]) if s.get("alap") else None
    if p is not None and p.is_file():
        ki.append(p)
    return ki


def sema_fajl(cfg) -> Path | None:
    """A vault-séma fájlja a feloldási lánc szerint (az első létező jelölt, lásd `sema_fajlok`): (1) a `[sema] vault` fájl, ha létezik;
    (2) az első megnevezett preset `<nev>.schema.json`-ja; (3) a szállított semleges `[sema] alap`. `None`, ha egyik sincs."""
    fajlok = sema_fajlok(cfg)
    return fajlok[0] if fajlok else None


# ------------------------------------------------------------------ a séma-fájl ellenőrzése (megbízhatatlan bemenet)

SEMA_MAX_BAJT = 1 << 20
SEMA_MAX_LISTA = 512
SEMA_MAX_OSZTALY = 64
SEMA_MAX_SZOVEG = 512
_VEZERLO = re.compile("[\x00-\x08\x0a-\x1f\x7f\x85\u2028\u2029]")


class SemaHiba(ValueError):
    """A séma-fájl érvénytelen (olvashatatlan, rossz típus, túl nagy, fordíthatatlan vagy veszélyes minta)."""


def _szoveglista(adat: dict, kulcs: str, hibak: list[str], *, kotelezo: bool = False, nullazhato: bool = False, hely: str = "") -> None:
    ertek = adat.get(kulcs)
    nev = f"{hely}{kulcs}"
    if ertek is None:
        if kotelezo or (kulcs in adat and not nullazhato):
            hibak.append(f"{nev}: lista kell")
        return
    if not isinstance(ertek, list) or len(ertek) > SEMA_MAX_LISTA:
        hibak.append(f"{nev}: lista kell (legfeljebb {SEMA_MAX_LISTA} elem)")
    elif any(not isinstance(x, str) or len(x) > SEMA_MAX_SZOVEG or _VEZERLO.search(x) for x in ertek):
        hibak.append(f"{nev}: csak rövid, vezérlőkarakter nélküli szövegek")


def _minta(adat: dict, kulcs: str, hibak: list[str], hely: str) -> None:
    ertek = adat.get(kulcs)
    if ertek is None:
        return
    from . import regex_biztonsag
    if not isinstance(ertek, str):
        hibak.append(f"{hely}{kulcs}: szöveg kell")
    elif regex_biztonsag.veszelyes(ertek):
        hibak.append(f"{hely}{kulcs}: érvénytelen vagy veszélyes reguláris kifejezés")


def sema_hibak(adat) -> list[str]:
    """A séma-adat (a `schema.json` / preset-séma tartalma) hibái; üres lista: érvényes. A fájl megbízhatatlan (a vault utazik): a
    típusokat, a méreteket, a vezérlőkaraktereket és a reguláris kifejezéseket (fordíthatók és nincs katasztrofális visszalépést
    engedő beágyazott ismétlés) ellenőrzi — a hibás séma helyett a lánc következő jelöltje él."""
    if not isinstance(adat, dict):
        return ["nem JSON-objektum"]
    h: list[str] = []
    _szoveglista(adat, "mezosorrend", h, kotelezo=True)
    for k in ("extra_kulcsok", "sema_nelkuli_utak", "sema_nelkuli_nevek"):
        _szoveglista(adat, k, h)
    for k in ("tags_ertekkeszlet", "status_ertekkeszlet"):
        _szoveglista(adat, k, h, nullazhato=True)
    if "status_gazdai" in adat and not isinstance(adat["status_gazdai"], bool):
        h.append("status_gazdai: igaz/hamis kell")
    osztalyok = adat.get("kivetel_osztalyok", [])
    if not isinstance(osztalyok, list) or len(osztalyok) > SEMA_MAX_OSZTALY:
        h.append(f"kivetel_osztalyok: lista kell (legfeljebb {SEMA_MAX_OSZTALY} elem)")
    else:
        for i, o in enumerate(osztalyok):
            hely = f"kivetel_osztalyok[{i}]."
            if not isinstance(o, dict):
                h.append(f"{hely[:-1]}: objektum kell")
                continue
            if not isinstance(o.get("nev"), str) or not o["nev"] or len(o["nev"]) > 64 or _VEZERLO.search(o["nev"]):
                h.append(f"{hely}nev: rövid szöveg kell")
            _szoveglista(o, "mezosorrend", h, kotelezo=True, hely=hely)
            _szoveglista(o, "utvonal_elotag", h, hely=hely)
            if "kisero" in o and o["kisero"] not in FAJTAK:
                h.append(f"{hely}kisero: ismeretlen fajta")
            for k in ("h1", "h1_egyezzen_fajlnevvel", "tartalmi"):
                if k in o and not isinstance(o[k], bool):
                    h.append(f"{hely}{k}: igaz/hamis kell")
            _minta(o, "h1_minta", h, hely)
    h1 = adat.get("h1", {})
    if h1 is None:
        h1 = {}
    if not isinstance(h1, dict):
        h.append("h1: objektum kell")
    else:
        _szoveglista(h1, "kivetel_utvonalak", h, hely="h1.")
        _minta(h1, "sorszam_elotag", h, "h1.")
        ko = h1.get("kivetel_osztalyok", [])
        if not isinstance(ko, list) or len(ko) > SEMA_MAX_OSZTALY:
            h.append(f"h1.kivetel_osztalyok: lista kell (legfeljebb {SEMA_MAX_OSZTALY} elem)")
        else:
            for i, k in enumerate(ko):
                hely = f"h1.kivetel_osztalyok[{i}]."
                if not isinstance(k, dict):
                    h.append(f"{hely[:-1]}: objektum kell")
                    continue
                _szoveglista(k, "utvonal_elotag", h, hely=hely)
                _minta(k, "fajlnev_minta", h, hely)
                for t in ("mappa_nev", "source_tartalmaz", "mod"):
                    if t in k and (not isinstance(k[t], str) or len(k[t]) > SEMA_MAX_SZOVEG or _VEZERLO.search(k[t])):
                        h.append(f"{hely}{t}: rövid szöveg kell")
    return h


def sema_olvas(ut: Path) -> dict:
    """Egy séma-fájl beolvasása és ellenőrzése: az érvényes adat, különben `SemaHiba` (a hibák felsorolásával)."""
    try:
        with open(ut, "rb") as f:
            nyers = f.read(SEMA_MAX_BAJT + 1)
        if len(nyers) > SEMA_MAX_BAJT:
            raise SemaHiba(f"{Path(ut).name}: a fájl túl nagy")
        adat = json.loads(nyers.decode("utf-8"))
    except SemaHiba:
        raise
    except (OSError, ValueError, RecursionError) as e:
        raise SemaHiba(f"{Path(ut).name}: nem olvasható JSON ({type(e).__name__})") from e
    hibak = sema_hibak(adat)
    if hibak:
        raise SemaHiba(f"{Path(ut).name}: " + "; ".join(hibak[:6]))
    return adat
