"""C31 (16. pont, 36. döntés, K47/T072): csak olvasó mérés a VALÓDI vaulton — az md-link célok dekódolása és az Obsidian
1.14.4 feloldásának (statikus olvasás) eltérései a 2.0-tól. A discover nem futtatja; a vaultba és a `var/`-ba nem ír.

    PYTHONPATH=. <venv python> -B tests/kezi/link_dekodolas_meres.py [--vault <út>] [--json <kimenet>] [--peldak N]

Mit mér (a `feloldas.bejaras`/`link_maszk` szabályával, minden `.md`-n):
  1. md-linkek: az összes nem külső md-cél; ebből `%XX`-et tartalmazó, `<…>` burkos, `./`/`../`-ral kezdődő, a 2.0 KULSO
     listáján kívüli `séma:` alakú (az Obsidian ezt külsőnek veszi); és hány feloldása változik a dekódolással
     (`feloldas.md_cel`, ha már van; különben a régi alak), osztályozva: feloldatlan → feloldott, más cél, feloldott → feloldatlan.
  2. Az Obsidian `getLinkpathDest`-jének (1.14.4, `app.js`, statikusan olvasva — lásd `obsidian_feloldas`) és a 2.0
     `Feloldo`-jának eltérése minden linkre (wiki és md), osztályonként:
       K  a 2.0 kétmenetes (pontos, utána kisbetűs), az Obsidian egy kisbetűs menetben old fel;
       S  az Obsidian végződés-illesztése nem szegmenshatáros (`endsWith`), a 2.0-é az;
       R  relatív cél (`./`, `../`): az Obsidian a forrás mappájához képest oldja fel;
       P  `/`-rel kezdődő cél: az Obsidian csak pontos útra old fel;
       ?  egyéb (a holtversenyek sorrendje: az Obsidian a hossz szerinti stabil rendezést a betöltési sorrendben tartja,
          a 2.0 hossz + ábécé szerint).
A kimenet a darabszámok és osztályonként legfeljebb N példa; a mérés ideje ~ a gráf ideje (néhány másodperc).
"""
from __future__ import annotations

import argparse
import collections
import json
import os
import re
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
from core import config  # noqa: E402
from core.index import feloldas  # noqa: E402
from core.index.feloldas import MD_RE, WIKI_RE, nfc  # noqa: E402
from core.index.maszk import link_maszk  # noqa: E402

_SEMA = re.compile(r"^[A-Za-z][A-Za-z0-9+.-]*:")


class ObsidianFeloldo:
    """Az Obsidian 1.14.4 `MetadataCache.getLinkpathDest(e, t)`-je Pythonban (statikus olvasás, a lényeg):
    `o = e.toLowerCase()`; a jelölt a kisbetűs alapnév (`uniqueFileLookup`; ha a cél alapnevében nincs pont, vagy így
    nincs találat: `+ ".md"`); egyetlen jelölt és mappa nélküli cél → az; `./`/`../` → a forrás mappájához képest, csak
    pontos útra; a vezető `/` levágva, pontos út; `/`-rel kezdődő célnál itt vége; különben az `endsWith(o)`-val
    végződők, a forrás mappájával (`startsWith(dirname(src).lower())`) kezdődők előre, mindkét csoport út-hossz szerint."""

    def __init__(self, files):
        self.lookup: dict[str, list[str]] = collections.defaultdict(list)
        for rp in files:
            self.lookup[os.path.basename(rp).lower()].append(rp)

    def resolve(self, e: str, src: str) -> str | None:
        e = nfc((e or "").strip())
        if e.endswith("\\"):                          # a táblázatbeli `[[cél\\|alias]]` escape-je az elemzőé, nem a feloldóé
            e = e[:-1].rstrip()
        if not e:
            return None
        o = e.lower()
        a = os.path.basename(o)
        s = self.lookup.get(a) if "." in a else None
        if not s:
            o = (e + ".md").lower()
            a = os.path.basename(o)
            s = self.lookup.get(a)
        if not s:
            return None
        if a == o and len(s) == 1:
            return s[0]
        l_ = os.path.dirname(src).lower()
        if o.startswith("./") or o.startswith("../"):
            if o.startswith("./../"):
                o = o[2:]
            if o.startswith("./"):
                o = (l_ + "/" if l_ else "") + o[2:]
            else:
                while o.startswith("../"):
                    o, l_ = o[3:], os.path.dirname(l_)
                o = (l_ + "/" if l_ else "") + o
            for m in s:
                if m.lower() == o:
                    return m
            l_ = os.path.dirname(src).lower()
        if o.startswith("/"):
            o = o[1:]
        for m in s:
            if m.lower() == o:
                return m
        if e.startswith("/"):
            return None
        d = sorted((m for m in s if m.lower().endswith(o) and m.lower().startswith(l_)), key=len)
        f = sorted((m for m in s if m.lower().endswith(o) and not m.lower().startswith(l_)), key=len)
        return (d + f)[0] if d + f else None


def _osztaly(cel: str, src: str, regi: str | None, obs: str | None, fo: feloldas.Feloldo) -> str:
    s = nfc(cel.strip())
    if s.startswith(("./", "../")):
        return "R"
    if s.startswith("/"):
        return "P"
    if obs and regi is None and "/" in s:
        return "S"
    kis = fo._menet(feloldas._elokeszit(s), src, False)
    if kis and kis[0] == obs:
        return "K"
    return "?"


def meres(vault: Path, peldak: int = 5) -> dict:
    t0 = time.perf_counter()
    lista = feloldas.bejaras(vault)
    files = [rp for rp, _ in lista]
    fo = feloldas.Feloldo(files)
    obs = ObsidianFeloldo(files)
    md_cel = getattr(feloldas, "md_cel", None)
    md = collections.Counter()
    md_valtozas = collections.Counter()
    md_pelda = collections.defaultdict(list)
    elteres = collections.Counter()
    elteres_pelda = collections.defaultdict(list)
    linkek = 0
    for rp, lemez in lista:
        if not rp.lower().endswith(".md"):
            continue
        with open(vault / lemez, "rb") as fh:
            txt = link_maszk(feloldas.szoveg(fh.read()))
        celok = [m.group(1) for m in WIKI_RE.finditer(txt)]
        for m in MD_RE.finditer(txt):
            nyers = m.group(1)
            if _SEMA.match(nyers) and not nyers.startswith(feloldas.KULSO):
                md["sema_kulso_az_obsidianban"] += 1
                md_pelda["sema"].append(f"{rp}: ({nyers[:60]})")
            if nyers.startswith(feloldas.KULSO):
                continue
            md["osszes"] += 1
            regi_cel = nyers.split("#")[0]
            if "%" in nyers:
                md["szazalek"] += 1
            if nyers.strip().startswith("<"):
                md["burok"] += 1
            if nyers.strip().startswith(("./", "../")):
                md["relativ"] += 1
            uj_cel = md_cel(nyers) if md_cel else regi_cel
            r_regi = fo.resolve(regi_cel, rp)[0]
            r_uj = fo.resolve(uj_cel, rp)[0] if uj_cel is not None else None
            if r_regi != r_uj:
                fajta = ("feloldatlan→feloldott" if r_regi is None else "feloldott→feloldatlan" if r_uj is None
                         else "más cél")
                md_valtozas[fajta] += 1
                md_pelda[fajta].append(f"{rp}: ({nyers[:80]}) {r_regi} → {r_uj}")
            celok.append(uj_cel if uj_cel is not None else "")
        for c in celok:
            if not (c or "").strip():
                continue
            linkek += 1
            r2 = fo.resolve(c, rp)[0]
            ro = obs.resolve(c, rp)
            if r2 != ro:
                o = _osztaly(c, rp, r2, ro, fo)
                elteres[o] += 1
                elteres_pelda[o].append(f"{rp}: [[{c[:60]}]] 2.0: {r2} · Obsidian: {ro}")
    return {
        "vault": str(vault), "fajlok": len(files), "linkek": linkek, "md": dict(md),
        "md_dekodolas_valtozas": dict(md_valtozas), "md_dekodolas_aktiv": md_cel is not None,
        "obsidian_elteres": dict(elteres),
        "peldak": {k: v[:peldak] for k, v in {**md_pelda, **elteres_pelda}.items()},
        "ido_s": round(time.perf_counter() - t0, 2),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--vault")
    ap.add_argument("--json")
    ap.add_argument("--peldak", type=int, default=5)
    a = ap.parse_args()
    vault = Path(a.vault) if a.vault else config.load().path("vault")
    r = meres(vault, a.peldak)
    szoveg = json.dumps(r, ensure_ascii=False, indent=1)
    print(szoveg)
    if a.json:
        Path(a.json).write_text(szoveg, encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
