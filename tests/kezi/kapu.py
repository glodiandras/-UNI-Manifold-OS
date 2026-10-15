"""A kézi (klónos) próbák egy paranccsal (C33, T069, A2-tesztek-12): `bin/mos kapu [nev…] [--lista] [--idokorlat MP]`.

A `tests/kezi` legerősebb, a valódi vault klónján mért próbái eddig semmilyen kapuhoz nem voltak kötve: hogy lefutottak-e,
az csak a NAPLO prózájában élt. Ez a futtató sorban indítja őket (mindegyik a közös elkülönítő segéddel, `_kornyezet.py`,
dolgozik: a valódi vaulthoz és `vault.git`-hez csak olvasva nyúl, a klón a saját `{tmp}`-ben készül), és az eredményt
géppel olvashatóan a `{runs}/kapu-<idő>.json`-ba írja: a kód HEAD-je, a munkafa tisztasága, próbánként a kilépési kód,
az idő és a kimenet vége. Kilépési kód: 0, ha minden próba RENDBEN; 1, ha bármelyik bukott; 2, hibás hívás.

A doctor (`core/doctor.py`) ebből jelzi, ha a legutóbbi kapu régebbi a HEAD-nél (és a kapuk által védett kód azóta
változott), vagy ha bukott (a CLAUDE.md §5.4: a `vaultio`, `atnevezes`, `feloldas`, `server` modult módosító chat végén
kötelező).

Munkafa-módban (`MOS_MUNKAFA`) a próbák a fő checkout vaultját és `vault.git`-jét olvassák (`MOS_VAULT`,
`MOS_VAULT_GIT`, ha a hívó nem adta meg): a munkafának nincs saját vaultja.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))
from core import config  # noqa: E402
from core.doctor import KAPU_VEDETT  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _kornyezet import munkafa_forras  # noqa: E402

# A CLAUDE.md §5.4 klónos kapui (a `vaultio`, `atnevezes`, `feloldas`, `server` modult módosító chat végén kötelezők)
KAPUK = ("apfs_proba", "szerkeszto_mentes", "atnevezes_proba", "graf_paritas", "link_feloldas_paritas")
# A kódrészek, amelyeket a kapuk védenek: a doctor csak ezek változásakor jelzi az elavult kaput. Egyetlen forrás: a doctor
# listája (importmentes modul), hogy a futtató és a jelző ne csússzon szét.
VEDETT = KAPU_VEDETT
FAROK_SOR = 25
ALAP_IDOKORLAT = 900
# a próbák mappája (a futtató saját tesztje egy álmappát ad meg: `MOS_KAPU_MAPPA`)
MAPPA = Path(os.environ.get("MOS_KAPU_MAPPA") or REPO / "tests" / "kezi")


def _git(*args: str) -> str | None:
    """A 2.0 kódtárának (nem a vaultnak és nem a legacynek) egy csak olvasó git-hívása."""
    try:
        p = subprocess.run(["git", *args], cwd=REPO, capture_output=True, text=True, timeout=30,
                           env={**os.environ, "GIT_OPTIONAL_LOCKS": "0"})
    except (OSError, subprocess.TimeoutExpired):
        return None
    return p.stdout.strip() if p.returncode == 0 else None


def fo_checkout() -> Path | None:
    """Munkafa-módban a fő checkout (a `git rev-parse --git-common-dir` szülője), különben None."""
    if not (REPO / ".git").is_file():
        return None
    k = _git("rev-parse", "--path-format=absolute", "--git-common-dir")
    return Path(k).parent if k else None


def futtat(nev: str, env: dict[str, str], idokorlat: float) -> dict:
    szkript = MAPPA / f"{nev}.py"
    t0 = time.monotonic()
    try:
        p = subprocess.run([sys.executable, "-B", str(szkript)], cwd=REPO, env=env, capture_output=True, text=True,
                           timeout=idokorlat)
        kod, ki = p.returncode, (p.stdout or "") + ("\n" + p.stderr if p.stderr else "")
    except subprocess.TimeoutExpired as e:
        kod = 124
        ki = (e.stdout or "") if isinstance(e.stdout, str) else (e.stdout or b"").decode(errors="replace")
        ki += f"\n[kapu] időtúllépés: {idokorlat:.0f} s"
    sorok = [s for s in ki.splitlines() if s.strip()]
    rendben = kod == 0
    return {"nev": nev, "kod": kod, "rendben": rendben, "ido_mp": round(time.monotonic() - t0, 1),
            "zaro_sor": next((s for s in reversed(sorok) if "RENDBEN" in s or "HIBA" in s or "ELTÉR" in s or "BUKOTT" in s),
                             sorok[-1] if sorok else ""),
            "farok": sorok[-FAROK_SOR:]}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="mos kapu", description="A klónos kézi próbák sorban, összesítéssel (C33, T069).")
    ap.add_argument("nevek", nargs="*", help=f"a futtatandó próbák (alap: {', '.join(KAPUK)})")
    ap.add_argument("--lista", action="store_true", help="a próbák listája, futtatás nélkül")
    ap.add_argument("--idokorlat", type=float, default=ALAP_IDOKORLAT, help="próbánkénti időkorlát (mp)")
    a = ap.parse_args(argv)
    if a.lista:
        print("\n".join(KAPUK))
        return 0
    nevek = list(a.nevek) or list(KAPUK)
    ismeretlen = [n for n in nevek if not (MAPPA / f"{n}.py").is_file()]
    if ismeretlen:
        print(f"ismeretlen próba: {', '.join(ismeretlen)} (a lista: --lista)", file=sys.stderr)
        return 2
    cfg = config.load()
    env = munkafa_forras(dict(os.environ))
    head = _git("rev-parse", "HEAD")
    tiszta = _git("status", "--porcelain", "--untracked-files=no")
    ki = {"verzio": 1, "ido": time.strftime("%Y-%m-%dT%H:%M:%S"), "head": head, "munkafa_tiszta": tiszta == "",
          "munkafa": bool(fo_checkout()), "vedett": list(VEDETT), "eredmenyek": []}
    t0 = time.monotonic()
    for n in nevek:
        print(f"[kapu] {n} …", flush=True)
        e = futtat(n, env, a.idokorlat)
        ki["eredmenyek"].append(e)
        print(f"[kapu] {n}: {'RENDBEN' if e['rendben'] else 'BUKOTT'} ({e['ido_mp']} s) — {e['zaro_sor']}", flush=True)
        if not e["rendben"]:
            print("\n".join("    " + s for s in e["farok"][-10:]), flush=True)
    ki["rendben"] = all(e["rendben"] for e in ki["eredmenyek"])
    ki["teljes"] = set(nevek) >= set(KAPUK)
    ki["ido_mp"] = round(time.monotonic() - t0, 1)
    runs = cfg.path("runs")
    runs.mkdir(parents=True, exist_ok=True)
    cel = runs / time.strftime("kapu-%Y%m%d-%H%M%S.json")
    tmp = cel.with_name("." + cel.name + ".tmp")
    tmp.write_text(json.dumps(ki, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, cel)
    db = sum(e["rendben"] for e in ki["eredmenyek"])
    print(f"[kapu] {'RENDBEN' if ki['rendben'] else 'BUKOTT'}: {db}/{len(nevek)} próba, {ki['ido_mp']} s — {cel}")
    return 0 if ki["rendben"] else 1


if __name__ == "__main__":
    sys.exit(main())
