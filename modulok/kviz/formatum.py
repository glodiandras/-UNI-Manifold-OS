"""A kvízjegyzet formátuma (`docs/C22-TERV.md` 2. fejezet): elemző, író, a fájlnév és a `## Kitöltések` szakasz.

A legacy `ATTCHMNTS - quizes` formátuma (L47) marad; a `Source` a vault konvenciója szerint lista (az elemző a legacy
sztring alakot is olvassa):

```markdown
---
Source:
  - "[[T03 - Az ókori Róma/Elmélet/08 - A polgárháborúk kora és Caesar]]"
Kviz: KVIZ-20261004-203015-3fa91c
Modell: "qwen35_9b"
Keszult: 2026-10-04 2030
---

# A polgárháborúk kora és Caesar — Kvíz 2026-10-04 2030

Kvíz a(z) [[…|…]] jegyzetből: 10 kérdés …

## Kérdések

> [!question] 1. kérdés — Az első triumvirátus
> Kivel kötött szövetséget Caesar a senatus ellen?
>
> - A) …
> - B) …
> - C) …
> - D) …

> [!success]- Megoldás
> B) …
>
> Magyarázat: …
>
> A jegyzetben ([[…#Az első triumvirátus|Az első triumvirátus]]): „a szó szerinti mondat”

## Kitöltések
…
```

- A kérdés azonosítója a címsorból jön (`N. kérdés` → `kN`): a törölt vagy átrendezett kérdés a többiét nem mozdítja.
- A kódkerítésben álló callout nem kérdés (a core `maszk.mask_code`-ja).
- Az elemző nem dob: a hibák a jelentésben (`hibak: [{sor, fajta, szoveg, kerdes}]`); a hibás kérdés kimarad.
- A `## Kitöltések` szakasz a `{tanulas_db}` tiszta függvénye (`kitoltes_szakasz`); az írása a C22b dolga.

Tiszta függvények: szöveg be, szerkezet ki; fájlt nem olvasnak és nem írnak.
"""
from __future__ import annotations

import hashlib
import re
import unicodedata
from dataclasses import dataclass, field
from datetime import datetime, timezone, tzinfo

import yaml

from core.index.maszk import FM_RE, mask_code

BETUK = "ABCD"
AZON_RE = re.compile(r"^KVIZ-\d{8}-\d{6}(?:-[0-9a-z]{1,12})*$")
KITOLTES_CIM = "## Kitöltések"
KITOLTES_MEGJ = "%% A Manifold írja minden kitöltés után — kézi szerkesztés ebben a szakaszban felülíródik. %%"
UTOTAG = " — Kvíz "
ALAP_MAPPA = "ATTCHMNTS - quizes"       # a kvízjegyzetek mappája, ha a `[kviz] mappa` hiányzik

_CALLOUT = re.compile(r">[ \t]?\[!(question|success)\]([+-]?)[ \t]*(.*?)[ \t]*$", re.I)
_SORELO = re.compile(r"^>[ \t]?")
_CIMSOR_SZAM = re.compile(r"^(\d+)\.[ \t]*kérdés(?:[ \t]+—[ \t]+(.+))?$", re.I)
_OPCIO = re.compile(r"^[-*][ \t]+([A-D])\)[ \t]*(.*)$")
_MEGOLDAS = re.compile(r"^([A-Z])\)[ \t]*(.*)$")
_MAGYARAZAT = re.compile(r"^Magyarázat:[ \t]*(.*)$")
_JEGYZETBEN = re.compile(r"^A jegyzetben \(\[\[([^\]|#]*)(?:#([^\]|]*))?(?:\|([^\]]*))?\]\]\):[ \t]*(.*)$")
_TILTOTT_NEV = re.compile(r'[\\/:*?"<>|#^\[\]$\x00-\x1f]')


def nfc(s: str) -> str:
    return unicodedata.normalize("NFC", s)


def normal(s: str) -> str:
    return re.sub(r"\s+", " ", nfc(s)).strip().casefold().rstrip(".,;:!?")


@dataclass
class Kerdes:
    id: str                                   # 'k3'
    kerdes: str
    valaszok: list[str]                       # pontosan négy
    helyes: int                               # 0–3
    magyarazat: str = ""
    idezet: str = ""                          # a forrásjegyzet mondata (a jegyzet szövege, nem a modellé)
    szakasz: str | None = None                # a szakasz címe (a kérdés címsorában)
    horgony: str | None = None                # a `[[forras#horgony]]`-hoz; None: csak a jegyzetre mutat

    @property
    def szam(self) -> int:
        return int(self.id[1:])


@dataclass
class Kviz:
    azon: str                                 # 'KVIZ-20261004-203015-3fa91c'
    forras: str                               # a forrásjegyzet vault-relatív útja `.md` nélkül (a `Source` link célja)
    cim: str                                  # a forrásjegyzet címe (sorszám-előtag nélkül)
    modell: str = ""
    keszult: str = ""                         # 'ÉÉÉÉ-HH-NN ÓÓPP'
    kerdesek: list[Kerdes] = field(default_factory=list)


@dataclass
class Elemzes:
    kviz: Kviz | None = None
    hibak: list[dict] = field(default_factory=list)       # {sor, fajta, szoveg, kerdes}


def keszult(mikor: datetime) -> str:
    """A `Keszult` mező és a fájlnév ideje: `ÉÉÉÉ-HH-NN ÓÓPP`."""
    return mikor.strftime("%Y-%m-%d %H%M")


def tartalom_hash(k: Kviz) -> str:
    """A kvíz tartalmi ujjlenyomata (kérdés, válaszok, helyes betű): a magyarázat és az idézet nem tartozik bele. A kitöltés
    ezt rögzíti, így látszik, ha a kvíz azóta megváltozott."""
    h = hashlib.sha256()
    for q in sorted(k.kerdesek, key=lambda x: x.szam):
        h.update("\x1f".join([q.id, normal(q.kerdes), *(normal(v) for v in q.valaszok), str(q.helyes)]).encode("utf-8"))
        h.update(b"\x1e")
    return h.hexdigest()


# ---------------------------------------------------------------------- fájlnév

def fajlnev(k: Kviz, sorszam: int | None = None) -> str:
    """`<a jegyzet címe> — Kvíz ÉÉÉÉ-HH-NN ÓÓPP[ (n)]`; a H1 ugyanez (a séma H1 = fájlnév szabálya). A fájlnévben tiltott
    jelek és a `$` (páratlan `$` a stílus-próbán bukna) szóközzé válnak."""
    cim = re.sub(r"\s+", " ", _TILTOTT_NEV.sub(" ", nfc(k.cim))).strip() or "Jegyzet"
    return f"{cim}{UTOTAG}{k.keszult}" + (f" ({sorszam})" if sorszam and sorszam > 1 else "")


# ---------------------------------------------------------------------- író

def _yaml_str(s: str) -> str:
    return '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'


def _link(forras: str, horgony: str | None, felirat: str) -> str:
    cel = forras + (f"#{horgony}" if horgony else "")
    return f"[[{cel}|{re.sub(r'[\[\]|]', ' ', felirat).strip()}]]"


def ir_kerdes(k: Kviz, q: Kerdes) -> str:
    sor = [f"> [!question] {q.szam}. kérdés" + (f" — {q.szakasz}" if q.szakasz else ""), f"> {q.kerdes}", ">"]
    sor += [f"> - {BETUK[i]}) {v}" for i, v in enumerate(q.valaszok)]
    sor += ["", "> [!success]- Megoldás", f"> {BETUK[q.helyes]}) {q.valaszok[q.helyes]}", ">"]
    if q.magyarazat:
        sor += [f"> Magyarázat: {q.magyarazat}", ">"]
    sor += [f"> A jegyzetben ({_link(k.forras, q.horgony, q.szakasz or k.cim)}): {q.idezet}"]
    return "\n".join(sor)


def ir(k: Kviz, kitoltesek: list[dict] | None = None, jelolesek=None, idozona: tzinfo | None = None) -> str:
    """A kvízjegyzet teljes szövege. A frontmatter a `kviz` sémaosztály sorrendje (Source, Kviz, Modell, Keszult), a H1 a
    fájlnév. A `kitoltesek` az adatbázis kitöltései (lásd `kitoltes_szakasz`); nélkülük „Még nincs kitöltés”."""
    nev = fajlnev(k)
    fej = ["---", "Source:", f"  - {_yaml_str(f'[[{k.forras}]]')}", f"Kviz: {k.azon}",
           f"Modell: {_yaml_str(k.modell)}" if k.modell else "Modell:", f"Keszult: {k.keszult}" if k.keszult else "Keszult:", "---", ""]
    bevezeto = [f"# {nev}", "",
                f"Kvíz a(z) {_link(k.forras, None, k.cim)} jegyzetből: {len(k.kerdesek)} kérdés, helyi modellel. Minden kérdés a "
                "jegyzet egy mondatához kötött, és a modell a kulcs nélkül is ellenőrizte. Kitölthető a Manifoldban (a jegyzetbe "
                "beágyazva), vagy itt: a megoldás a kérdés alatt, lenyitható.", "", "## Kérdések", ""]
    kerdesek = "\n\n".join(ir_kerdes(k, q) for q in k.kerdesek)
    return ("\n".join(fej + bevezeto) + ("\n" + kerdesek + "\n\n" if kerdesek else "\n")
            + kitoltes_szakasz(k, kitoltesek or [], jelolesek, idozona))


# ---------------------------------------------------------------------- a Kitöltések szakasz

def kitoltes_szakasz(k: Kviz, kitoltesek: list[dict], jelolesek=None, idozona: tzinfo | None = None) -> str:
    """A kvízjegyzet gép írta szakasza: kitöltésenként egy sor, alatta, hogy mit nézz át és hol.

    `kitoltesek`: időrendben, soronként `{mikor: UTC ISO, mod: teljes|hibasak, osszegzes: {pont, osszes, szazalek,
    matrix: {tudja, szerencses, tevkepzet, hiany}, atnezni: [{szakasz, horgony, kerdesek: [szám]}]}}`; `jelolesek`: a
    „hibás” kérdések azonosítói; `idozona`: a kiírt idő zónája (alap: a gép helyi ideje)."""
    sor = [KITOLTES_CIM, "", KITOLTES_MEGJ, ""]
    if not kitoltesek:
        sor.append("Még nincs kitöltés.")
    for t in kitoltesek:
        o = t.get("osszegzes") or {}
        m = o.get("matrix") or {}
        mikor = datetime.fromisoformat(str(t["mikor"]).replace("Z", "+00:00"))
        if mikor.tzinfo is None:
            mikor = mikor.replace(tzinfo=timezone.utc)
        mikor = mikor.astimezone(idozona) if idozona else mikor.astimezone()
        sor.append(f"- {mikor.strftime('%Y-%m-%d %H:%M')} — {o.get('pont', 0)}/{o.get('osszes', 0)} ({o.get('szazalek', 0)} %)"
                   + (" · csak az előzőleg hibás kérdések" if t.get("mod") == "hibasak" else "")
                   + f" · tévképzet {m.get('tevkepzet', 0)} · hiány {m.get('hiany', 0)} · szerencsés tipp {m.get('szerencses', 0)}")
        at = [f"{_link(k.forras, a.get('horgony'), a.get('szakasz') or k.cim)} ({', '.join(f'{x}.' for x in a['kerdesek'])} kérdés)"
              for a in o.get("atnezni", [])]
        if at:
            sor.append("\t- Nézd át: " + "; ".join(at))
    jel = sorted(jelolesek or (), key=lambda q: int(q[1:]) if q[1:].isdigit() else 0)
    if jel:
        sor += ["", "Hibásnak jelölt kérdés: " + ", ".join(q[1:] + "." for q in jel) + " — a pontszámba nem számít."]
    return "\n".join(sor) + "\n"


def kitoltes_csere(szoveg: str, szakasz: str) -> str:
    """A `## Kitöltések` szakasz cseréje a kvízjegyzetben (a következő 1–2. szintű fejezetig tart; hiányában a jegyzet végére
    kerül). Idempotens; a jegyzet többi részéhez nem nyúl. Az írás (gépi írás, alap-hash) a C22b dolga."""
    sorok = szoveg.split("\n")
    uj = szakasz.rstrip("\n").split("\n")
    try:
        i = next(x for x, l in enumerate(sorok) if l.rstrip() == KITOLTES_CIM)
    except StopIteration:
        return szoveg.rstrip("\n") + "\n\n" + "\n".join(uj) + "\n"
    j = next((x for x in range(i + 1, len(sorok)) if re.match(r"^#{1,2}\s", sorok[x])), len(sorok))
    vege = sorok[j:]
    return "\n".join(sorok[:i] + uj + ([""] + vege if vege else [""]))


# ---------------------------------------------------------------------- elemző

def _link_cel(forras) -> str:
    s = str(forras).strip()
    m = re.fullmatch(r"\[\[([^\]]+)\]\]", s)
    return (m.group(1) if m else s).split("|", 1)[0].split("#", 1)[0].strip()


def _frontmatter(txt: str, e: Elemzes) -> tuple[dict, int]:
    m = FM_RE.match(txt)
    if not m:
        return {}, 0
    try:
        d = yaml.safe_load(m.group(1)) or {}
    except yaml.YAMLError as ex:
        e.hibak.append({"sor": 1, "fajta": "frontmatter", "szoveg": str(ex).splitlines()[0]})
        return {}, txt[:m.end()].count("\n")
    return (d if isinstance(d, dict) else {}), txt[:m.end()].count("\n")


def _callout_torzs(sorok: list[str], i: int, maszk: list[str]) -> tuple[list[str], int]:
    torzs, n = [], len(sorok)
    i += 1
    while i < n and sorok[i].startswith(">") and maszk[i].lstrip().startswith(">"):
        torzs.append(_SORELO.sub("", sorok[i], count=1))
        i += 1
    return torzs, i


def elemez(txt: str, azon_tartalek: str | None = None) -> Elemzes:
    """Egy kvízjegyzet. Az `azon_tartalek`-ot (az útból képzett azonosítót) a `Kviz:` mező hiányában használja a hívó
    (kézzel írt kvíz); nélküle a hiányzó azonosító hiba, és a `kviz` `None`."""
    txt = txt.replace("\r\n", "\n").replace("\r", "\n")
    e = Elemzes()
    fm, fm_sorok = _frontmatter(txt, e)
    sorok = txt.split("\n")
    maszk = mask_code(txt).split("\n")

    forras_ertek = fm.get("Source")
    forras_lista = forras_ertek if isinstance(forras_ertek, list) else ([forras_ertek] if forras_ertek else [])
    forras = _link_cel(forras_lista[0]) if forras_lista else ""
    azon = str(fm.get("Kviz") or "").strip() or (azon_tartalek or "")
    if not azon:
        e.hibak.append({"sor": 1, "fajta": "azonosito_nelkul", "szoveg": "nincs `Kviz:` azonosító a frontmatterben"})
        return e
    cim = re.sub(r"^\d+[A-Z]? - ", "", forras.rsplit("/", 1)[-1])
    for s, mk in zip(sorok, maszk):
        h1 = re.match(r"^#[ \t]+(.+?)[ \t]*$", mk)
        if h1 and UTOTAG in mk:
            cim = cim or s[h1.start(1):h1.end(1)].split(UTOTAG)[0]
            break
    k = Kviz(azon=azon, forras=forras, cim=nfc(cim), modell="" if fm.get("Modell") is None else str(fm["Modell"]),
             keszult="" if fm.get("Keszult") is None else str(fm["Keszult"]))

    # a callout-ok sorrendben: a kérdés és a hozzá tartozó (a következő kérdés előtti) megoldás
    jelenlegi: dict | None = None
    kerdesek: list[dict] = []
    i, n = fm_sorok, len(sorok)
    while i < n:
        m = _CALLOUT.fullmatch(sorok[i]) if maszk[i].lstrip().startswith(">") else None
        if not m:
            i += 1
            continue
        tipus, cimsor = m.group(1).lower(), m.group(3)
        torzs, kov = _callout_torzs(sorok, i, maszk)
        if tipus == "question":
            jelenlegi = {"sor": i + 1, "cimsor": cimsor, "torzs": torzs, "megoldas": None}
            kerdesek.append(jelenlegi)
        elif jelenlegi is not None and jelenlegi["megoldas"] is None:
            jelenlegi["megoldas"] = torzs
        i = kov

    if not kerdesek:
        e.hibak.append({"sor": 1, "fajta": "nincs_kerdes", "szoveg": "nincs `[!question]` callout a jegyzetben", "kerdes": None})
    latott: set[str] = set()
    for d in kerdesek:
        hiba = lambda fajta, szoveg, kid=None: e.hibak.append({"sor": d["sor"], "fajta": fajta, "szoveg": szoveg, "kerdes": kid})
        cs = _CIMSOR_SZAM.match(d["cimsor"].strip())
        if not cs:
            hiba("azonosito_nelkul", d["cimsor"])
            continue
        kid = f"k{int(cs.group(1))}"
        if kid in latott:
            hiba("duplikalt", kid, kid)
            continue
        latott.add(kid)
        szoveg_sorok: list[str] = []
        valaszok: dict[str, str] = {}
        for s in d["torzs"]:
            o = _OPCIO.match(s.strip())
            if o and o.group(1) not in valaszok:
                valaszok[o.group(1)] = o.group(2).strip()
            elif not valaszok and s.strip():
                szoveg_sorok.append(s.strip())
        if not szoveg_sorok:
            hiba("kerdes_nelkul", kid, kid)
            continue
        if list(valaszok) != list(BETUK) or any(not v for v in valaszok.values()):
            hiba("valasz_hiany", f"{len(valaszok)} válasz a négy helyett", kid)
            continue
        if d["megoldas"] is None:
            hiba("megoldas_nelkul", kid, kid)
            continue
        sorok_m = [s.strip() for s in d["megoldas"] if s.strip()]
        elso = _MEGOLDAS.match(sorok_m[0]) if sorok_m else None
        if not elso or elso.group(1) not in BETUK:
            hiba("megoldas_ervenytelen", sorok_m[0] if sorok_m else "", kid)
            continue
        helyes = BETUK.index(elso.group(1))
        if normal(valaszok[elso.group(1)]) != normal(elso.group(2)):
            hiba("megoldas_eltero", f"{elso.group(1)}) szövege eltér a válaszétól", kid)
            continue
        magyarazat = idezet = ""
        horgony = None
        for s in sorok_m[1:]:
            if (mg := _MAGYARAZAT.match(s)):
                magyarazat = mg.group(1).strip()
            elif (jb := _JEGYZETBEN.match(s)):
                horgony, idezet = (jb.group(2) or None), jb.group(4).strip()
        k.kerdesek.append(Kerdes(id=kid, kerdes=" ".join(szoveg_sorok), valaszok=[valaszok[b] for b in BETUK], helyes=helyes,
                                 magyarazat=magyarazat, idezet=idezet, szakasz=(cs.group(2) or "").strip() or None, horgony=horgony))
    e.kviz = k
    return e
