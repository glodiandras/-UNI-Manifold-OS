"""F3 integrációs kapu (F3-DESIGN §9): friss telepítés, végig, egy termék-alakú álgyökéren.

Termék-alakú, CSAK OLVASHATÓ gyökér (`X.app/Contents/Resources/manifold`, `var/` nélkül), ál-HOME szóközös
`Library/Application Support/Manifold` telepítéssel (K13), egy meglévő Obsidian-vault. A lépések sorrendben:

1. `workspace letrehoz` (CLI-alfolyamat): `.obsidian` + `.manifold` + élő pillanatkép-tároló + az első `kezi` commit, regiszter;
2. a core alfolyamat a munkatéren (`MOS_VAULT`, termék-elrendezés): kézfogás, a zárak és az állapot a vaultban;
3. egy jegyzet mentése az API-n át: pillanatkép (gépi commit) a vault tárolójában, a vault a `.manifold`-on kívül érintetlen;
4. belső lemezes mentés: `{backup_gyoker}/{workspace_id}` mappa tulajdonosjellel, ellenőrzött `git bundle`;
5. visszaállítás: az elveszett tároló (`{var}/vault.git`) és két fájl a bundle-ből, a core újraindul és ugyanazt a történetet látja.

Közben a kódfába semmi nem kerül (I1), a telepítés a `{install}`-ba ír, és a vault-állapot a `.manifold/var`-ban él."""
from __future__ import annotations

import http.client
import json
import os
import shutil
import stat
import subprocess
import sys
import tomllib
import unittest
import urllib.parse
from pathlib import Path

from core import mentes, server, visszaallitas
from tests.fresh_install import lenyomat, obsidian_vault, termek_cfg
from tests.helpers import REPO, alg_bundle, tmpdir
from tests.multi_user import elso_sor, termek_env

TITOK = "alap-titok-0123456789abcdef"
JEGYZET = "Első mentett jegyzet"


def _csak_olvashato(gyoker: Path) -> None:
    """`chmod -R a-w`: a termék kódfája csak olvasható (a telepített `.app`-é az)."""
    for d, mappak, fajlok in os.walk(gyoker):
        for n in (*fajlok, *mappak):
            p = Path(d) / n
            if not p.is_symlink():
                p.chmod(p.stat().st_mode & ~(stat.S_IWUSR | stat.S_IWGRP | stat.S_IWOTH))
    gyoker.chmod(gyoker.stat().st_mode & ~(stat.S_IWUSR | stat.S_IWGRP | stat.S_IWOTH))


def _irhato(gyoker: Path) -> None:
    """A teszt-mappa takarításához (a csak olvasható fa nem törölhető)."""
    for d, mappak, fajlok in os.walk(gyoker):
        for n in (*mappak, *fajlok):
            p = Path(d) / n
            if not p.is_symlink():
                p.chmod(p.stat().st_mode | stat.S_IWUSR)
        Path(d).chmod(Path(d).stat().st_mode | stat.S_IWUSR)
    gyoker.chmod(gyoker.stat().st_mode | stat.S_IWUSR)


class FrissTelepitesTest(unittest.TestCase):
    def setUp(self):
        self._t = tmpdir()
        self.addCleanup(self._t.cleanup)
        self.t = Path(self._t.name)
        self.root = alg_bundle(self._t.name)
        self.home = self.t / "home"
        self.install = self.home / "Library" / "Application Support" / "Manifold"      # szóköz az úton (K13)
        self.vault = obsidian_vault(self.t / "Jegyzeteim")
        self.vault_elotte = lenyomat(self.vault, kihagy=())
        _csak_olvashato(self.root)
        self.addCleanup(_irhato, self.root)              # a `_t.cleanup` előtt fut (fordított sorrend)
        self.kod_elotte = lenyomat(self.root, kihagy=())

    # ------------------------------------------------------------------ segédek

    def _env(self) -> dict:
        return termek_env(self.root, self.home, self.vault, MOS_API_TITOK=TITOK)

    def _cli(self, *args: str) -> dict:
        p = subprocess.run([sys.executable, "-B", "-m", "core.workspace", *args, "--json"], cwd=REPO, env=self._env(),
                           capture_output=True, text=True, timeout=120)
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        return json.loads(p.stdout)

    def _core(self) -> tuple[subprocess.Popen, dict]:
        p = subprocess.Popen([sys.executable, "-B", "-m", "core", "start"], cwd=REPO, stdin=subprocess.PIPE,
                             stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, env=self._env())
        self.addCleanup(self._leallit, p)
        sor = elso_sor(p)
        self.assertTrue(sor, "a core nem adott kézfogást")
        return p, json.loads(sor)

    @staticmethod
    def _leallit(p: subprocess.Popen) -> None:
        if p.poll() is None:
            p.stdin.close()
            try:
                p.wait(60)
            except subprocess.TimeoutExpired:
                p.kill()
                p.wait()
        for f in (p.stdin, p.stdout):
            if f and not f.closed:
                f.close()

    @staticmethod
    def _k(port: int, metodus: str, ut: str, torzs: dict | None = None) -> tuple[int, dict]:
        c = http.client.HTTPConnection("127.0.0.1", port, timeout=60)
        try:
            c.request(metodus, ut, body=json.dumps(torzs) if torzs is not None else None,
                      headers={"Host": f"127.0.0.1:{port}", "X-Manifold": TITOK, "Content-Type": "application/json"})
            r = c.getresponse()
            return r.status, json.loads(r.read() or b"null")
        finally:
            c.close()

    def _ment_jegyzet(self, port: int, ut: str, szoveg: str) -> dict:
        kod, d = self._k(port, "GET", "/api/vault/fajl?ut=" + urllib.parse.quote(ut))
        self.assertEqual(kod, 200, d)
        kod, d = self._k(port, "PUT", "/api/vault/fajl", {"ut": ut, "tartalom": szoveg, "alap": d["hash"], "elso": True, "pillanat": True})
        self.assertEqual((kod, d.get("git")), (200, True), d)
        return d

    def _vault_git(self, *args: str) -> str:
        git_dir = self.vault / ".manifold" / "var" / "vault.git"
        p = subprocess.run(["git", "--git-dir", str(git_dir), *args], capture_output=True, text=True, timeout=60)
        self.assertEqual(p.returncode, 0, p.stderr)
        return p.stdout

    # ------------------------------------------------------------------ a teljes út

    def test_telepitestol_a_visszaallitasig(self):
        self.assertFalse((self.root / "var").exists(), "friss telepítés: nincs var/")
        self.assertFalse(self.install.exists())

        # 1. munkatér létrehozása a meglévő Obsidian-vaulton
        r = self._cli("letrehoz", str(self.vault))
        id = r["id"]
        self.assertRegex(id, r"^[0-9a-f]{32}$")
        self.assertEqual((r["uj"], r["allapot"]), (True, "vault"))
        ws = self.vault / ".manifold"
        w = tomllib.loads((ws / "workspace.toml").read_text(encoding="utf-8"))["workspace"]
        self.assertEqual((w["id"], w["formatum"], w["obsidian_letrehozva"]), (id, 1, False))      # a vaultnak volt `.obsidian`-ja
        self.assertTrue((ws / "var" / "vault.git").is_dir(), "a pillanatkép-tároló a vaultban él")
        self.assertEqual(self._vault_git("log", "-1", "--format=%s").strip(), "munkatér létrehozva")
        self.assertIn("Mos-Forras: kezi", self._vault_git("log", "-1", "--format=%B"))
        reg = json.loads((self.install / "workspaces.json").read_text(encoding="utf-8"))
        self.assertEqual((reg["utolso"], reg["munkaterek"][id]["vault"]), (id, str(self.vault)))
        self.assertEqual(lenyomat(self.vault), self.vault_elotte, "a vault a `.manifold`-on kívül bájtra azonos")

        # 2. a core a munkatéren
        p, k = self._core()
        self.assertEqual((k["elrendezes"], k["munkater_id"], k["vault"]), ("termek", id, os.path.realpath(self.vault)))
        self.assertEqual(server.zar_foglalt(ws / "var" / "run" / "core.lock"), {"foglalt": True, "pid": p.pid, "vault": str(self.vault)})
        self.assertTrue((ws / "var" / "feladatok.sqlite").is_file())
        self.assertTrue(list((self.install / "run" / "vaults").glob("*.lock")), "a vault-őr a telepítés `run/`-jában")

        # 3. mentés az API-n át: pillanatkép a vault tárolójában
        mentett = self._ment_jegyzet(k["port"], "Jegyzetek/Első.md", "---\ntags: [a]\n---\nFelülírt első jegyzet.\n")
        self.assertTrue(mentett["pillanat"])
        kod, naplo = self._k(k["port"], "GET", "/api/pillanat/vault/naplo?n=10")
        self.assertEqual(kod, 200, naplo)
        targyak = [c["targy"] for c in naplo["commitok"]]
        self.assertTrue(any("Jegyzetek/Első.md" in t for t in targyak), targyak)
        self.assertEqual(naplo["commitok"][0]["sha"], mentett["pillanat"])
        ujak = self._k(k["port"], "POST", "/api/vault/uj", {"nev": JEGYZET})[1]
        self.assertEqual((ujak["ok"], ujak["git"]), (True, True), ujak)

        # a core leáll: a kilépési mentés a telepítés `backups/<id>/` mappájába ír (nem a vaultba, nem a kódfába)
        self._leallit(p)
        self.assertIsNotNone(p.returncode)
        self.assertTrue(list((self.install / "backups" / id).glob("mos-allapot-*")), "kilépési állapotmentés")
        fej = self._vault_git("rev-parse", "HEAD").strip()

        # 4. belső lemezes mentés: tulajdonosjeles, per-munkatér mappa; a bundle ellenőrizhető
        cfg = termek_cfg(self.root, self.home, self.vault)
        self.assertEqual(cfg.path("backup"), self.install / "backups" / id)
        ki = mentes.ment(cfg, csak_ha_valtozott=False)
        bundle = next(b for b in ki if b.name.startswith("vault-"))
        jel = json.loads((self.install / "backups" / id / mentes.JEL_NEV).read_text(encoding="utf-8"))
        self.assertEqual((jel["munkater_id"], jel["vault"]), (id, str(self.vault)))
        self.assertEqual(mentes.tulajdonos(cfg), "sajat")
        v = subprocess.run(["git", "bundle", "verify", str(bundle)], capture_output=True, text=True)
        self.assertEqual(v.returncode, 0, v.stderr)
        self.assertIn(fej, subprocess.run(["git", "bundle", "list-heads", str(bundle)], capture_output=True, text=True).stdout)
        self.assertFalse(str(bundle).startswith(str(self.vault)), "a mentés nem a vaultba kerül")

        # 5. visszaállítás: az elveszett tároló (félretéve, nem törölve) + két fájl a bundle-ből, bájtra
        kuka = self.t / "Kuka"
        kuka.mkdir()
        shutil.move(str(ws / "var" / "vault.git"), str(kuka / "vault.git"))
        eredeti = {rp: (self.vault / rp).read_bytes() for rp in ("Jegyzetek/Első.md", f"{JEGYZET}.md")}
        for rp in eredeti:
            shutil.move(str(self.vault / rp), str(kuka / rp.replace("/", "_")))
        eredmeny = visszaallitas.visszaallit(cfg, bundle)
        self.assertEqual(eredmeny["head"], fej)
        self.assertEqual(sorted(eredmeny["irt"]), sorted(eredeti))
        for rp, bajtok in eredeti.items():
            self.assertEqual((self.vault / rp).read_bytes(), bajtok, rp)
        self.assertEqual(self._vault_git("rev-parse", "HEAD").strip(), fej)

        # a core újraindul a visszaállított munkatéren: ugyanaz a történet, és tovább pillanatképez
        p2, k2 = self._core()
        self.assertEqual(k2["munkater_id"], id)
        kod, naplo2 = self._k(k2["port"], "GET", "/api/pillanat/vault/naplo?n=50")
        self.assertEqual(kod, 200, naplo2)
        self.assertIn(fej, [c["sha"] for c in naplo2["commitok"]])
        uj = self._ment_jegyzet(k2["port"], "Jegyzetek/Első.md", "---\ntags: [a]\n---\nA visszaállítás után is ment.\n")
        szarmazik = subprocess.run(["git", "--git-dir", str(ws / "var" / "vault.git"), "merge-base", "--is-ancestor", fej, uj["pillanat"]],
                                   capture_output=True, text=True)
        self.assertEqual(szarmazik.returncode, 0, "az új pillanatkép a visszaállított történetre épül")
        self._leallit(p2)

        # 6. a kódfába és a vaultba (a `.manifold`-on kívül, a mentett jegyzeteken túl) semmi nem került
        self.assertEqual(lenyomat(self.root, kihagy=()), self.kod_elotte, "a csak olvasható kódfa érintetlen")
        self.assertFalse((self.root / "var").exists())
        elvart = dict(self.vault_elotte)
        elvart["Jegyzetek/Első.md"] = "---\ntags: [a]\n---\nA visszaállítás után is ment.\n".encode("utf-8")
        elvart[f"{JEGYZET}.md"] = eredeti[f"{JEGYZET}.md"]
        self.assertEqual(lenyomat(self.vault), elvart, "a vault a két mentett jegyzeten kívül bájtra azonos")
        self.assertFalse(any(rp.startswith(".manifold") for rp in lenyomat(self.vault)), "a `.manifold` a lenyomaton kívül")


if __name__ == "__main__":
    unittest.main()
