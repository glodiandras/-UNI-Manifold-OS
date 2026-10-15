"""A `kod` aranyhalmaz építése és gépi ellenőrzése (C36b) — minden fordítás és futtatás a program-homokozóban.

    bin/mos exec <python> -B modulok/eval/kod/keszit.py [--ellenoriz | --ir] [--feladat k01 …] [--menet 100]

Feladatonként (`feladatok/kNN/`: `leiras.md` teszt-blokkokkal, `ref.cpp`, `lassu.cpp`, `bemenet.py` generátorral és
validátorral, `meta.json` a beültetett hibákkal):

1. a `ref.cpp` és a `lassu.cpp` lefordul, és a leírás minden tesztjén átmegy;
2. `--menet` kicsi véletlen bemeneten (mag = 1, 2, …; a validátor mindet elfogadja) a kettő kimenete egyezik, és egy nagy bemeneten
   a `ref` az időkorlát felén belül fut;
3. minden hiba egysoros csere (`sor`-adik sora pontosan az `eredeti`), lefordul, és **lelepleződik**: az első elbukó teszt-blokk,
   különben az első eltérő kicsi véletlen bemenet, különben a nagy bemenet (időtúllépés vagy eltérés). A leleplező eset a hiba
   **bizonyítéka**; ezt kapja a modell a `hiba`/`tipp`/`megoldas` tételben (ahogy élesben az ellenőrzés eredményét).

`--ir`: a sikeres ellenőrzés után az `arany.json` (a fájlok sha256-ja, a befagyasztott bizonyítékok) újraíródik; a `verzio` és az
`allapot` (vázlat → jóváhagyott) a meglévő fájlból marad. `--ir` nélkül csak ellenőriz, és összeveti a meglévő `arany.json`-nal.
Kilépési kód: 0 rendben, 1 hiba.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import random
import sys
from pathlib import Path

ITT = Path(__file__).resolve().parent
REPO = ITT.parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from core import cpp_teszt  # noqa: E402
from modulok.cpp import ai_ellenorzes as AE  # noqa: E402

FAJLOK = ("leiras.md", "ref.cpp", "lassu.cpp", "bemenet.py", "meta.json")
MENET = 100
FAJTAK = ("index", "tulcsordulas", "inicializalas", "alapeset", "ido", "feltetel", "sorrend", "egyeb")


def feladat_mappak(szurt: list[str] | None = None) -> list[Path]:
    m = sorted(p for p in (ITT / "feladatok").iterdir() if p.is_dir() and (p / "meta.json").is_file())
    return [p for p in m if not szurt or p.name in szurt]


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def bemenet_modul(mappa: Path):
    spec = importlib.util.spec_from_file_location(f"kod_bemenet_{mappa.name}", mappa / "bemenet.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def valtozat(ref: str, h: dict) -> str:
    """A hibás változat: a `ref` `sor`-adik sora (1-től) pontosan az `eredeti`, helyette a `csere`."""
    sorok = ref.split("\n")
    i = int(h["sor"]) - 1
    if not 0 <= i < len(sorok) or sorok[i] != h["eredeti"]:
        raise ValueError(f"{h['id']}: a {h['sor']}. sor nem az `eredeti` (ott: {sorok[i] if 0 <= i < len(sorok) else '—'!r})")
    sorok[i] = h["csere"]
    return "\n".join(sorok)


def betolt(mappa: Path) -> dict:
    meta = json.loads((mappa / "meta.json").read_text(encoding="utf-8"))
    leiras = (mappa / "leiras.md").read_text(encoding="utf-8")
    return {"mappa": mappa, "meta": meta, "leiras": leiras, "ref": (mappa / "ref.cpp").read_text(encoding="utf-8"),
            "lassu": (mappa / "lassu.cpp").read_text(encoding="utf-8"), "tesztek": cpp_teszt.tesztek(leiras, 10.0, 1024),
            "bemenet": bemenet_modul(mappa)}


def bemenetek(bm, menet: int) -> list[str]:
    return [bm.general(random.Random(mag), "kicsi") for mag in range(1, menet + 1)]


def nagy_bemenet(bm) -> str:
    return bm.general(random.Random(1), "nagy")


def _leiras_nagy(bem: str) -> str:
    elso = bem.split("\n", 1)[0].strip()
    return f"egy nagy bemeneten (első sora: {elso[:40]})"


def ellenoriz(f: AE.Futtato, fd: dict, menet: int, log=print) -> dict:
    """Egy feladat ellenőrzése. → `{hibak: [{…, bizonyitek}], hibaüzenetek: [...], ido_ms_ref_nagy}`."""
    meta, hibak_ki, gond = fd["meta"], [], []
    fid = meta["id"]
    idokorlat = float(meta.get("idokorlat_s") or 1.0)
    if fid != fd["mappa"].name:
        gond.append(f"az id ({fid}) nem egyezik a mappa nevével")
    if any(t.hiba for t in fd["tesztek"]) or not fd["tesztek"]:
        gond.append("a leírás teszt-blokkjai hibásak vagy hiányoznak")
    ref = f.fordit(fd["ref"], "ref")
    lassu = f.fordit(fd["lassu"], "lassu")
    for nev, p in (("ref", ref), ("lassu", lassu)):
        if not p.ok:
            gond.append(f"a {nev}.cpp nem fordul: {p.uzenet} {p.diagnosztika[:2]}")
    if gond:
        return {"hibak": [], "gond": gond}
    for nev, p in (("ref", ref), ("lassu", lassu)):
        t = AE.teszt_futas(f, p, fd["tesztek"])
        if t["atment_db"] != t["ossz"]:
            rossz = [(e["sorszam"], e["kapott"][:60]) for e in t["eredmenyek"] if not e["atment"]]
            gond.append(f"a {nev}.cpp elbukik a leírás tesztjein: {rossz}")
    kicsik = bemenetek(fd["bemenet"], menet)
    ervenytelen = [i + 1 for i, b in enumerate(kicsik) if not fd["bemenet"].ervenyes(b)]
    if ervenytelen:
        gond.append(f"a validátor elutasítja a generált kicsi bemenetet (mag: {ervenytelen[:5]})")
    ref_ki = []
    for i, b in enumerate(kicsik, 1):
        a = f.futtat(ref, b, idokorlat_s=idokorlat)
        c = f.futtat(lassu, b, idokorlat_s=AE.REFERENCIA_IDOKORLAT_S)
        ref_ki.append(a["stdout"])
        if a["allapot"] != "ok" or c["allapot"] != "ok" or not AE.egyezik(a["stdout"], c["stdout"]):
            gond.append(f"a ref és a lassú eltér (mag {i}): {b[:80]!r} → {a['stdout'][:40]!r} / {c['stdout'][:40]!r} "
                        f"({a['allapot']}/{c['allapot']})")
            break
    nagy = nagy_bemenet(fd["bemenet"])
    if not fd["bemenet"].ervenyes(nagy):
        gond.append("a validátor elutasítja a nagy bemenetet")
    rn = f.futtat(ref, nagy, idokorlat_s=idokorlat)
    if rn["allapot"] != "ok" or rn["ido_ms"] > idokorlat * 1000 / 2:
        gond.append(f"a ref a nagy bemeneten: {rn['allapot']}, {rn['ido_ms']} ms (a korlát fele: {idokorlat * 500:g} ms)")
    log(f"  {fid}: ref/lassú {menet} bemeneten, ref a nagyon {rn['ido_ms']:.0f} ms")
    sorok = set()
    for h in meta["hibak"]:
        if h.get("fajta") not in FAJTAK:
            gond.append(f"{h['id']}: ismeretlen fajta {h.get('fajta')!r}")
        if h["sor"] in sorok:
            gond.append(f"{h['id']}: két hiba ugyanazon a soron")
        sorok.add(h["sor"])
        try:
            kod = valtozat(fd["ref"], h)
        except ValueError as exc:
            gond.append(str(exc))
            continue
        p = f.fordit(kod, h["id"])
        if not p.ok:
            gond.append(f"{h['id']}: a hibás változat nem fordul: {p.diagnosztika[:1]}")
            continue
        biz = None
        t = AE.teszt_futas(f, p, fd["tesztek"])
        if t["elbukott"]:
            e = next(x for x in t["eredmenyek"] if not x["atment"])
            tt = next(x for x in fd["tesztek"] if x.sorszam == e["sorszam"])
            biz = {"fajta": "teszt", "forras": f"teszt-{tt.sorszam}", "allapot": e["allapot"], "bemenet": tt.bemenet,
                   "vart": tt.kimenet, "kapott": e["kapott"]}
        if biz is None:
            for i, b in enumerate(kicsik):
                r = f.futtat(p, b, idokorlat_s=idokorlat)
                if r["allapot"] != "ok" or not AE.egyezik(ref_ki[i], r["stdout"]):
                    biz = {"fajta": "teszt", "forras": f"kicsi-{i + 1}", "allapot": r["allapot"] if r["allapot"] != "ok"
                           else "hibas_kimenet", "bemenet": b, "vart": ref_ki[i], "kapott": r["stdout"]}
                    break
        if biz is None:
            r = f.futtat(p, nagy, idokorlat_s=idokorlat)
            if r["allapot"] == "idotullepes":
                biz = {"fajta": "ido", "forras": "nagy", "allapot": "idotullepes", "leiras": _leiras_nagy(nagy)}
            elif r["allapot"] != "ok" or not AE.egyezik(rn["stdout"], r["stdout"]):
                biz = {"fajta": "nagy", "forras": "nagy", "allapot": r["allapot"] if r["allapot"] != "ok" else "hibas_kimenet",
                       "leiras": _leiras_nagy(nagy), "vart": rn["stdout"][:200], "kapott": r["stdout"][:200]}
        if biz is None:
            gond.append(f"{h['id']}: a hiba nem leplezhető le (a tesztek, {menet} kicsi és a nagy bemenet mind jó)")
            continue
        if h["fajta"] == "ido" and biz["fajta"] != "ido":
            gond.append(f"{h['id']}: `ido` fajtájú hiba, de nem időtúllépés leplezi le ({biz['forras']})")
        log(f"    {h['id']} ({h['fajta']}, {h['sor']}. sor): leleplezi {biz['forras']} ({biz['allapot']})")
        hibak_ki.append({**h, "bizonyitek": biz})
    return {"hibak": hibak_ki, "gond": gond, "ref_nagy_ms": rn["ido_ms"]}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="A kod aranyhalmaz ellenőrzése a program-homokozóban.")
    ap.add_argument("--ir", action="store_true", help="sikeres ellenőrzés után az arany.json újraírása")
    ap.add_argument("--ellenoriz", action="store_true", help="csak ellenőrzés és összevetés a meglévő arany.json-nal (az alap)")
    ap.add_argument("--feladat", action="append", help="csak ezek (ismételhető); --ir mellett nem használható")
    ap.add_argument("--menet", type=int, default=MENET)
    a = ap.parse_args(argv)
    if a.ir and a.feladat:
        ap.error("az --ir a teljes halmazt írja (--feladat nélkül)")
    if a.ir and a.ellenoriz:
        ap.error("az --ir és az --ellenoriz kizárja egymást")
    from core import config
    cfg = config.load()
    regi = json.loads((ITT / "arany.json").read_text(encoding="utf-8")) if (ITT / "arany.json").is_file() else {}
    feladatok, hibas = [], False
    with AE.Futtato(cfg) as f:
        h = f.hiany()
        if h:
            print(f"HIBA: {h}", file=sys.stderr)
            return 1
        for mappa in feladat_mappak(a.feladat):
            fd = betolt(mappa)
            r = ellenoriz(f, fd, a.menet)
            for g in r["gond"]:
                print(f"  HIBA {mappa.name}: {g}")
            hibas |= bool(r["gond"])
            m = fd["meta"]
            feladatok.append({"id": m["id"], "cim": m["cim"], "tema": m["tema"], "nehezseg": m["nehezseg"],
                              "idokorlat_s": m.get("idokorlat_s", 1.0),
                              "sha256": {n: sha(mappa / n) for n in FAJLOK}, "hibak": r["hibak"]})
    if not a.feladat and regi.get("feladatok"):
        elteres = [x["id"] for x, y in zip(feladatok, regi["feladatok"]) if x != y] + \
            ([] if len(feladatok) == len(regi["feladatok"]) else ["(a feladatok száma)"])
        print(f"az arany.json-nal {'egyezik' if not elteres else 'ELTÉR: ' + ', '.join(elteres)}")
    if hibas:
        print("HIBA: az aranyhalmaz nem ment át az ellenőrzésen")
        return 1
    if a.ir:
        ki = {"verzio": regi.get("verzio", "v1"), "allapot": regi.get("allapot", "vazlat"), "keszult": regi.get("keszult"),
              "jovahagyva": regi.get("jovahagyva"), "leiras": regi.get("leiras", ""), "menet": a.menet, "feladatok": feladatok}
        (ITT / "arany.json").write_text(json.dumps(ki, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        print(f"arany.json írva: {len(feladatok)} feladat, {sum(len(x['hibak']) for x in feladatok)} hiba")
    print("RENDBEN")
    return 0


if __name__ == "__main__":
    sys.exit(main())
