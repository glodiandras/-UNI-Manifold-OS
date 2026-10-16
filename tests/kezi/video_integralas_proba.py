"""C20b kész-feltétele: a videó bevitele a vaultba a legacyvel azonos vault-változást ad — a VALÓDI adaton csak olvasva (A), és egy
vault-APFS-klónon írva, visszavonással (B). Modell nélkül fut (a lexikai besorolás és a verifikátor determinisztikus; ahol a legacy
témáját a helyi modell vagy a gazda döntötte, a próba a legacy döntését adja meg, mint a legacy `--topic`); a discover nem futtatja.

    MOS_VAULT="<vault>" MOS_VAULT_GIT="<fő checkout>/var/vault.git" \\
    MOS_VIDEO_JOBS="<a médiajobok mappája>" MOS_STAGING="<a staging-klón>" \\
    bin/mos exec var/venv/bin/python -B tests/kezi/video_integralas_proba.py [--csak-olvas] [--n 8] [--megtart] [--limit N]

A. **A valódi adaton, csak olvasva** — a legacy `kesz` jobjaira (`state.json`):
   1. a lexikai besorolás (`egyezes.classify`) automatikus döntése és top1-e egyezik a legacy `besorolas`-ával;
   2. a vault-oldali átalakítók bájtra a vaultban álló mellékletet adják: `.info.json`, `.vtt`, a forrásleíró jegyzet;
   3. a verifikátor (`kotes.kotes`, a videó meglévő horgonyai kitakarva) a legacy gépi (`gep`) kötéseit adja vissza.
B. **Írás a vault-klónon** — `--n` job kimenetei (videó, mellékletek, a `#t=` horgonyok) a klónból kikerülnek (kézi commit), a lánc
   (`integralas.Integralas`, élesben, a klón saját gépi-írás szolgáltatásával) újra beviszi őket; ellenőrzés: a videó bájtra azonos, a
   mellékletek és a forrásleíró jegyzet bájtra a valódi vaultéval, a legacy beírt horgonyai mind visszakerültek, a jegyzetek törzse és
   többi mezője változatlan; utána minden tétel visszavonása (revert + a bináris napló: a klón az archívumba, nem törlődik) a klónt a
   bevitel előtti állapotra hozza, a staging-példány érintetlen. A próbamappa a végén törlődik (saját `var/tmp`), hacsak nincs `--megtart`.
"""
import argparse
import hashlib
import json
import os
import re
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
from core import config, frame, gepi_iras, snapshot, vaultio  # noqa: E402
from core.tulajdonsagok import Tulajdonsagok  # noqa: E402
from _kornyezet import cfg_elkulonitve, probamappa  # noqa: E402
from modulok.ytdlp import egyezes as X, integralas as I, konvertalas, kotes as KT, staging, vaultoldal as VO  # noqa: E402
from modulok.ytdlp.szovegreteg import cuek, nfc  # noqa: E402
from tests.grafikon_segedek import SzolgaltatasKliens  # noqa: E402

VIDEOK = "ATTCHMNTS - Videos"
eredmenyek: list[tuple[bool, str]] = []


def ellenoriz(nev: str, ok: bool, reszlet: str = "") -> bool:
    eredmenyek.append((bool(ok), nev))
    print(f"[{'RENDBEN' if ok else 'HIBA   '}] {nev}" + (f" — {reszlet}" if reszlet else ""), flush=True)
    return bool(ok)


def sha(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def kesz_jobok(jobs: Path, stag: Path) -> list[tuple[str, dict, Path]]:
    ki = []
    for st in sorted(jobs.glob("*/state.json")):
        s = json.loads(st.read_text(encoding="utf-8"))
        if s.get("allapot") != "kesz" or not s.get("staging"):
            continue
        m = staging.keres_azonosito(s["video_id"], stag)
        if m:
            ki.append((st.parent.name, s, Path(m)))
    return ki


def jeloltek(jobs: Path, kulcs: str) -> list[dict]:
    p = jobs / kulcs / "jeloltek.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.is_file() else []


def video_ut(vault: Path, el: dict, nev: str) -> Path:
    p = vault / (el.get("video_cel") or el["cel"]) / nev
    return p if p.is_file() else vault / VIDEOK / nev


def a_resz(cfg, jobs: Path, stag: Path, vault: Path, limit: int | None) -> None:
    print(f"\n== A. a valódi adat, csak olvasva ==\n   jobs: {jobs}\n   staging: {stag}\n   vault: {vault}", flush=True)
    ff = str(cfg.path("ffmpeg"))
    t0 = time.monotonic()
    idx = X.NoteIndex(vault)
    korp = KT.Korpusz(idx)
    elvet = KT.elvetettek(jobs.parent / "kotes" / "elvetett.jsonl")
    cimkek = dict(cfg.section("pdf").get("tags") or {})
    lista = kesz_jobok(jobs, stag)[: limit or None]
    db = {"besorolas": 0, "info": 0, "vtt": 0, "jegyzet": 0, "gep_leg": 0, "gep_kozos": 0, "uj_tobblet": 0}
    elter: dict[str, list] = {k: [] for k in (*db, "kerekites")}
    for kulcs, s, m in lista:
        src = staging.olvas(m)
        el = s["lepesek"]["elhelyezes"]
        cel = vault / el["cel"]
        torzs = s["torzs"]
        nev = next(f for f in el["fajlok"] if f.lower().endswith(".mp4"))
        vp = video_ut(vault, el, nev)
        felm = konvertalas.felmeres(ff, vp)
        vtt_nev = next(f for f in el["fajlok"] if f.endswith(".vtt"))
        vtt = VO.vtt_stagingbol(src, vtt_nev.rsplit(".", 2)[-2], s["lepesek"]["letoltes"].get("hossz_s"))
        f = X.Forras(nev, cuek(vtt), felm.hossz_s or -1.0)
        cls = X.classify(f, idx, "hu", csak_targy=I.targy_betu(src))
        lb = s.get("besorolas") or {}
        if bool(cls["auto"]) == bool(lb.get("auto")) and (cls["top3"] or [{}])[0].get("tema") == (lb.get("top3") or [{}])[0].get("tema"):
            db["besorolas"] += 1
        else:
            elter["besorolas"].append(kulcs)
        for kind, uj, ut in (("info", VO.info_json_szoveg(src), cel / f"{torzs}.info.json"), ("vtt", vtt, cel / vtt_nev)):
            if ut.is_file() and ut.read_text(encoding="utf-8") == uj:
                db[kind] += 1
            else:
                elter[kind].append(kulcs)
        jegyzet = VO.forrasjegyzet(nev, cimke=cimkek.get(X.targy(s["tema"]["tema"]) or ""), info=json.loads(VO.info_json_szoveg(src)),
                                   hossz=felm.hossz_s, meret=vp.stat().st_size, feliratok=[VO.felirat_sor(vtt_nev, vtt)],
                                   info_nev=f"{torzs}.info.json", fedettseg_=VO.fedettseg(vtt, felm.hossz_s))
        regi = (cel / f"{torzs}.md").read_text(encoding="utf-8")
        if regi == jegyzet:
            db["jegyzet"] += 1
        elif kerekites(regi, jegyzet):
            db["jegyzet"] += 1
            elter["kerekites"].append(kulcs)
        else:
            elter["jegyzet"].append(kulcs)
        mn = nfc(nev)
        mentett = {rp: n["media"] for rp, n in idx.notes.items()}
        for n in idx.notes.values():
            n["media"] = [(a, b) for a, b in n["media"] if a != mn]
        try:
            res = KT.kotes(f, korp, s["tema"]["tema"], elvet=elvet)
        finally:
            for rp, mm in mentett.items():
                idx.notes[rp]["media"] = mm
        leg = {(x["jegyzet"], x.get("vegso_t")) for x in jeloltek(jobs, kulcs) if x.get("sav") == "gep" and x.get("beirva") == "irva"}
        uj = {(x["jegyzet"], x["vegso_t"]) for x in res["auto"]}
        db["gep_leg"] += len(leg)
        db["gep_kozos"] += len(leg & uj)
        db["uj_tobblet"] += len(uj - leg)
        if leg - uj:
            elter["gep_kozos"].append((kulcs, sorted(leg - uj)))
    n = len(lista)
    print(f"   {n} kész job, {time.monotonic() - t0:.0f} s", flush=True)
    ellenoriz("A1 a lexikai besorolás (auto + top1) egyezik a legacyével", db["besorolas"] == n, f"{db['besorolas']}/{n}; eltér: {elter['besorolas'][:5]}")
    ellenoriz("A2 az .info.json bájtra azonos", db["info"] == n, f"{db['info']}/{n}; eltér: {elter['info'][:5]}")
    ellenoriz("A2 a .vtt bájtra azonos", db["vtt"] == n, f"{db['vtt']}/{n}; eltér: {elter['vtt'][:5]}")
    ellenoriz("A2 a forrásleíró jegyzet bájtra azonos (a hangfedettség 3. tizedese ±0,001-en belül)", db["jegyzet"] == n,
              f"{db['jegyzet']}/{n}, ebből {len(elter['kerekites'])} csak a hangfedettség kerekítésében tér el (a legacy ffprobe "
              f"ezredmásodperces hosszt mért, a 2.0 az `ffmpeg -i` századmásodperces hosszát): {elter['kerekites'][:3]}; "
              f"eltér: {elter['jegyzet'][:5]}")
    ellenoriz("A3 a legacy gépi kötései mind visszajönnek (a verifikátor)", db["gep_kozos"] == db["gep_leg"],
              f"{db['gep_kozos']}/{db['gep_leg']}; többlet {db['uj_tobblet']} (a 2026-09-23 óta kalibrált N tárgy és a legacy futás "
              f"óta bővült korpusz); hiányzik: {elter['gep_kozos'][:3]}")


_FEDETTSEG = re.compile(r"hangfedettség: \*\*([0-9.]+)\*\*")


def kerekites(a: str, b: str) -> bool:
    """A két jegyzet csak a hangfedettség értékében tér el, és az eltérés legfeljebb 0,001 (a hossz mérésének pontossága)."""
    ma, mb = _FEDETTSEG.search(a), _FEDETTSEG.search(b)
    if not (ma and mb) or _FEDETTSEG.sub("X", a) != _FEDETTSEG.sub("X", b):
        return False
    return abs(float(ma.group(1)) - float(mb.group(1))) <= 0.0010001


def manifeszt(gyoker: Path, kizar: list[str]) -> dict[str, str]:
    out = {}
    for d, almappak, fajlok in os.walk(gyoker):
        if ".git" in almappak:
            almappak.remove(".git")
        for f in fajlok:
            p = Path(d) / f
            rel = nfc(str(p.relative_to(gyoker)))
            if any(fnmatch(f, k) or fnmatch(rel, k) for k in kizar) or not p.is_file():
                out[rel] = f"meta:{p.lstat().st_size}"
            else:
                out[rel] = "sha256:" + hashlib.sha256(p.read_bytes()).hexdigest()
    return out


_HORGONY_SOR = '  - "[[{}#t='


def b_resz(cfg, jobs: Path, stag: Path, vault: Path, n: int, megtart: bool) -> None:
    print("\n== B. a bevitel a vault-klónon és a visszavonás ==", flush=True)
    lista = kesz_jobok(jobs, stag)
    auto = [x for x in lista if (x[1].get("besorolas") or {}).get("auto")]
    tobbi = [x for x in lista if not (x[1].get("besorolas") or {}).get("auto")]
    valasztott = (auto[: (n + 1) // 2] + tobbi[: n // 2])[:n]
    d = probamappa(cfg, "c20b-video", megtart=megtart, szkript="video_integralas_proba.py")
    print(f"   próbamappa: {d}; {len(valasztott)} job ({sum(1 for x in valasztott if x in auto)} lexikai auto)", flush=True)
    vault_k, git_k = frame.trial_clone(cfg, d)
    kcfg = cfg_elkulonitve(d, cfg, vault=vault_k, vault_git=git_k, home=True)
    for nev in ("kotes/elvetett.jsonl", "itelet/n_kotes_minta.json", "itelet/n_cimkek.json", "itelet/n_kotes_minta_2.json",
                "itelet/n_cimkek_2.json"):             # a legacy olvasott elvetései és címkéi (csak másolat a próbába)
        f = jobs.parent / nev
        if f.is_file():
            (kcfg.path("video_jobs").parent / nev).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(f, kcfg.path("video_jobs").parent / nev)
    repo = snapshot.repos(kcfg)["vault"]
    kizar = repo.exclude
    # 1. a legacy kimenetek eltávolítása a klónból (a staging-példány APFS-klónja a próba stagingjébe)
    vartak = {}
    for kulcs, s, m in valasztott:
        el = s["lepesek"]["elhelyezes"]
        nev = next(f for f in el["fajlok"] if f.lower().endswith(".mp4"))
        cel = el["cel"]
        vp = video_ut(vault, el, nev)
        legacy_irt = {(x["jegyzet"], x.get("vegso_t")) for x in jeloltek(jobs, kulcs) if x.get("beirva") == "irva"}
        vartak[kulcs] = {"nev": nev, "cel": cel, "video": str(vp.relative_to(vault)), "torzs": s["torzs"], "irt": legacy_irt,
                         "mellekletek": sorted([f"{cel}/{f}" for f in el["fajlok"] if not f.lower().endswith(".mp4")] + [f"{cel}/{s['torzs']}.md"])}
        (vault_k / vartak[kulcs]["video"]).unlink()
        for rel in vartak[kulcs]["mellekletek"]:
            (vault_k / rel).unlink()
        for rp, _ in legacy_irt:
            p = vault_k / rp
            t = p.read_text(encoding="utf-8")
            t2 = "".join(sor for sor in t.splitlines(keepends=True) if not sor.startswith(_HORGONY_SOR.format(nev)))
            if t2 != t:
                p.write_text(t2, encoding="utf-8")
        rel = m.relative_to(stag)
        (kcfg.path("staging") / rel).parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(["cp", "-c", "-R", str(m), str(kcfg.path("staging") / rel)], check=True)
    repo.commit("C20b próba: a legacy kimenetek eltávolítva", {"Mos-Forras": "kezi"})
    elotte = manifeszt(vault_k, kizar)
    staging_elotte = {k: sha(kcfg.path("staging") / m.relative_to(stag) / "video.mp4") for k, _, m in valasztott}
    # 2. a bevitel: élesben a klónon (a klón saját gépi-írás szolgáltatása), modell nélkül
    V = vaultio.Vault(kcfg)
    G = gepi_iras.GepiIras(kcfg, V, Tulajdonsagok(kcfg, None), varakozas_mp=5)

    class NincsModell:
        def van(self, feladat):
            return False
    felulir = {k: s["tema"]["tema"] for k, s, _ in valasztott if not (s.get("besorolas") or {}).get("auto")}
    lanc = I.Integralas(kcfg, modellek=NincsModell(), gepi=SzolgaltatasKliens(G, V), temak=felulir,
                        log=lambda s: print("        " + s) if s.startswith("[videó]") else None)
    r = lanc.futtat([kcfg.path("staging") / m.relative_to(stag) for _, _, m in valasztott])
    ellenoriz("B1 minden tétel bekerült", r["eredmeny"] == {"integralva": len(valasztott)}, str(r["eredmeny"]))
    tetelek = {t["kulcs"]: t for t in r["tetelek"]}
    for kulcs, s, m in valasztott:
        v, t = vartak[kulcs], tetelek.get(kulcs) or {}
        ok_v = (vault_k / VIDEOK / v["nev"]).is_file() and sha(vault_k / VIDEOK / v["nev"]) == sha(vault / v["video"])
        ok_m = all((vault_k / rel).is_file() and (vault_k / rel).read_bytes() == (vault / rel).read_bytes() for rel in v["mellekletek"])
        ok_t = (t.get("tema") or {}).get("tema") == s["tema"]["tema"]
        uj = set()
        for rp in {x[0] for x in v["irt"]} | {k["jegyzet"] for k in t.get("kotesek") or [] if k.get("dontes") == "elfogad"}:
            txt = (vault_k / rp).read_text(encoding="utf-8")
            uj |= {(rp, int(x)) for x in re.findall(re.escape(f"[[{v['nev']}#t=") + r"(\d+)\]\]", txt)}
        tobblet = uj - v["irt"]
        ok_h = v["irt"] <= uj
        ellenoriz(f"B2 {v['torzs'][:40]}: videó, mellékletek bájtra, téma, a legacy horgonyai",
                  ok_v and ok_m and ok_t and ok_h,
                  f"videó {ok_v}, mellékletek {ok_m}, téma {ok_t} ({(t.get('tema') or {}).get('forras')}), horgony "
                  f"{len(v['irt'] & uj)}/{len(v['irt'])}" + (f", többlet {len(tobblet)}" if tobblet else ""))
    # a horgonyos jegyzetek a Source-on kívül változatlanok (a valódi vault + a legacy horgonyok halmazként)
    rossz = []
    for kulcs, _, _ in valasztott:
        for rp, _ in vartak[kulcs]["irt"]:
            a, b = (vault / rp).read_text(encoding="utf-8"), (vault_k / rp).read_text(encoding="utf-8")
            if a.split("\n---", 1)[-1] != b.split("\n---", 1)[-1]:
                rossz.append(rp)
    ellenoriz("B3 a horgonyos jegyzetek törzse változatlan", not rossz, str(rossz[:3]))
    ellenoriz("B3 a staging-példányok érintetlenek (klón)", all(sha(kcfg.path("staging") / m.relative_to(stag) / "video.mp4") == staging_elotte[k]
                                                               for k, _, m in valasztott))
    # 4. a visszavonás (a vezérlő „Visszavonás”-ának magja: App.undo → revert + a bináris napló)
    shak = [t["commit"] for t in r["tetelek"] if t.get("commit")]
    for s_ in reversed(shak):
        repo.undo_commit(s_, snapshot.exclusions(kcfg, "vault"))
        bn.visszavonas_utan(kcfg, repo, s_, None, log=lambda s: None)
    utana = manifeszt(vault_k, kizar)
    kul = sorted(k for k in set(elotte) | set(utana) if elotte.get(k) != utana.get(k))
    ellenoriz("B4 minden tétel visszavonása után a klón a bevitel előtti (bájtra)", not kul, str(kul[:5]))
    arch = sorted(kcfg.path("video_visszavont").rglob("*.mp4"))
    ellenoriz("B4 a videó-klónok az archívumba kerültek (nem törlődtek)", len(arch) == len(valasztott), f"{len(arch)} videó")
    ellenoriz("B4 a staging-példányok érintetlenek", all(sha(kcfg.path("staging") / m.relative_to(stag) / "video.mp4") == staging_elotte[k]
                                                         for k, _, m in valasztott))
    if not megtart:
        shutil.rmtree(d)
        print(f"   a próbamappa törölve: {d}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--csak-olvas", action="store_true")
    ap.add_argument("--n", type=int, default=8)
    ap.add_argument("--limit", type=int)
    ap.add_argument("--megtart", action="store_true")
    a = ap.parse_args()
    cfg = config.load()
    jobs, stag, vault = cfg.path("video_jobs"), cfg.path("staging"), cfg.path("vault")
    a_resz(cfg, jobs, stag, vault, a.limit)
    if not a.csak_olvas:
        b_resz(cfg, jobs, stag, vault, a.n, a.megtart)
    jo = sum(1 for ok, _ in eredmenyek if ok)
    print(f"\n{'RENDBEN' if jo == len(eredmenyek) else 'HIBA'}: {jo}/{len(eredmenyek)}")
    return 0 if jo == len(eredmenyek) else 1


if __name__ == "__main__":
    sys.exit(main())
