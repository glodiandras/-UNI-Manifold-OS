"""Az „erősen módosult” küszöb mérése a vault pillanatkép-tárolójának előzményein (C23b; `docs/C23-TERV.md` 6. fejezet).

    python -m modulok.kartya.kuszob_meres [--git <vault.git>] [--ki <jelentés.json>] [--minta 20]

**Csak olvas**: a `vault.git`-et `GIT_OPTIONAL_LOCKS=0`-val, `git log` és `git cat-file --batch` hívással (a vaulthoz és a
munkafához nem nyúl). Jegyzetenként (tartalmi `.md`) az egymást követő pillanatképek közti változást a közös mértékkel
(`core.automatika.valtozas`: hosszal súlyozott mondathalmaz-Jaccard-távolság és az új mondatok karaktere) méri, az
eloszlásból küszöböt javasol (a kis szerkesztés és az átírás közti völgy), és mintát ad a küszöb két oldaláról a jóváhagyáshoz.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from collections import defaultdict

from core import automatika as A
from core import config


def _git(gitdir: str, *args, bemenet: bytes | None = None) -> bytes:
    env = {**os.environ, "GIT_OPTIONAL_LOCKS": "0"}
    return subprocess.run(["git", f"--git-dir={gitdir}", *args], input=bemenet, capture_output=True, check=True,
                          env=env).stdout


def valtozatok(gitdir: str, szuro=A.tartalmi_ut) -> dict[str, list[tuple[str, str, str]]]:
    """Jegyzetenként a változatok `(commit, blob, dátum)` időrendben (a törlés kimarad)."""
    ki: dict[str, list[tuple[str, str, str]]] = defaultdict(list)
    log = _git(gitdir, "log", "--reverse", "--format=C %H %cI", "--raw", "--no-renames", "-z", "--", "*.md").decode("utf-8", "replace")
    commit = datum = None
    reszek = log.split("\x00")
    i = 0
    while i < len(reszek):
        r = reszek[i].lstrip("\n")
        if r.startswith("C "):
            sor, _, maradek = r.partition("\n")
            _, commit, datum = sor.split(" ", 2)
            r = maradek.lstrip("\n")
        if r.startswith(":"):
            mezok = r[1:].split()
            ut = reszek[i + 1] if i + 1 < len(reszek) else ""
            i += 2
            if len(mezok) >= 5 and mezok[4] != "D" and ut.lower().endswith(".md") and szuro(ut):
                ki[ut].append((commit, mezok[3], datum))
            continue
        i += 1
    return ki


def blobok(gitdir: str, shak: list[str]) -> dict[str, str]:
    if not shak:
        return {}
    ki = {}
    out = _git(gitdir, "cat-file", "--batch", bemenet=("\n".join(shak) + "\n").encode())
    p = 0
    for s in shak:
        fej_vege = out.index(b"\n", p)
        fej = out[p:fej_vege].split()
        n = int(fej[2])
        ki[s] = out[fej_vege + 1:fej_vege + 1 + n].decode("utf-8", "replace")
        p = fej_vege + 1 + n + 1
    return ki


def mer(gitdir: str, max_jegyzet: int | None = None, log=lambda s: None, szuro=A.tartalmi_ut) -> list[dict]:
    v = valtozatok(gitdir, szuro)
    utak = sorted(u for u, x in v.items() if len(x) >= 2)[:max_jegyzet]
    log(f"{len(v)} jegyzet, ebből {len(utak)} legalább két változattal")
    parok = []
    for n, u in enumerate(utak):
        lista = v[u]
        tart = blobok(gitdir, sorted({b for _, b, _ in lista}))
        elozo = None
        for commit, blob, datum in lista:
            m = A.mondatok(tart[blob])
            if elozo is not None and m != elozo[0]:
                val = A.valtozas(elozo[0], m)
                parok.append({"ut": u, "commit": commit[:12], "datum": datum, "tavolsag": val.tavolsag,
                              "uj_karakter": val.uj_karakter, "hossz": A.hossz(m), "elozo_hossz": A.hossz(elozo[0]),
                              "uj_mondatok": sorted(m - elozo[0], key=len, reverse=True)[:3],
                              "eltunt_mondatok": sorted(elozo[0] - m, key=len, reverse=True)[:2]})
            elozo = (m,)
        if n % 200 == 0:
            log(f"{n}/{len(utak)} jegyzet, {len(parok)} változáspár")
    return parok


def osszegez(parok: list[dict], kuszob: float | None = None, uj_karakter: int = 600, minta: int = 20) -> dict:
    """Eloszlás (tized-vödrök), javasolt küszöb (a 0,1–0,6 sáv legritkább vödrének közepe, ha nincs megadva), és minta a
    küszöb két oldaláról (fele alatta, fele fölötte, a küszöbhöz legközelebbiek)."""
    vodrok = [0] * 10
    for p in parok:
        vodrok[min(9, int(p["tavolsag"] * 10))] += 1
    if kuszob is None:
        sav = range(1, 6)
        i = min(sav, key=lambda k: vodrok[k])
        kuszob = round(i / 10 + 0.05, 2)
    fole = sorted((p for p in parok if p["tavolsag"] >= kuszob), key=lambda p: p["tavolsag"])
    ala = sorted((p for p in parok if p["tavolsag"] < kuszob), key=lambda p: -p["tavolsag"])
    erosen = sum(1 for p in parok if p["tavolsag"] >= kuszob or p["uj_karakter"] >= uj_karakter)
    return {"parok": len(parok), "vodrok": {f"{k / 10:.1f}–{(k + 1) / 10:.1f}": c for k, c in enumerate(vodrok)},
            "kuszob": kuszob, "uj_karakter": uj_karakter, "erosen_modosult": erosen,
            "arany": round(erosen / len(parok), 3) if parok else None,
            "minta_alatta": ala[:minta // 2], "minta_folotte": fole[:minta // 2]}


MUVELETEK = ("elgepeles_3", "mondat_1", "bekezdes_4", "szakasz_30", "atiras_50")


def szintetikus(gitdir: str, szuro, n: int = 60, seed: int = 23) -> dict:
    """A vault HEAD-jének `n` tantárgyi jegyzetén (csak olvasva) jellemző szerkesztések a mondathalmaz szintjén: 3 mondat elgépelése,
    1 mondat, egy 4 mondatos bekezdés, egy a jegyzet ~30%-ának megfelelő új szakasz (más jegyzet mondataiból), a mondatok felének
    átírása. → műveletenként a távolság és az új karakter, és küszöbönként, hány esetben „erős” a döntés."""
    import random
    r = random.Random(seed)
    fa = _git(gitdir, "ls-tree", "-r", "-z", "HEAD").decode("utf-8", "replace").split("\x00")
    jegy = [(x.split("\t", 1)[1], x.split()[2]) for x in fa if "\t" in x]
    jegy = [(u, b) for u, b in jegy if u.lower().endswith(".md") and szuro(u)]
    r.shuffle(jegy)
    tart = blobok(gitdir, [b for _, b in jegy[:n * 3]])
    halmazok = [(u, A.mondatok(tart[b])) for u, b in jegy[:n * 3]]
    halmazok = [(u, m) for u, m in halmazok if A.hossz(m) >= 400][:n]
    keszlet = [x for _, m in halmazok for x in m]
    ki = {mv: [] for mv in MUVELETEK}
    for u, m in halmazok:
        lista = sorted(m)
        idegen = [x for x in r.sample(keszlet, min(len(keszlet), 400)) if x not in m]

        def mert(uj):
            v = A.valtozas(m, frozenset(uj))
            return {"ut": u, "tavolsag": v.tavolsag, "uj_karakter": v.uj_karakter, "hossz": A.hossz(m)}
        valt = set(lista)
        for x in r.sample(lista, min(3, len(lista))):
            valt.discard(x)
            i = r.randrange(len(x))
            valt.add(x[:i] + "x" + x[i + 1:])
        ki["elgepeles_3"].append(mert(valt))
        ki["mondat_1"].append(mert(m | set(idegen[:1])))
        ki["bekezdes_4"].append(mert(m | set(idegen[1:5])))
        cel, plusz = 0.3 * A.hossz(m), []
        for x in idegen[5:]:
            if sum(map(len, plusz)) >= cel:
                break
            plusz.append(x)
        ki["szakasz_30"].append(mert(m | set(plusz)))
        fele = set(r.sample(lista, len(lista) // 2))
        ki["atiras_50"].append(mert((m - fele) | set(idegen[-len(fele):])))
    o = {}
    for mv, lista in ki.items():
        t = sorted(x["tavolsag"] for x in lista)
        o[mv] = {"db": len(t), "tavolsag_median": t[len(t) // 2] if t else None,
                 "tavolsag_p10_p90": [t[int(len(t) * 0.1)], t[int(len(t) * 0.9)]] if t else None,
                 "eros": {str(k): sum(1 for x in lista if x["tavolsag"] >= k or x["uj_karakter"] >= 600)
                          for k in (0.2, 0.3, 0.4)}}
    return {"jegyzetek": len(halmazok), "muveletek": o, "reszletek": ki}


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(prog="kuszob_meres")
    ap.add_argument("--git")
    ap.add_argument("--ki")
    ap.add_argument("--kuszob", type=float)
    ap.add_argument("--minta", type=int, default=20)
    ap.add_argument("--max", type=int)
    ap.add_argument("--minden", action="store_true", help="minden tartalmi jegyzet (alap: az automatikus kártya-szűrő)")
    ap.add_argument("--szintetikus", type=int, default=0, help="ennyi jegyzeten a jellemző szerkesztések mérése is")
    a = ap.parse_args(argv)
    cfg = config.load()
    gitdir = a.git or str(cfg.path("vault_git"))
    from core import kartya_feladat
    szuro = A.tartalmi_ut if a.minden else kartya_feladat.automatikus_szuro(cfg)
    parok = mer(gitdir, a.max, log=lambda s: print(s, file=sys.stderr, flush=True), szuro=szuro)
    o = osszegez(parok, a.kuszob, int(cfg.section("kartya", "automatika").get("uj_karakter", 600)), a.minta)
    sz = szintetikus(gitdir, szuro, a.szintetikus) if a.szintetikus else None
    if sz:
        o["szintetikus"] = sz["muveletek"]
    szoveg = json.dumps({"osszegzes": o, "parok": parok, "szintetikus": sz}, ensure_ascii=False, indent=1)
    if a.ki:
        with open(a.ki, "w", encoding="utf-8") as f:
            f.write(szoveg)
    print(json.dumps({k: v for k, v in o.items() if not k.startswith("minta")}, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
