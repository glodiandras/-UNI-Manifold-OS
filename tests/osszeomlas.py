"""Összeomlás-injektáló tesztállvány (C29.6, 2. audit T193): egy vault-író művelet **megölése a lépéshatáron**, majd
`App.indulas()` és a helyreállítás invariánsai.

Az állvány nem teszt (a `test_osszeomlas.py` használja). Működése:
  1. `Allvany`: álgyökér + álvault + pillanatkép-tároló (a `tests/helpers.alg_core`-ral, a valódi vaulthoz és `var/`-hoz
     nem ér); a vault tartalma az `ALAP`.
  2. `futtat(muvelet, pont)`: alfolyamatban (`python -m tests.osszeomlas <művelet>`) `MOS_OSSZEOMLAS=<pont>` mellett lefut a
     művelet (gépi tétel, átnevezés, mappa-átnevezés, mentés, …); a `core/osszeomlas.py` horga a megnevezett
     lépéshatáron `os._exit(137)`-tel öli a folyamatot — `finally`, `atexit` és szálleállítás nélkül, mint a SIGKILL
     vagy az áramszünet. 137 helyett 0 azt jelenti, hogy a pont nem teljesült (a teszt hibája).
  3. `indulas()`: a szülő folyamatban egy `server.App(cfg).indulas()` — ugyanaz a kód, amely az éles indulásnál fut.
  4. `invariansok(vart)`: a vault az „előtte” vagy a „teljesen utána” bájtokon áll (soha nem a kettő keveréke), nincs
     szándéknapló és ideiglenes fájl, a pillanatkép-tároló tiszta és ép (`git fsck`).

A „teljesen utána” állapotot egy horog nélküli referencia-futás adja (azonos műveletsor egy másik álvaulton).
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import unicodedata
from pathlib import Path

from tests.helpers import REPO, alg_core, env, ir

FM = "---\nTags:\nSource:\nStatus:\nNN:\nCanvas:\n---\n"
KOR = "KARTYA-20261004-101500"
ALAP = {
    "T01/a.md": FM + "# A\n\n## Gyakorlás\nelső sor\n",
    "Cél.md": "# Cél\nSzöveg\n",
    "Hivo1.md": "Lásd [[Cél]] és [[Mappa/Egy]].\n",
    "Hivo2.md": "[[Cél|alias]] és [[Egy]]\n",
    "Mappa/Egy.md": "# Egy\n[[Ketto]] és [[Cél]]\n",
    "Mappa/Ketto.md": "# Ketto\n[[Egy]]\n",
    "X/Szoveg.md": "semmi link\n",
}

# művelet → a horgok, amelyeken az alfolyamat megölhető (a `core/osszeomlas.pont` nevei)
PONTOK = {
    "gepi": ("gepi.naplo_kesz", "gepi.egy_fajl_irva", "gepi.commit_elott", "gepi.commit_utan"),
    "atnevezes": ("atnevezes.naplo_kesz", "atnevezes.fajl_irva", "atnevezes.atnevezve", "atnevezes.commit_elott",
                  "atnevezes.commit_utan"),
    "mappa": ("atnevezes.naplo_kesz", "atnevezes.fajl_irva", "atnevezes.atnevezve", "atnevezes.commit_elott",
              "atnevezes.commit_utan"),
    "atomi": ("atomi.csere_elott", "atomi.csere_utan"),
    "mentes": ("mentes.bundle_tmp", "mentes.allapot_fele"),
    "visszavonas": ("visszavonas.apply_utan", "visszavonas.commit_utan"),
    "visszaallit": ("visszavonas.apply_utan", "visszavonas.commit_utan"),       # ugyanaz a közös törzs (`_visszafordit`)
}
V2_SOR = b"masodik valtozat\n"
GEPI_SOR = b"gepi sor\n"
UTANA_PONTOK = {"gepi.commit_utan", "atnevezes.commit_utan"}      # a commit megvolt: a „teljesen utána” állapot marad


def lenyomat(gyoker) -> dict:
    """A vault minden fájlja bájtra (és az üres mappák), az `.obsidian` nélkül."""
    ki = {}
    for d, mappak, fajlok in os.walk(gyoker):
        mappak[:] = [m for m in mappak if m != ".obsidian"]
        for f in fajlok:
            p = os.path.join(d, f)
            ki[unicodedata.normalize("NFC", os.path.relpath(p, gyoker))] = Path(p).read_bytes()
        if not mappak and not fajlok:
            ki[unicodedata.normalize("NFC", os.path.relpath(d, gyoker)) + "/"] = b""
    return ki


class Allvany:
    """Egy álgyökér az ALAP vaulttal és a saját pillanatkép-tárolójával."""

    def __init__(self, tmp: str, fajlok: dict | None = None):
        from core import snapshot
        self.cfg, self.root, self.v = alg_core(tmp)
        for rp, t in (ALAP if fajlok is None else fajlok).items():
            ir(self.v, rp, t, "wb" if isinstance(t, bytes) else "w")
        self.repo = snapshot.repos(self.cfg)["vault"]
        self.repo.init()
        self.repo.commit("alap", {"Mos-Forras": "kezi"})
        self.elotte = lenyomat(self.v)

    # ------------------------------------------------------------ az alfolyamat

    def futtat(self, muvelet: str, pont: str | None = None, **param) -> subprocess.CompletedProcess:
        """A művelet alfolyamatban; `pont`: ott hal meg (137). Nélküle végigfut (0)."""
        e = env(MOS_ROOT=str(self.root), PYTHONPATH=str(REPO), **({"MOS_OSSZEOMLAS": pont} if pont else {}))
        return subprocess.run([sys.executable, "-B", "-m", "tests.osszeomlas", muvelet, json.dumps(param)], cwd=REPO,
                              env=e, capture_output=True, timeout=180)

    # ------------------------------------------------------------ az indulás

    def indulas(self) -> list[str]:
        """A következő indulás: `App.indulas()` a megmaradt állapoton → az indulási üzenetek."""
        from core import server
        app = server.App(self.cfg, start_delay=0)
        try:
            app.indulas()
            return list(app.indulasi_uzenetek)
        finally:
            app.queue.close(timeout=0)
            app.index.leallit()

    # ------------------------------------------------------------ az invariánsok

    def tmp_maradek(self) -> list[str]:
        return sorted(os.path.relpath(p, self.v) for p in self.v.rglob("*.manifold-tmp"))

    def naplok(self) -> list[str]:
        run = self.cfg.path("run")
        return sorted(p.name for p in run.iterdir() if p.is_dir()) if run.is_dir() else []

    def invariansok(self, teszt, vart: dict, *, tmp_lehet: bool = False, kor_commit: bool | None = None,
                    tiszta_tar: bool = True) -> None:
        """A közös invariánsok; `vart`: az egyetlen megengedett vault-lenyomat (előtte VAGY utána)."""
        mostani = lenyomat(self.v)
        teszt.assertEqual(sorted(mostani), sorted(vart), "a fájlok halmaza nem az elvárt")
        for rp in vart:
            teszt.assertEqual(mostani[rp], vart[rp], f"a(z) {rp} tartalma nem az elvárt (az előtte/utána keveréke?)")
        if not tmp_lehet:
            teszt.assertEqual(self.tmp_maradek(), [], "ideiglenes fájl maradt")
        teszt.assertEqual([n for n in self.naplok() if n in ("atnevezes", "gepi-iras", "visszavonas")], [],
                          "szándéknapló maradt")
        if tiszta_tar:
            # a `diff-files` ELŐBB: a `git status` mellékhatásként maga is frissíti az index stat-adatait, és elfedné a hibát
            teszt.assertEqual(self.repo.git("diff-files", "--name-only", check=False).stdout.strip(), "",
                              "a git-index stat-adatai elavultak (a helyreállítás nem frissítette az indexet)")
            teszt.assertEqual(self.repo.dirty_paths(), [], "a pillanatkép-tároló nem tiszta")
        fsck = self.repo.git("fsck", "--no-progress", check=False)
        teszt.assertEqual(fsck.returncode, 0, fsck.stderr)
        if kor_commit is not None:
            teszt.assertEqual(bool(self.repo.log(30, run=KOR)), kor_commit, "a gépi commit megléte nem az elvárt")


# ============================================================ az alfolyamat műveletei

def _cfg():
    from core import config
    return config.load(dict(os.environ))


def _gepi(param: dict) -> None:
    from core import gepi_iras, vaultio
    from core.tulajdonsagok import Tulajdonsagok
    cfg = _cfg()
    v = vaultio.Vault(cfg)
    g = gepi_iras.GepiIras(cfg, v, Tulajdonsagok(cfg, None), varakozas_mp=1.0)
    alap = vaultio.sha1((cfg.path("vault") / "T01/a.md").read_bytes())
    g.ir({"kor": KOR, "tetel": "t1", "forras": "mos-kartya", "uzenet": "kártyák", "modell": None, "muveletek": [
        {"tipus": "csere", "ut": "T01/a.md", "alap": alap, "tartalom": ALAP["T01/a.md"] + "gépi sor\n"},
        {"tipus": "uj", "ut": "_Proba/Mappa/B.md", "osztaly": "normal", "tartalom": FM + "# B\n"},
    ]})


def _atnevezes_kozos(regi: str, uj: str) -> None:
    from core import vaultio
    from core.atnevezes import Atnevezes
    from tests.index_segedek import index_indit
    cfg = _cfg()
    ix, _ = index_indit(cfg)
    a = Atnevezes(cfg, vaultio.Vault(cfg), ix)
    t = a.terv(regi, uj)
    assert t["ok"], t["blokkolok"]
    a.vegrehajt(regi, uj, t["terv_hash"])


def _atnevezes(param: dict) -> None:
    _atnevezes_kozos("Cél.md", "Új név.md")


def _mappa(param: dict) -> None:
    _atnevezes_kozos("Mappa", "Mappa2")


def _atomi(param: dict) -> None:
    """Egy tartós, atomi csere (a mentés magja): a `core/tartos.py` horgain hal meg."""
    from core import tartos
    tartos.atomi_ir(_cfg().path("vault") / "T01/a.md", b"uj tartalom\n")


def _mentes(param: dict) -> None:
    """A belső lemezes mentés: egy kis SQLite és JSON az állapotban, majd `ment` (a `mentes.*` horgokon hal meg)."""
    import sqlite3
    from core import mentes
    cfg = _cfg()
    cfg.path("state").mkdir(parents=True, exist_ok=True)
    (cfg.path("state") / "felulet.json").write_text('{"tema": "sotet"}', encoding="utf-8")
    con = sqlite3.connect(cfg.path("router_db"))
    con.execute("CREATE TABLE t (x TEXT)")
    con.execute("INSERT INTO t VALUES ('sor')")
    con.commit()
    con.close()
    mentes.ment(cfg)


def _visszavonas(param: dict) -> None:
    """Egy gépi commit, majd a visszavonása (`Repo.undo_commit`): a `visszavonas.*` horgokon hal meg."""
    from core import snapshot
    cfg = _cfg()
    repo = snapshot.repos(cfg)["vault"]
    (cfg.path("vault") / "T01/a.md").write_bytes(ALAP["T01/a.md"].encode("utf-8") + GEPI_SOR)
    sha = repo.commit_machine("gép", {"Mos-Kor": "KARTYA-20261004-101500", "Mos-Tetel": "t"}, ["T01/a.md"])
    repo.undo_commit(sha)


def _visszaallit(param: dict) -> None:
    """Két gépi változat, majd az első visszaállítása (`Elozmeny.visszaallit`, revert-commit): ugyanazokon a horgokon hal meg."""
    from core import elozmeny, snapshot
    cfg = _cfg()
    repo = snapshot.repos(cfg)["vault"]
    p = cfg.path("vault") / "T01/a.md"
    p.write_bytes(ALAP["T01/a.md"].encode("utf-8") + GEPI_SOR)
    v1 = repo.commit_machine("v1", {"Mos-Kor": "KARTYA-20261004-101500", "Mos-Tetel": "t"}, ["T01/a.md"])
    p.write_bytes(ALAP["T01/a.md"].encode("utf-8") + GEPI_SOR + V2_SOR)
    repo.commit_machine("v2", {"Mos-Kor": "KARTYA-20261004-101501", "Mos-Tetel": "t"}, ["T01/a.md"])
    elozmeny.Elozmeny(cfg).visszaallit("T01/a.md", v1)


MUVELETEK = {"gepi": _gepi, "atnevezes": _atnevezes, "mappa": _mappa, "atomi": _atomi, "mentes": _mentes,
             "visszavonas": _visszavonas, "visszaallit": _visszaallit}


def gyerek(argv: list[str]) -> int:
    MUVELETEK[argv[0]](json.loads(argv[1]) if len(argv) > 1 else {})
    return 0


if __name__ == "__main__":
    sys.exit(gyerek(sys.argv[1:]))
