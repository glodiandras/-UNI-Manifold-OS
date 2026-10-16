"""A modellek rögzített revíziója (C19, T141; az 1. audit §6 ajánlása): a `config/models.toml` és a regiszter `revizio`
kulcsa a HF-repó egy commit-sha-ja. A letöltés ezzel a revízióval megy (`revision=`), a betöltő ezt a pillanatképet tölti
(`local_files_only`), a kalibrációs sor a mért pillanatkép sha-ját hordozza (`snapshot`), és a doctor jelzi, ha a helyi
gyorsítótár (`refs/main`, `snapshots/<sha>`) vagy egy kalibrált sor pillanatképe eltér a rögzítettől.

Csak olvas: a HF-gyorsítótár szerkezete `{models}/hub/models--<org>--<név>/{refs/main, snapshots/<sha>/}`. Hálózat nincs.
"""
from __future__ import annotations

import re
from pathlib import Path

SHA = re.compile(r"^[0-9a-f]{40}$")


def repo_mappa(models: Path, repo: str) -> Path:
    return Path(models) / "hub" / f"models--{repo.replace('/', '--')}"


def helyi_main(models: Path, repo: str) -> str | None:
    """A helyi gyorsítótár `refs/main`-je (a legutóbb letöltött főág-commit), vagy None."""
    try:
        s = (repo_mappa(models, repo) / "refs" / "main").read_text(encoding="utf-8").strip()
    except OSError:
        return None
    return s if SHA.match(s) else None


def van_pillanatkep(models: Path, repo: str, sha: str) -> bool:
    return bool(sha) and (repo_mappa(models, repo) / "snapshots" / sha).is_dir()


def mert_pillanatkep(models: Path, repo: str, revizio: str = "") -> str:
    """A mérés (és a betöltés) pillanatképe: a rögzített revízió, ha helyben megvan; különben a `refs/main`; különben ''."""
    if revizio and van_pillanatkep(models, repo, revizio):
        return revizio
    return helyi_main(models, repo) or ""


def ellenoriz(modellek: dict[str, dict], models: Path) -> list[dict]:
    """A manifeszt (`models.toml`) modelljei közül a helyben meglévők eltérései: `{modell, fajta, uzenet}`; fajta: `nincs_revizio` |
    `rossz_revizio` | `hianyzo_pillanatkep` | `main_elter`."""
    ki = []
    for nev, m in sorted(modellek.items()):
        repo, rev = m["repo"], str(m.get("revizio") or "")
        main = helyi_main(models, repo)
        if main is None and not repo_mappa(models, repo).is_dir():
            continue                                              # nincs letöltve: nincs mit összevetni
        if not rev:
            ki.append({"modell": nev, "fajta": "nincs_revizio",
                       "uzenet": f"{nev}: a models.toml-ban nincs `revizio` (helyben: {main or '?'})"})
        elif not SHA.match(rev):
            ki.append({"modell": nev, "fajta": "rossz_revizio", "uzenet": f"{nev}: a `revizio` nem 40 jegyű commit-sha: {rev}"})
        elif not van_pillanatkep(models, repo, rev):
            ki.append({"modell": nev, "fajta": "hianyzo_pillanatkep",
                       "uzenet": f"{nev}: a rögzített revízió ({rev[:12]}) pillanatképe nincs a gyorsítótárban"})
        elif main != rev:
            ki.append({"modell": nev, "fajta": "main_elter",
                       "uzenet": f"{nev}: a helyi refs/main ({(main or '?')[:12]}) eltér a rögzített revíziótól ({rev[:12]})"})
    return ki


def kalibracio_elteres(sorok: list[dict], revizio: dict[str, str]) -> list[str]:
    """A kalibrált sorok, amelyek pillanatképe nem a modell rögzített revíziója (`revizio`: modellnév → sha)."""
    ki = []
    for s in sorok:
        rev = revizio.get(s["modell"], "")
        snap = s.get("snapshot") or ""
        if s.get("kalibralt") and rev and snap != rev:
            ki.append(f"{s['feladat']} · {s['modell']}: a kalibráció pillanatképe ({snap[:12] or 'ismeretlen'}) nem a "
                      f"rögzített revízió ({rev[:12]}) — újramérés kell")
    return ki
