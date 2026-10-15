"""C12 / K11 — Obsidian-paritás: a 2.0 Bases-lekérdezése az Obsidian CSV-exportjával összevetve (a discover nem futtatja).

    bin/mos exec var/venv/bin/python -B tests/kezi/bazis_paritas.py <próbavault> <CSV-mappa> [--cellak]

Előkészület (kézi):
  1. `var/venv/bin/python -B tests/kezi/bazis_proba.py <üres ideiglenes könyvtár>` → a próbavault.
  2. A próbavaultot Obsidian 1.11.7-ben megnyitni, és mind a 9 nézetet CSV-be exportálni (Results → Export CSV),
     a fájlneveken, amelyeket a `bazis_proba.py` kiír (`<base neve> - <nézet neve>.csv`).
  3. Ez a szkript.

A szkript a próbavaultra ideiglenes indexet épít (a `{tmp}` alatt, a végén törlődik; a vaultba nem ír), lekérdezi
mind a 9 nézetet a 2.0 kiértékelőjével, és a CSV **első oszlopát** (a `file.path`) veti össze: sorhalmaz ÉS sorrend.
Az első sor fejléc, ha az első cellája nem a vault egy fájlútja. Kilépési kód: 0, ha minden nézet sorhalmaza és sorrendje
azonos (0 eltérés = zöld); 1, ha bármi eltér vagy hiányzik.

`--cellak`: a többi oszlop szövegét is összeveti (csak tájékoztató; az Obsidian megjelenítési formátumai eltérhetnek,
ezért nem számít a végeredménybe) — a javító körben segít kideríteni, melyik cella tér el.
"""
import csv
import shutil
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
from core import config  # noqa: E402
from _kornyezet import cfg_elkulonitve, probamappa  # noqa: E402
from core.bazis.api import Bazisok  # noqa: E402
from core.index import indexelo  # noqa: E402
from tests.kezi import bazis_proba  # noqa: E402


def csv_beolvas(p: Path) -> list[list[str]]:
    """A CSV sorai (UTF-8, BOM-mal is; vessző vagy pontosvessző elválasztóval)."""
    szoveg = p.read_text(encoding="utf-8-sig")
    elso = szoveg.split("\n", 1)[0]
    elvalaszto = ";" if elso.count(";") > elso.count(",") else ","
    return [sor for sor in csv.reader(szoveg.splitlines(), delimiter=elvalaszto) if any(c.strip() for c in sor)]


def ut_tiszta(s: str) -> str:
    """A cella útja: szóköz, `[[ ]]`, visszaper → vault-út."""
    s = s.strip().replace("\\", "/")
    if s.startswith("[[") and s.endswith("]]"):
        s = s[2:-2].split("|", 1)[0]
    return s


def cella_szoveg(x) -> str:
    """A 2.0 cella egyszerű szövege (a CSV-vel való összevetéshez)."""
    if x is None:
        return ""
    if isinstance(x, bool):
        return "true" if x else "false"
    if isinstance(x, float) and x == int(x):
        return str(int(x))
    if isinstance(x, dict):
        t = x.get("t")
        if t == "datum":
            return x["iso"].replace("T", " ")
        if t == "link":
            return x.get("ut") or x.get("cel") or ""
        if t == "lista":
            return ", ".join(cella_szoveg(e) for e in x["e"])
        if t == "cimke":
            return x["v"]
        if t == "hiba":
            return "#HIBA " + x["u"]
        return str(x)
    return str(x)


def egyszerusit(s: str) -> str:
    return s.strip().replace("[[", "").replace("]]", "").replace("T", " ").lower()


def hasonlit(kulcs, vart: list[str], kapott: list[str]) -> list[str]:
    """Az eltérések leírása (üres lista: azonos halmaz és sorrend)."""
    hibak = []
    hiany = [u for u in vart if u not in kapott]
    tobb = [u for u in kapott if u not in vart]
    ism = sorted({u for u in kapott if kapott.count(u) > 1})
    if hiany:
        hibak.append(f"hiányzik az Obsidian-exportból ({len(hiany)}): {hiany}")
    if tobb:
        hibak.append(f"az Obsidian-exportban több van ({len(tobb)}): {tobb}")
    if ism:
        hibak.append(f"ismétlődő sor az exportban: {ism}")
    if not hiany and not tobb and vart != kapott:
        i = next(i for i, (a, b) in enumerate(zip(vart, kapott)) if a != b)
        hibak.append(f"azonos halmaz, de más a sorrend: a(z) {i + 1}. sor a 2.0-ban {vart[i]!r}, az Obsidianban {kapott[i]!r}")
    return hibak


def main(argv: list[str]) -> int:
    args = [a for a in argv[1:] if not a.startswith("--")]
    cellak = "--cellak" in argv
    if len(args) != 2:
        print(__doc__)
        return 2
    vault, csvmappa = Path(args[0]).expanduser().resolve(), Path(args[1]).expanduser().resolve()
    if not vault.is_dir() or not csvmappa.is_dir():
        print(f"A próbavault vagy a CSV-mappa nem létezik: {vault} / {csvmappa}")
        return 2

    cfg0 = config.load()
    d = probamappa(cfg0, "c12-paritas", szkript="bazis_paritas.py")
    cfg = cfg_elkulonitve(d, cfg0, vault=vault)          # a próbavault csak olvasva; minden más út a próbamappába
    ix = indexelo.Index(cfg)
    ix.figyelo_fajta = "lekerdezes"
    ix.lekerdezes_mp = 3600
    ix.indit()
    ix.var(300)
    eredmeny = []                                            # (kulcs, [eltérések], tájékoztató)
    try:
        b = Bazisok(cfg, ix)
        utak = set(s["ut"] for s in b.lekerdez({"szoveg": "views:\n  - type: table\n"})["sorok"])
        for fajl, nezet in bazis_proba.NEZETEK:
            kulcs = f"{fajl} / {nezet}"
            v = b.lekerdez({"szoveg": (vault / fajl).read_text(encoding="utf-8"), "ez": fajl, "nezet": nezet})
            if not v["ok"] or (v["nezet"] or {}).get("nev") != nezet:
                eredmeny.append((kulcs, [f"a 2.0 nem tudta lekérdezni: {v['hibak']}"], []))
                continue
            vart = [s["ut"] for s in v["sorok"]]
            p = csvmappa / bazis_proba.csv_nev(fajl, nezet)
            if not p.is_file():
                eredmeny.append((kulcs, [f"hiányzik a CSV: {p.name}"], []))
                continue
            sorok = csv_beolvas(p)
            fejlec = bool(sorok) and ut_tiszta(sorok[0][0]) not in utak
            adat = sorok[1:] if fejlec else sorok
            kapott = [ut_tiszta(s[0]) for s in adat]
            if kapott and not any(u in utak for u in kapott):
                eredmeny.append((kulcs, [f"az első oszlop nem fájlút (pl. {kapott[0]!r}): a nézet `order`-ének első eleme "
                                         "a `file.path` — a CSV nem ezt tartalmazza?"], []))
                continue
            hibak = hasonlit(kulcs, vart, kapott)
            info = []
            if cellak and not hibak:
                oszl = [o["nev"] for o in v["oszlopok"]]
                for s, sor in zip(v["sorok"], adat):
                    for j, c in enumerate(s["cellak"][1:], 1):
                        if j >= len(sor):
                            info.append(f"{s['ut']}: a CSV-ben nincs {oszl[j]!r} oszlop")
                            break
                        if egyszerusit(cella_szoveg(c)) != egyszerusit(sor[j]):
                            info.append(f"{s['ut']} / {oszl[j]}: 2.0 {cella_szoveg(c)!r} ≠ Obsidian {sor[j]!r}")
            eredmeny.append((kulcs, hibak, info, len(vart)))
    finally:
        ix.leallit()
        shutil.rmtree(d, ignore_errors=True)                 # a saját var/tmp próbamappánk

    rossz = 0
    for e in eredmeny:
        kulcs, hibak, info = e[0], e[1], e[2]
        if hibak:
            rossz += 1
            print(f"ELTÉR   {kulcs}")
            for h in hibak:
                print(f"          {h}")
        else:
            print(f"EGYEZIK {kulcs}  ({e[3]} sor)")
        for i in info[:20]:
            print(f"          (tájékoztató) {i}")
        if len(info) > 20:
            print(f"          (tájékoztató) … és még {len(info) - 20} cella-eltérés")
    print()
    if rossz:
        print(f"ELTÉRÉS: {rossz} nézet / {len(eredmeny)} — javító kör kell (a NAPLO-ba: nézet, 2.0-sorok, Obsidian-sorok).")
        return 1
    print(f"RENDBEN: mind a(z) {len(eredmeny)} nézet sorhalmaza és sorrendje azonos az Obsidian exportjával (0 eltérés).")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
