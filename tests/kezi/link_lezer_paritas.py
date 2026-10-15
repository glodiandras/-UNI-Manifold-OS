"""C10.6 kész-feltétele: a core link-halmaza a VALÓDI vaulton összevetve a szerkesztő Lezer-elemzőjének
link-halmazával, fájlonként (audit M6: két elemző, eddig csak a képletekre volt paritásmérés). Csak olvas; a
discover nem futtatja.

    bin/mos exec var/venv/bin/python -B tests/kezi/link_lezer_paritas.py

1. A vitest (Node, `app/vitest.kezi.config.ts`) az `app/tests/kezi/linkek.kezi.ts`-t futtatja: minden `.md`-re a
   szerkesztő elemzőjének linkjei (wikilink, beágyazás, md-link) és azok a `[[`-k, amelyekből nem lett link, a
   környező csomópont nevével.
2. A core link-listája a **lemezről** számolódik (`elemzo.elemez`, az élő indextől függetlenül), ugyanazzal a
   maszkkal, mint a gráf és az index (`maszk.link_maszk`).
3. Összevetés a jegyzet törzsén, (sor, fajta, beágyazás, cél) szerint; a cél szóközök és a záró `\\` nélkül. A
   frontmatter linkjei külön sor: a szerkesztő ott szándékosan nem elemez (a tulajdonság-linkek a core-éi).
   Minden eltérés okot kap: a csak a core-ban álló linknél a szerkesztő kontextusa (pl. `CodeBlock`, `TableCell`),
   a csak a szerkesztőben állónál az, hogy a core maszkja takarja-e.

**Kapu** (kilépési kód 1): a C10.6-ban egységesített szerkezetekben — kerítéses kód, soron belüli kód, képlet —
nincs eltérés, egyik irányban sem. A többi ok (lezáratlan `[[`, a táblázat escape nélküli `|`-e, szóközös md-URL,
behúzott kód, HTML) riport: a `WIKI_RE`/`MD_RE` alakjából és a két nyitott kérdésből jön, a NAPLO-ba kerül.
Riport: `{runs}/link-lezer-<idő>.json`.
"""
import collections
import json
import os
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
from core import config  # noqa: E402
from _kornyezet import md_db, vitest_futtat  # noqa: E402
from core.index import elemzo, feloldas, maszk  # noqa: E402
from core.index.feloldas import KULSO  # noqa: E402

KAPU = {"FencedCode", "InlineCode", "InlineMath", "DisplayMath", "MathBlock"}


def cel_norm(cel: str) -> str:
    s = (cel or "").strip()
    if s.endswith("\\"):
        s = s[:-1].rstrip()
    return s


def core_linkek(txt: str) -> tuple[list[dict], int]:
    """A core linkjei a törzsben: [{sor, oszlop, fajta, beagyazas, cel}], és a frontmatter linkjeinek száma."""
    j = elemzo.elemez(txt)
    fm = maszk.FM_RE.match(txt)
    fm_veg = fm.end() if fm else 0
    kezdet = [0]
    for i, c in enumerate(txt):
        if c == "\n":
            kezdet.append(i + 1)
    ki, fm_db = [], 0
    for L in j.linkek:
        if kezdet[L.sor - 1] + L.oszlop < fm_veg:
            fm_db += 1
            continue
        fajta = "wiki" if L.fajta == "wiki" else "md"
        ki.append({"sor": L.sor, "oszlop": L.oszlop + (1 if L.beagyazas and fajta == "md" else 0), "fajta": fajta,
                   "beagyazas": bool(L.beagyazas), "cel": cel_norm(L.cel)})
    return ki, fm_db


def lezer_linkek(adat: dict) -> list[dict]:
    """A szerkesztő linkjei a core alakjában: a külső md-link kimarad, az md-cél a `#` előtt áll."""
    ki = []
    for L in adat["linkek"]:
        cel = L["cel"]
        if L["fajta"] == "md":
            if cel.startswith(KULSO):
                continue
            cel = cel.split("#")[0]
        ki.append({**L, "cel": cel_norm(cel)})
    return ki


def kulcs(L: dict) -> tuple:
    return (L["sor"], L["fajta"], L["beagyazas"], L["cel"])


def main() -> int:
    cfg = config.load()
    vault = cfg.path("vault")
    runs = cfg.path("runs")
    runs.mkdir(parents=True, exist_ok=True)
    nyers_ut = cfg.path("tmp") / time.strftime("c106-lezer-%Y%m%d-%H%M%S.json")
    nyers_ut.parent.mkdir(parents=True, exist_ok=True)
    print(f"[linkek] vault: {vault}")
    p = vitest_futtat("tests/kezi/linkek.kezi.ts", dict(MOS_KEZI_VAULT=str(vault), MOS_KEZI_RIPORT=str(nyers_ut)),
                      md_db(vault), 300)                          # időkorlát a jegyzetek számához igazítva
    if not nyers_ut.exists():
        print(p.stdout[-3000:], p.stderr[-2000:])
        print("[linkek] HIBA: nem készült riport")
        return 2
    r = json.loads(nyers_ut.read_text(encoding="utf-8"))
    nyers_ut.unlink()                                       # a saját var/tmp fájlunk
    lezer = r["fajlonkent"]

    ossz = collections.Counter()
    okok: dict[str, list] = collections.defaultdict(list)
    fajl_elteres: dict[str, list] = {}
    core_ossz = lezer_ossz = fm_ossz = fajlok = 0
    for rp, lemez in feloldas.bejaras(vault):
        if not rp.lower().endswith(".md"):
            continue
        fajlok += 1
        with open(os.path.join(vault, lemez), "rb") as fh:
            txt = feloldas.szoveg(fh.read())
        c_linkek, fm_db = core_linkek(txt)
        adat = lezer.get(rp, {"linkek": [], "nem_link": [], "frontmatter_veg": 0})
        l_linkek = lezer_linkek(adat)
        core_ossz += len(c_linkek)
        lezer_ossz += len(l_linkek)
        fm_ossz += fm_db
        a = collections.Counter(kulcs(x) for x in c_linkek)
        b = collections.Counter(kulcs(x) for x in l_linkek)
        if a == b:
            continue
        nem_link = {(x["sor"], x["oszlop"]): x["kontextus"] for x in adat["nem_link"]}
        linkmaszk = maszk.link_maszk(txt)
        kezdet = [0]
        for i, ch in enumerate(txt):
            if ch == "\n":
                kezdet.append(i + 1)
        sorok = txt.split("\n")
        tetelek = []
        csak_core, csak_lezer = a - b, b - a
        for L in c_linkek:
            if csak_core.get(kulcs(L), 0) <= 0:
                continue
            csak_core[kulcs(L)] -= 1
            if L["fajta"] == "wiki":
                h = (L["sor"], L["oszlop"] + (1 if L["beagyazas"] else 0))
                ok = nem_link.get(h, "a szerkesztőben más a cél szövege")
                if not L["cel"] and "[[]]" in sorok[L["sor"] - 1]:
                    ok = "üres [[]] (a szerkesztőben nem link)"
                elif ok.startswith("egyéb"):
                    ok = "lezáratlan vagy többsoros [[ (" + ok.split(": ")[1] + ")"
            else:
                ok = "md-link: a szerkesztő nem látja linknek (pl. szóköz az URL-ben)"
            tetelek.append({"oldal": "core", "ok": ok, **L, "szoveg": sorok[L["sor"] - 1][:160]})
        for L in l_linkek:
            if csak_lezer.get(kulcs(L), 0) <= 0:
                continue
            csak_lezer[kulcs(L)] -= 1
            off = kezdet[L["sor"] - 1] + L["oszlop"]
            takart = off < len(txt) and linkmaszk[off] == " " and txt[off] != " "
            ok = ("a core maszkja takarja" if takart else
                  "a core-ban más a cél szövege" if L["fajta"] == "wiki" else "md-link: a core regexe nem illeszkedik")
            tetelek.append({"oldal": "szerkesztő", "ok": ok, **L, "szoveg": sorok[L["sor"] - 1][:160]})
        fajl_elteres[rp] = tetelek
        for t in tetelek:
            k = f"csak a {'core-ban' if t['oldal'] == 'core' else 'szerkesztőben'}: {t['ok']}"
            ossz[k] += 1
            okok[k].append((rp, t))

    kapu = [(rp, t) for rp, lista in fajl_elteres.items() for t in lista
            if (t["oldal"] == "core" and t["ok"] in KAPU) or t["ok"] == "a core maszkja takarja"]
    print(f"[linkek] {fajlok} jegyzet; a törzsben a core {core_ossz}, a szerkesztő {lezer_ossz} linket lát "
          f"(a vitest {r['ido_mp']} s); a frontmatterben a core {fm_ossz} tulajdonság-linket (a szerkesztő ott nem elemez)")
    print(f"[linkek] eltérő fájl: {len(fajl_elteres)}; eltérő link: {sum(ossz.values())}")
    for k, n in sorted(ossz.items(), key=lambda x: (-x[1], x[0])):
        print(f"  {n:5}  {k}")
        for rp, t in okok[k][:4]:
            print(f"           {rp}:{t['sor']}  [{t['fajta']}] {t['cel'][:60]!r}  | {t['szoveg'][:90]}")
    riport = runs / time.strftime("link-lezer-%Y%m%d-%H%M%S.json")
    riport.write_text(json.dumps({"jegyzetek": fajlok, "core": core_ossz, "szerkeszto": lezer_ossz, "frontmatter": fm_ossz,
                                  "osszesites": dict(ossz), "kapu": [[rp, t] for rp, t in kapu],
                                  "fajlonkent": fajl_elteres}, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"[linkek] riport: {riport}")
    if kapu:
        print(f"ELTÉR: {len(kapu)} link a kód- vagy képletszerkezetekben (a kapu)")
        for rp, t in kapu[:20]:
            print(f"    {rp}:{t['sor']}  {t['oldal']}  {t['ok']}  {t['cel'][:60]!r}")
        return 1
    print("RENDBEN: a kerítéses kódban, a soron belüli kódban és a képletben a core és a szerkesztő ugyanazt látja")
    return 0


if __name__ == "__main__":
    sys.exit(main())
