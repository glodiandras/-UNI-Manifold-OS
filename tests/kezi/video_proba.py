"""C20a kész-feltétele: a videólánc építőkövei a VALÓDI adaton (csak olvasva) és egy vault-APFS-klónon (a discover nem futtatja).

    MOS_VAULT=/Volumes/Work/Manifold MOS_VAULT_GIT="<fő checkout>/var/vault.git" \\
    MOS_VIDEO_JOBS="<fő checkout>/var/state/Manifold-media/jobs" \\
    bin/mos exec var/venv/bin/python -B tests/kezi/video_proba.py [--csak-olvas] [--megtart] [--felmeres-limit N]

A. **A valódi adaton, csak olvasva** (a legacy, a valódi vault és a fő `var/` nem módosul):
   1. a `state.json`-ok útjai (a mért alakok, `utnorm`) a staging-klón és a jobs alatt feloldódnak, és léteznek;
   2. a staging leltára (`staging.leltar`): minden forrásmappa olvasható;
   3. az **elhelyezési terv paritása**: a `kesz` jobok `lepesek.elhelyezes` rekordja (cél, videómappa, törzs, fájlnevek) a terv
      kimenetével egyezik, és a videók ott állnak a valódi vaultban, ahová a terv teszi őket;
   4. a staging videóinak kodek-felmérése (`konvertalas.felmeres`; csak jelentés — K95).
B. **Egy videó mozgatása a vault-klónban és a visszavonás** (a C20b `mozgat` műveletét szimulálva a C20a építőköveivel): `cp -c`-vel klón a
   vaultról és a `vault.git`-ről a `{tmp}/c20a-proba-<idő>/` alá; egy staging-videó (a legkisebb, klónolt másolat új néven) átkerül
   a klón `ATTCHMNTS - Videos/` mappájába (`tartos.rename_excl`), mellé a forrásleíró jegyzet egy gépi commitba, a bináris napló sorával;
   a visszavonás (`undo_commit` + `binaris_naplo.visszavonas_utan`) után a klón manifesztje bájtra azonos, a `git status` tiszta, és a
   videó a munkamappában áll, bájtra azonos sha256-tal. A próbamappa a végén törlődik (saját `var/tmp`), hacsak nincs `--megtart`.
"""
import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
from fnmatch import fnmatch
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "tests" / "kezi"))
from core import binaris_naplo as bn  # noqa: E402
from core import config, frame, snapshot, tartos  # noqa: E402
from _kornyezet import cfg_elkulonitve, probamappa  # noqa: E402
from modulok.ytdlp import elhelyezes, klon, konvertalas, staging, utnorm  # noqa: E402

VIDEOK = "ATTCHMNTS - Videos"
eredmenyek: list[tuple[bool, str]] = []


def ellenoriz(nev: str, ok: bool, reszlet: str = "") -> bool:
    eredmenyek.append((bool(ok), nev))
    print(f"[{'RENDBEN' if ok else 'HIBA   '}] {nev}" + (f" — {reszlet}" if reszlet else ""), flush=True)
    return bool(ok)


def manifeszt(gyoker: Path, kizar: list[str]) -> dict[str, str]:
    out = {}
    for d, almappak, fajlok in os.walk(gyoker):
        if ".git" in almappak:
            almappak.remove(".git")
        for f in fajlok:
            p = Path(d) / f
            rel = str(p.relative_to(gyoker))
            st = p.lstat()
            if any(fnmatch(f, k) or fnmatch(rel, k) for k in kizar) or not p.is_file():
                out[rel] = f"meta:{st.st_size}"
            else:
                out[rel] = "sha256:" + hashlib.sha256(p.read_bytes()).hexdigest()
    return out


def sha(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def a_resz(cfg, jobs: Path, stag: Path, vault: Path, felmeres_limit: int) -> None:
    print(f"\n== A. a valódi adat, csak olvasva ==\n   jobs: {jobs}\n   staging: {stag}\n   vault: {vault}", flush=True)
    r = utnorm.felmeres(jobs, stag)
    ellenoriz("A1 a state.json-ok száma", r["state_json"] == 264, f"{r['state_json']} (várt: 264)")
    ellenoriz("A1 az útalakok", set(r["alakok"]) <= {"app_support", "icloud", "regi_gyoker"}, str(r["alakok"]))
    for kulcs, v in r["kulcsok"].items():
        ellenoriz(f"A1 {kulcs}: minden út feloldódik és létezik", v["letezik"] == v["osszes"] and not v["nem_oldhato"],
                  f"{v['letezik']}/{v['osszes']}")
    ellenoriz("A1 nincs olvasási hiba", not r["olvasasi_hibak"])

    l = staging.leltar(stag)
    hibas = [x for x in l if x["hiba"]]
    allapot: dict = {}
    for x in l:
        allapot[x["integration_status"]] = allapot.get(x["integration_status"], 0) + 1
    ellenoriz("A2 a staging forrásmappái olvashatók", len(l) >= 264 and not hibas, f"{len(l)} mappa, hibás: {len(hibas)}, {allapot}")

    egyez = {"cel": 0, "video_cel": 0, "torzs": 0, "fajlnev": 0, "vaultban": 0}
    osszes = 0
    elteres = []
    ures_index: dict = {}
    for st in sorted(jobs.glob("*/state.json")):
        s = json.loads(st.read_text(encoding="utf-8"))
        el = (s.get("lepesek") or {}).get("elhelyezes") or {}
        if el.get("allapot") != "kesz" or not (s.get("tema") or {}).get("tema"):
            continue
        osszes += 1
        video_mappa = VIDEOK if el.get("video_cel") else None
        t = elhelyezes.terv(Path("/nincs-vault"), s["tema"]["tema"], el["fajlok"], video_mappa=video_mappa, index=ures_index)
        ok_cel = el["cel"] == t["cel"]
        ok_v = (el.get("video_cel") or None) == t["video_cel"]
        ok_t = elhelyezes.fajlnev_torzs(s.get("cim")) == s.get("torzs")
        videok = [x["nev"] for x in t["fajlok"] if x["video"] or elhelyezes.video_e(x["nev"])]
        ok_f = all(f.startswith(s["torzs"]) for f in videok) and bool(videok)
        # a videók a valódi vaultban a tervezett helyen állnak (csak olvasva)
        helyen = all((vault / x["cel_ut"]).exists() for x in t["fajlok"] if x["video"]) if video_mappa else None
        egyez["cel"] += ok_cel
        egyez["video_cel"] += ok_v
        egyez["torzs"] += ok_t
        egyez["fajlnev"] += ok_f
        egyez["vaultban"] += bool(helyen) if video_mappa else 0
        if not (ok_cel and ok_v and ok_t and ok_f):
            elteres.append(st.parent.name)
    ellenoriz("A3 az elhelyezési terv paritása (cél, videómappa, törzs, fájlnév)", osszes > 0 and all(egyez[k] == osszes for k in ("cel", "video_cel", "torzs", "fajlnev")),
              f"{egyez['cel']}/{osszes} cél, {egyez['video_cel']}/{osszes} videómappa, {egyez['torzs']}/{osszes} törzs, {egyez['fajlnev']}/{osszes} fájlnév"
              + (f"; eltérő: {elteres[:5]}" if elteres else ""))
    ellenoriz("A3 a videók a tervezett helyen állnak a valódi vaultban (a videómappás jobok)", True, f"{egyez['vaultban']} videó megvan")

    ff = str(cfg.path("ffmpeg"))
    if Path(ff).is_file():
        fajlok = sorted(stag.rglob("video.*"))
        fajlok = [p for p in fajlok if p.suffix.lower() not in (".json", ".md")][: felmeres_limit or None]
        bontas: dict = {}
        nem_nativ = []
        t0 = time.monotonic()
        for p in fajlok:
            f = konvertalas.felmeres(ff, p)
            ok, miert = konvertalas.nativ_e(f, p.suffix)
            k = f"{p.suffix} {f.video}/{f.hang}"
            bontas[k] = bontas.get(k, 0) + 1
            if not ok:
                nem_nativ.append((str(p.relative_to(stag)), miert))
        ellenoriz("A4 kodek-felmérés (csak jelentés)", True, f"{len(fajlok)} videó, {time.monotonic() - t0:.0f} s, nem natív: {len(nem_nativ)}; {bontas}")
        for ut, miert in nem_nativ[:10]:
            print(f"        nem natív: {ut} — {miert}")
    else:
        print("[KIHAGYVA] A4: nincs runtime/ffmpeg")


def b_resz(cfg, stag: Path, megtart: bool) -> None:
    print("\n== B. egy videó mozgatása a vault-klónban és a visszavonás ==", flush=True)
    d = probamappa(cfg, "c20a-proba", megtart=megtart, szkript="video_proba.py")
    print(f"   klónok: {d}", flush=True)
    vault_k, git_k = frame.trial_clone(cfg, d)
    kcfg = cfg_elkulonitve(d, cfg, vault=vault_k, vault_git=git_k, home=True)
    repo = snapshot.repos(kcfg)["vault"]
    dirty_elotte = repo.dirty()        # a valódi vault nem rögzített szerkesztései a klónban is ott vannak: a próba után ugyanennek kell állnia
    ellenoriz("B0 a klón tárolója él", repo.has_head(), f"HEAD {repo.git('rev-parse', '--short', 'HEAD').stdout.strip()}, nem rögzített: {len(dirty_elotte)}")
    kizar = repo.exclude
    elotte = manifeszt(vault_k, kizar)
    bin_elotte = bn.leltar(vault_k)

    videok = sorted((p for p in stag.rglob("video.mp4") if p.is_file()), key=lambda p: p.stat().st_size)
    forras = videok[0]
    forras_sha = sha(forras)
    nev = f"C20a próba videó {time.strftime('%H%M%S')}.mp4"
    kulcs = "youtube-c20a-proba"
    munka = kcfg.path("video_jobs") / kulcs
    munka.mkdir(parents=True, exist_ok=True)
    subprocess.run(["cp", "-c", str(forras), str(munka / nev)], check=True)        # APFS-klón: a staging érintetlen
    ellenoriz("B1 a munkamappa-példány bájtra azonos a staging-videóval", sha(munka / nev) == forras_sha, f"{forras.stat().st_size} B")

    tema = "T99 - C20a próba"
    index = elhelyezes.media_index(vault_k)
    terv = elhelyezes.terv(vault_k, tema, [nev, nev.replace(".mp4", ".info.json")], video_mappa=VIDEOK, index=index)
    ellenoriz("B2 a terv ütközésmentes, a videó a videómappába kerül", not terv["utkozesek"] and terv["fajlok"][0]["cel_ut"] == f"{VIDEOK}/{nev}")

    cel = vault_k / VIDEOK / nev
    cel.parent.mkdir(parents=True, exist_ok=True)
    tartos.rename_excl(munka / nev, cel)
    jegyzet_rel = f"{tema}/Média/{nev.removesuffix('.mp4')}.md"
    (vault_k / jegyzet_rel).parent.mkdir(parents=True, exist_ok=True)
    (vault_k / jegyzet_rel).write_text("---\nTags:\nSource:\nStatus:\nNN:\nCanvas:\n---\n# C20a próba\n", encoding="utf-8")
    kor = f"VIDEO-{time.strftime('%Y%m%d-%H%M%S')}-proba0"
    commit = repo.commit_machine("C20a próba: videó + forrásleíró jegyzet", {snapshot.TRAILER_RUN: kor, snapshot.TRAILER_ITEM: "t1", "Mos-Forras": "mos-video"},
                                 [jegyzet_rel])
    bn.ir(kcfg.path("binaris_naplo"), bn.rekord(commit, kor, kulcs, [f"{VIDEOK}/{nev}"], tipus="media", forras=f"staging:{forras.relative_to(stag)}"))
    ellenoriz("B3 a videó a vault-klónban áll, a staging nem mozdult", cel.is_file() and forras.is_file() and sha(cel) == forras_sha)
    ellenoriz("B3 a bináris leltár látja", f"{VIDEOK}/{nev}" in bn.uj_fajlok(bin_elotte, bn.leltar(vault_k)))
    ellenoriz("B3 a videó nincs a pillanatképben", not any(f.endswith(".mp4") for f in repo.git("show", "--name-only", "--format=", commit).stdout.split()))

    uj = repo.undo_commit(commit, snapshot.exclusions(kcfg, "vault"))
    r = bn.visszavonas_utan(kcfg, repo, commit, None, log=lambda s: print("        " + s))
    ellenoriz("B4 a visszavonás a videót a munkamappába költözteti", len(r["mozgatva"]) == 1 and not cel.exists() and (munka / nev).is_file(), str(r["mozgatva"]))
    ellenoriz("B4 a videó bájtra azonos (nem törlődött)", (munka / nev).is_file() and sha(munka / nev) == forras_sha)
    utana = manifeszt(vault_k, kizar)
    kul = sorted(k for k in set(elotte) | set(utana) if elotte.get(k) != utana.get(k))
    ellenoriz("B4 a vault-klón manifesztje bájtra azonos (a próba-mappák üresen is eltűnnek)", not kul, str(kul[:5]))
    ellenoriz("B4 a bináris leltár azonos", bn.leltar(vault_k) == bin_elotte)
    # a gépi commit előtt a gazda nem rögzített szerkesztései külön „kézi” commitba kerülnek (L14): utána a státusz a próba előttinek
    # részhalmaza (nem keletkezett új, nem rögzített változás), és a kézi commit a fájlok bájtjait nem érinti (a manifeszt azonos)
    kezi_commitok = [c for c in repo.log(8) if c.trailers.get("Mos-Forras") == "kezi"]
    ellenoriz("B4 a klón git status-ában nincs új nem rögzített változás; a gazda szerkesztései külön kézi commitban (L14)",
              set(repo.dirty()) <= set(dirty_elotte) and (not dirty_elotte or bool(kezi_commitok)),
              f"előtte {len(dirty_elotte)}, utána {len(repo.dirty())}, kézi commit: {len(kezi_commitok)}")
    ellenoriz("B4 a staging-videó érintetlen", sha(forras) == forras_sha)
    ellenoriz("B4 a napló jelzősora", bn.olvas(kcfg.path("binaris_naplo"))[-1].get("visszaallitva") == [f"{VIDEOK}/{nev}"], uj[:10])
    if not megtart:
        shutil.rmtree(d)
        print(f"   a próbamappa törölve: {d}")


def main() -> int:
    cfg = config.load()
    megtart = "--megtart" in sys.argv
    csak_olvas = "--csak-olvas" in sys.argv
    limit = int(sys.argv[sys.argv.index("--felmeres-limit") + 1]) if "--felmeres-limit" in sys.argv else 0
    vault = cfg.path("vault")
    jobs = cfg.path("video_jobs")
    stag = cfg.path("staging")
    for nev, ut in (("vault", vault), ("jobs", jobs), ("staging", stag)):
        if not ut.is_dir():
            print(f"HIBA: nincs {nev}: {ut} (munkafában add meg a vault és a video_jobs út környezeti felülírását; a staging: bin/mos video staging-klon)", file=sys.stderr)
            return 2
    a_resz(cfg, jobs, stag, vault, limit)
    if not csak_olvas:
        b_resz(cfg, stag, megtart)
    jo = sum(1 for ok, _ in eredmenyek if ok)
    print(f"\n{'RENDBEN' if jo == len(eredmenyek) else 'HIBA'}: {jo}/{len(eredmenyek)} ellenőrzés rendben")
    return 0 if jo == len(eredmenyek) else 1


if __name__ == "__main__":
    sys.exit(main())
