"""F3 (§5): a belső lemezes mentés munkatér-tudatos. Munkaterenként külön mentési mappa (`{backup_gyoker}/{munkater_id}`), a
mappa tulajdonosjelölője (`.manifold-mentes.json`: saját → normál rotáció, idegen → nincs rotáció és figyelmeztetés, jelölő
nélküli, nem üres „örökölt” mappa → a régi bundle csak ismert fejekkel törlődik, az állapotmásolat rotációja ki), és a
vaultban lévő mentési mappa elutasítása. Álvaulton, ál-HOME alatt: a valódi `~/Manifold-backup`-hoz nem nyúl."""
import json
import os
import re
import shutil
import sqlite3
import subprocess
import unittest
from pathlib import Path
from unittest import mock

from core import config, frame, mentes, snapshot
from tests.helpers import alg_bundle, alg_core, ir, tmpdir

ID_A = "a" * 32
ID_B = "b" * 32


def git(gyoker: Path, *args: str) -> str:
    p = subprocess.run(["git", "-C", str(gyoker), "-c", "user.name=t", "-c", "user.email=t@t", *args],
                       capture_output=True, text=True, env=snapshot.hermetikus_env())
    assert p.returncode == 0, p.stderr
    return p.stdout


def idegen_bundle(hova: Path, tmp: Path) -> Path:
    """Egy MÁSIK tár bundle-je (más commitokkal): az örökölt mappában ismeretlen fejű bundle."""
    tar = tmp / f"idegen-{hova.stem}"
    tar.mkdir()
    git(tar, "init", "-q")
    (tar / "x.md").write_text("másik vault\n", encoding="utf-8")
    git(tar, "add", "-A")
    git(tar, "commit", "-q", "-m", "idegen")
    git(tar, "bundle", "create", "-q", str(hova), "--all")
    return hova


def jelolo(backup: Path, munkater_id: str | None, vault: str | None) -> Path:
    backup.mkdir(parents=True, exist_ok=True)
    p = backup / mentes.JEL_NEV
    p.write_text(json.dumps({"formatum": 1, "munkater_id": munkater_id, "vault": vault,
                             "letrehozva": "2026-01-01T00:00:00+00:00"}), encoding="utf-8")
    return p


def sqlite_fajl(p: Path, ertek: str = "egy") -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(p)
    con.execute("CREATE TABLE IF NOT EXISTS t(v TEXT)")
    con.execute("INSERT INTO t VALUES (?)", (ertek,))
    con.commit()
    con.close()


class Hordozhato(unittest.TestCase):
    """Hordozható elrendezés (a fejlesztő SSD-je): álgyökér, `{home}/Manifold-backup`, azonosító nélkül."""

    def setUp(self):
        self._t = tmpdir()
        self.addCleanup(self._t.cleanup)
        self.t = Path(self._t.name)
        self.cfg, self.root, self.v = alg_core(self._t.name)
        ir(self.v, "A.md", "# A\n")
        self.repo = snapshot.repos(self.cfg)["vault"]
        self.repo.init()
        self.repo.commit("alap", {"Mos-Forras": "kezi"})
        self.backup = self.cfg.path("backup")

    def cfg_ujra(self, **mentes_kulcsok) -> config.Config:
        """Az `os.toml` `[mentes]` kulcsai átírva (mint a `test_mentes`-ben), majd újratöltés."""
        toml = self.root / "config" / "os.toml"
        szoveg = toml.read_text(encoding="utf-8")
        for k, v in mentes_kulcsok.items():
            szoveg = re.sub(rf"^{k} = .*$", f"{k} = {v}", szoveg, count=1, flags=re.M)
        toml.write_text(szoveg, encoding="utf-8")
        return config.load({"MOS_ROOT": str(self.root), "HOME": str(self.t / "home")})

    def nevek(self, minta: str) -> list[str]:
        return sorted(p.name for p in self.backup.glob(minta))

    def regi_sajat_bundle(self, nev: str = "vault-20250101-000001.bundle") -> Path:
        """A tár egy régebbi állapotának bundle-je (a fejei megvannak a tárban)."""
        self.backup.mkdir(parents=True, exist_ok=True)
        ut = self.backup / nev
        self.repo.git("bundle", "create", "-q", str(ut), "--all")
        return ut

    # ------------------------------------------------------------ üres mappa → jelölő

    def test_az_elso_iras_ures_mappaba_beirja_a_jelolot(self):
        self.assertEqual(mentes.tulajdonos(self.cfg), "ures")                    # nincs is mappa
        self.assertEqual(len(mentes.ment(self.cfg, allapot=False)), 1)
        jel = json.loads((self.backup / mentes.JEL_NEV).read_text(encoding="utf-8"))
        self.assertEqual((jel["munkater_id"], jel["vault"]), (None, str(self.v.resolve())))   # azonosító nélkül: a vault azonosít
        self.assertTrue(jel["letrehozva"])
        self.assertEqual(mentes.tulajdonos(self.cfg), "sajat")

    def test_a_finder_szemete_nem_teszi_a_mappat_oroklottve(self):
        self.backup.mkdir(parents=True)
        (self.backup / ".DS_Store").write_bytes(b"x")
        self.assertEqual(mentes.tulajdonos(self.cfg), "ures")
        mentes.ment(self.cfg, allapot=False)
        self.assertEqual(mentes.tulajdonos(self.cfg), "sajat")

    def test_a_jelolo_csak_irasnal_keletkezik_az_olvasas_nem_irja(self):
        mentes.friss(self.repo, self.backup)
        mentes.hiba_olvas(self.cfg)
        mentes.tulajdonos(self.cfg)
        self.assertFalse(self.backup.exists())

    def test_a_probaklon_mentese_nem_hoz_letre_mappat_es_jelolot(self):
        self.repo.git("config", frame.KLON_JEL, "1")
        self.assertEqual(mentes.ment(self.cfg), [])
        self.assertFalse(self.backup.exists())

    # ------------------------------------------------------------ saját: a mai rotáció

    def test_sajat_jelolovel_a_rotacio_a_mai(self):
        mentes.ment(self.cfg, allapot=False)                                    # jelölő beírva
        for i in range(3):
            (self.backup / f"vault-2025010{i}-000000.bundle").write_bytes(b"regi")
        cfg = self.cfg_ujra(megtartott_bundle=2)
        mentes.ment(cfg, allapot=False)
        self.assertEqual(len(self.nevek("vault-*.bundle")), 2)                  # a keep fölöttiek (a régiek) törölve
        self.assertNotIn("vault-20250100-000000.bundle", self.nevek("vault-*.bundle"))
        self.assertEqual(mentes.tulajdonos(cfg), "sajat")

    def test_sajat_mappaban_az_allapotmasolat_rotal(self):
        sqlite_fajl(self.cfg.path("router_db"))
        mentes.ment(self.cfg, allapot=False)
        for i in range(3):
            (self.backup / f"mos-allapot-2025010{i}-000000").mkdir()
        cfg = self.cfg_ujra(allapot_megtartott=2)
        self.assertIsNotNone(mentes.allapot_masolat(cfg))
        self.assertEqual(len(self.nevek("mos-allapot-*")), 2)

    # ------------------------------------------------------------ idegen: nincs rotáció, figyelmeztetés

    def test_idegen_jelolo_nincs_rotacio_es_figyelmeztetes(self):
        jel = jelolo(self.backup, ID_B, str(self.t / "masik-vault"))
        elotte = jel.read_bytes()
        for i in range(3):
            (self.backup / f"vault-2025010{i}-000000.bundle").write_bytes(b"masik munkater")
        cfg = self.cfg_ujra(megtartott_bundle=1)
        hibak: dict = {}
        ki = mentes.ment(cfg, hibak=hibak, allapot=False)
        self.assertEqual(len(ki), 1)                                            # a mentés megvan (az adat védelme előbbre való)
        self.assertEqual(len(self.nevek("vault-*.bundle")), 4)                  # 3 idegen + 1 új: semmi sem törlődött
        self.assertIn(mentes.IDEGEN_KULCS, hibak)
        self.assertEqual(jel.read_bytes(), elotte)                              # a másik munkatér jelölőjét nem írjuk át
        self.assertEqual(mentes.tulajdonos(cfg), "idegen")

    def test_idegen_mappaban_az_allapotmasolat_es_a_migracio_sem_rotal(self):
        jelolo(self.backup, ID_B, None)
        sqlite_fajl(self.cfg.path("router_db"))
        for i in range(3):
            (self.backup / f"mos-allapot-2025010{i}-000000").mkdir()
        for i in range(4):
            (self.backup / f"mos-migracio-pos-v1-2025010{i}-000000.sqlite").write_bytes(b"regi")
        cfg = self.cfg_ujra(allapot_megtartott=1, megtartott_migracio=1)
        self.assertIsNotNone(mentes.allapot_masolat(cfg))
        mentes.migracio_elott(cfg, cfg.path("router_db"), 1)
        self.assertEqual(len(self.nevek("mos-allapot-*")), 4)
        self.assertEqual(len(self.nevek("mos-migracio-pos-v1-*.sqlite")), 4)
        self.assertEqual(len(self.nevek("mos-migracio-router-v1-*.sqlite")), 1)  # a saját másolat megvan

    def test_olvashatatlan_vagy_idegen_formaju_jelolo_idegen(self):
        for tartalom in ("nem json", "[]", '{"munkater_id": 5, "vault": null}', '{"vault": "x"}'):
            self.backup.mkdir(parents=True, exist_ok=True)
            (self.backup / mentes.JEL_NEV).write_text(tartalom, encoding="utf-8")
            self.assertEqual(mentes.tulajdonos(self.cfg), "idegen", tartalom)
        (self.backup / mentes.JEL_NEV).unlink()
        (self.backup / mentes.JEL_NEV).symlink_to(self.t / "nincs-ilyen")
        self.assertEqual(mentes.tulajdonos(self.cfg), "idegen")                  # lógó link nem jelölő

    def test_masik_vault_azonosito_nelkul_idegen(self):
        mentes.ment(self.cfg, allapot=False)
        masik = self.t / "work" / "MasikVault"
        masik.mkdir()
        cfg2 = config.load({"MOS_ROOT": str(self.root), "HOME": str(self.t / "home"), "MOS_VAULT": str(masik),
                            "MOS_BACKUP": str(self.backup)})
        self.assertEqual(mentes.tulajdonos(cfg2), "idegen")
        self.assertEqual(mentes.tulajdonos(self.cfg), "sajat")

    def test_a_figyelmeztetes_a_kilepeskori_hibanyomba_kerul_es_a_siker_torli(self):
        jel = jelolo(self.backup, ID_B, None)
        mentes.kilepeskor(self.cfg)
        d = mentes.hiba_olvas(self.cfg)
        self.assertIsNotNone(d)
        self.assertIn(mentes.IDEGEN_KULCS, d["hibak"])
        jel.unlink()                                                             # a felhasználó külön mappát választ
        (self.backup / "vault-20250101-000000.bundle").unlink(missing_ok=True)
        shutil.rmtree(self.backup)
        mentes.kilepeskor(self.cfg)
        self.assertIsNone(mentes.hiba_olvas(self.cfg))

    def test_verseny_ha_egy_masik_iro_megelozte_az_o_jelolojet_tiszteljuk(self):
        def megelozo(cfg, backup):
            jelolo(backup, ID_B, None)
            raise FileExistsError(backup / mentes.JEL_NEV)
        with mock.patch.object(mentes, "_jel_ir", side_effect=megelozo):
            self.assertEqual(mentes._tulajdonos_biztosit(self.cfg), "idegen")

    # ------------------------------------------------------------ örökölt: ismeretlen fejű bundle marad

    def test_oroklott_mappaban_csak_az_ismert_fejek_torlodnek(self):
        """A v2-vel közös `~/Manifold-backup`: nincs jelölő, van tartalom. A régi bundle csak akkor törlődik, ha minden feje
        megvan EBBEN a tárban; az idegen, a csonka és az ismeretlen fejű marad, a jelölő nem keletkezik."""
        sajat = self.regi_sajat_bundle("vault-20250101-000001.bundle")
        idegen = idegen_bundle(self.backup / "vault-20250101-000002.bundle", self.t)
        csonka = self.backup / "vault-20250101-000003.bundle"
        csonka.write_bytes(b"nem bundle")
        cfg = self.cfg_ujra(megtartott_bundle=1)
        self.assertEqual(mentes.tulajdonos(cfg), "orokolt")
        ki = mentes.ment(cfg, allapot=False)
        self.assertEqual(len(ki), 1)
        marad = self.nevek("vault-*.bundle")
        self.assertNotIn(sajat.name, marad)                                      # a saját régi: a fejei megvannak → törölhető
        self.assertIn(idegen.name, marad)
        self.assertIn(csonka.name, marad)
        self.assertEqual(len(marad), 3)
        self.assertFalse((self.backup / mentes.JEL_NEV).exists())                # a közös mappát nem jelöljük meg
        self.assertEqual(mentes.tulajdonos(cfg), "orokolt")

    def test_oroklott_mappaban_nincs_allapotmasolat_rotacio(self):
        sqlite_fajl(self.cfg.path("router_db"))
        self.backup.mkdir(parents=True)
        for i in range(3):
            (self.backup / f"mos-allapot-2025010{i}-000000").mkdir()
        cfg = self.cfg_ujra(allapot_megtartott=1, allapot_napi=0)
        self.assertIsNotNone(mentes.allapot_masolat(cfg))
        self.assertEqual(len(self.nevek("mos-allapot-*")), 4)

    def test_oroklott_mappaban_a_migracios_masolat_sem_rotal_a_sajat_mappaban_igen(self):
        """A v2-vel közös mappában a `mos-migracio-<fájl>-v*` nevek a másik telepítés biztonsági másolatai is: ott nincs rotáció (a
        legújabb `keep` a kettő közül maradna, a másik régi másolatai törlődnének). A saját (jelölt) mappában a rotáció a mai."""
        self.backup.mkdir(parents=True)
        for i in range(4):
            (self.backup / f"mos-migracio-router-v1-2025010{i}-000000.sqlite").write_bytes(b"regi")
        sqlite_fajl(self.cfg.path("router_db"))
        cfg = self.cfg_ujra(megtartott_migracio=2)
        mentes.migracio_elott(cfg, cfg.path("router_db"), 1)
        self.assertEqual(len(self.nevek("mos-migracio-router-v1-*.sqlite")), 5)           # 4 régi + az új: semmi sem törlődött
        self.assertFalse((self.backup / mentes.JEL_NEV).exists())
        jelolo(self.backup, None, str(self.v.resolve()))                                 # a mappa a miénk lett
        mentes.migracio_elott(cfg, cfg.path("router_db"), 1)
        self.assertEqual(len(self.nevek("mos-migracio-router-v1-*.sqlite")), 2)

    def test_oroklott_mappaban_a_masik_iro_felkesz_tmp_fajlja_nem_torlodik_a_regi_igen(self):
        """A közös mappában a másik író (v2) éppen készülő bundle-je / állapotmásolata nem esik a takarítás áldozatául; a több órás
        maradék viszont igen (egy megszakadt mentésé)."""
        sqlite_fajl(self.cfg.path("router_db"))
        self.regi_sajat_bundle("vault-20250101-000001.bundle")                            # tartalom: a mappa nem üres, jelölő nincs
        friss_bundle = self.backup / "vault-20260101-000000.bundle.tmp"
        regi_bundle = self.backup / "vault-20250101-000000.bundle.tmp"
        friss_mappa = self.backup / "mos-allapot-20260101-000000.tmp"
        regi_mappa = self.backup / "mos-allapot-20250101-000000.tmp"
        for f in (friss_bundle, regi_bundle):
            f.write_bytes(b"felkesz")
        for d in (friss_mappa, regi_mappa):
            d.mkdir()
        for p in (regi_bundle, regi_mappa):
            os.utime(p, (1_700_000_000, 1_700_000_000))
        self.assertEqual(mentes.tulajdonos(self.cfg), "orokolt")
        self.assertEqual(len(mentes.ment(self.cfg)), 2)                                   # a vault-bundle és az állapotmásolat
        self.assertTrue(friss_bundle.exists() and friss_mappa.exists())
        self.assertFalse(regi_bundle.exists() or regi_mappa.exists())

    def test_oroklott_mappaban_a_kodtar_bundle_is_fejellenorzessel_torlodik(self):
        subprocess.run(["git", "-C", str(self.root), "init", "-q"], check=True, capture_output=True)
        git(self.root, "commit", "-q", "--allow-empty", "-m", "alap")
        self.backup.mkdir(parents=True)
        sajat = self.backup / "mos-kodtar-20250101-000001.bundle"
        git(self.root, "bundle", "create", "-q", str(sajat), "--all")
        idegen = idegen_bundle(self.backup / "mos-kodtar-20250101-000002.bundle", self.t)
        cfg = self.cfg_ujra(megtartott_bundle=1)
        ki = mentes.ment(cfg, allapot=False)
        self.assertTrue(any(p.name.startswith("mos-kodtar-") for p in ki))
        marad = self.nevek("mos-kodtar-*.bundle")
        self.assertNotIn(sajat.name, marad)
        self.assertIn(idegen.name, marad)

    def test_fejek_ismertek(self):
        olvas = lambda *a: mentes._olvas(self.repo, *a)                          # noqa: E731
        sajat = self.regi_sajat_bundle()
        self.assertTrue(mentes._fejek_ismertek(olvas, sajat))
        idegen = idegen_bundle(self.backup / "idegen.bundle", self.t)
        self.assertFalse(mentes._fejek_ismertek(olvas, idegen))
        csonka = self.backup / "csonka.bundle"
        csonka.write_bytes(b"x")
        self.assertFalse(mentes._fejek_ismertek(olvas, csonka))
        self.assertFalse(mentes._fejek_ismertek(olvas, self.backup / "nincs.bundle"))

    # ------------------------------------------------------------ a bundle-mag `torolheto` szabálya

    def test_bundle_keszit_torolheto(self):
        dest = self.t / "cel"
        for i in range(3):
            dest.mkdir(exist_ok=True)
            (dest / f"x-2025010{i}-000000.bundle").write_bytes(b"regi")

        def keszit(tmp: Path) -> None:
            tmp.write_bytes(b"uj")
        snapshot.bundle_keszit("x", keszit, dest, 1, lambda p: p.name.endswith("1-000000.bundle"))
        self.assertEqual(sorted(p.name for p in dest.glob("x-*.bundle"))[:2],
                         ["x-20250100-000000.bundle", "x-20250102-000000.bundle"])   # csak az „1” törölhető volt
        self.assertEqual(len(list(dest.glob("x-*.bundle"))), 3 + 1 - 1)

    def test_bundle_keszit_torolheto_kivetele_azt_jelenti_hogy_marad(self):
        dest = self.t / "cel"
        dest.mkdir()
        (dest / "x-20250101-000000.bundle").write_bytes(b"regi")

        def rossz(_p: Path) -> bool:
            raise mentes.MentesHiba("időkorlát")
        snapshot.bundle_keszit("x", lambda tmp: tmp.write_bytes(b"uj"), dest, 1, rossz)
        self.assertEqual(len(list(dest.glob("x-*.bundle"))), 2)

    def test_bundle_keszit_alapesetben_mindent_torol_a_keep_folott(self):
        dest = self.t / "cel"
        dest.mkdir()
        for i in range(3):
            (dest / f"x-2025010{i}-000000.bundle").write_bytes(b"regi")
        snapshot.bundle_keszit("x", lambda tmp: tmp.write_bytes(b"uj"), dest, 2)
        self.assertEqual(len(list(dest.glob("x-*.bundle"))), 2)

    # ------------------------------------------------------------ a mentési mappa nem lehet a vaultban

    def test_a_vaultban_levo_mentesi_mappa_elutasitva_es_nem_jon_letre(self):
        for rel in ("Mentesek", ".manifold/var/mentes"):
            cel = self.v / rel
            cfg = config.load({"MOS_ROOT": str(self.root), "HOME": str(self.t / "home"), "MOS_BACKUP": str(cel)})
            with self.assertRaises(mentes.BackupUtHiba):
                mentes.ment(cfg)
            hibak: dict = {}
            self.assertEqual(mentes.ment(cfg, hibak=hibak), [])
            self.assertIn(mentes.UT_KULCS, hibak)
            with self.assertRaises(mentes.BackupUtHiba):
                mentes.allapot_masolat(cfg)
            with self.assertRaises(OSError):                                     # a migráció-előtti hívók az OSError-t kezelik
                mentes.migracio_elott(cfg, cfg.path("router_db"), 1)
            self.assertFalse(cel.exists(), rel)
        self.assertFalse((self.v / "Mentesek").exists())

    def test_a_vault_maga_es_a_kis_nagybetus_alakja_is_elutasitva(self):
        cfg = config.load({"MOS_ROOT": str(self.root), "HOME": str(self.t / "home"), "MOS_BACKUP": str(self.v)})
        with self.assertRaises(mentes.BackupUtHiba):
            mentes.ment(cfg)
        nagy = self.v.parent / self.v.name.swapcase() / "Mentes"
        if (self.v.parent / self.v.name.swapcase()).exists():                    # kis-nagybetű-érzéketlen fájlrendszer
            cfg = config.load({"MOS_ROOT": str(self.root), "HOME": str(self.t / "home"), "MOS_BACKUP": str(nagy)})
            with self.assertRaises(mentes.BackupUtHiba):
                mentes.ment(cfg)

    def test_a_vaulton_kivuli_mentesi_mappa_rendben(self):
        cfg = config.load({"MOS_ROOT": str(self.root), "HOME": str(self.t / "home"),
                           "MOS_BACKUP": str(self.t / "mentesek" / "egy")})
        self.assertEqual(len(mentes.ment(cfg, allapot=False)), 1)

    # ------------------------------------------------------------ az állapotforrások

    def test_allapot_forrasok_hordozhato_munkater_nelkul_valtozatlan(self):
        nevek = [n for n, _ in mentes.allapot_forrasok(self.cfg)]
        self.assertFalse([n for n in nevek if n.startswith("workspace/")])
        ir(self.v, ".manifold/workspace.toml", f'[workspace]\nid = "{ID_A}"\n')
        ir(self.v, ".manifold/schema.json", "{}")
        cfg = config.load({"MOS_ROOT": str(self.root), "HOME": str(self.t / "home")})
        nevek = [n for n, _ in mentes.allapot_forrasok(cfg)]
        self.assertIn("workspace/workspace.toml", nevek)
        self.assertIn("workspace/schema.json", nevek)


class Termek(unittest.TestCase):
    """Termék-elrendezés (`X.app/Contents/Resources/manifold`): `{backup_gyoker}/{munkater_id}`, az azonosító a jelölőben."""

    def setUp(self):
        self._t = tmpdir()
        self.addCleanup(self._t.cleanup)
        self.t = Path(self._t.name)
        self.root = alg_bundle(self._t.name)
        self.home = self.t / "home"

    def munkater(self, nev: str, munkater_id: str, **env) -> config.Config:
        vault = self.t / nev
        (vault / ".manifold").mkdir(parents=True, exist_ok=True)
        (vault / ".manifold" / "workspace.toml").write_text(f'[workspace]\nid = "{munkater_id}"\n', encoding="utf-8")
        cfg = config.load({"MOS_ROOT": str(self.root), "HOME": str(self.home), "MOS_VAULT": str(vault), **env})
        ir(vault, "A.md", f"# {nev}\n")
        repo = snapshot.repos(cfg)["vault"]
        cfg.path("var").mkdir(parents=True, exist_ok=True)
        repo.init()
        repo.commit("alap", {"Mos-Forras": "kezi"})
        return cfg

    def test_munkaterenkent_kulon_mappa_sajat_jelolovel(self):
        a, b = self.munkater("A-vault", ID_A), self.munkater("B-vault", ID_B)
        self.assertEqual(a.path("backup").name, ID_A)
        self.assertEqual(b.path("backup").name, ID_B)
        self.assertEqual(a.path("backup").parent, a.path("backup_gyoker"))
        self.assertEqual(a.path("backup").parent, b.path("backup").parent)       # gépszintű gyökér, munkaterenként almappa
        for cfg, azon in ((a, ID_A), (b, ID_B)):
            self.assertEqual(mentes.tulajdonos(cfg), "ures")
            self.assertEqual(len(mentes.ment(cfg, allapot=False)), 1)
            jel = json.loads((cfg.path("backup") / mentes.JEL_NEV).read_text(encoding="utf-8"))
            self.assertEqual((jel["munkater_id"], jel["vault"]), (azon, str(cfg.path("vault").resolve())))
            self.assertEqual(mentes.tulajdonos(cfg), "sajat")
        self.assertEqual(len(list(a.path("backup").glob("vault-*.bundle"))), 1)  # nem keveredik a másik munkatér bundle-jével
        self.assertEqual(len(list(b.path("backup").glob("vault-*.bundle"))), 1)

    def test_a_masik_munkater_mappajanak_masolata_idegen(self):
        a, b = self.munkater("A-vault", ID_A), self.munkater("B-vault", ID_B)
        mentes.ment(a, allapot=False)
        shutil.copytree(a.path("backup"), b.path("backup"))                      # a felhasználó átmásolta A mentéseit B helyére
        for i in range(3):
            (b.path("backup") / f"vault-2025010{i}-000000.bundle").write_bytes(b"A munkatere")
        hibak: dict = {}
        self.assertEqual(mentes.tulajdonos(b), "idegen")
        mentes.ment(b, hibak=hibak, allapot=False)
        self.assertIn(mentes.IDEGEN_KULCS, hibak)
        self.assertEqual(len(list(b.path("backup").glob("vault-2025010?-000000.bundle"))), 3)   # semmi sem törlődött

    def test_az_athelyezett_vault_azonos_azonositoval_sajat_marad_es_a_jelolo_frissul(self):
        a = self.munkater("A-vault", ID_A)
        mentes.ment(a, allapot=False)
        uj = self.t / "Athelyezett"
        shutil.move(str(a.path("vault")), str(uj))
        a2 = config.load({"MOS_ROOT": str(self.root), "HOME": str(self.home), "MOS_VAULT": str(uj)})
        self.assertEqual(a2.path("backup"), a.path("backup"))
        self.assertEqual(mentes.tulajdonos(a2), "sajat")
        mentes.ment(a2, allapot=False)
        jel = json.loads((a2.path("backup") / mentes.JEL_NEV).read_text(encoding="utf-8"))
        self.assertEqual((jel["munkater_id"], jel["vault"]), (ID_A, str(uj.resolve())))

    def test_az_azonositot_megtarto_masik_letezo_vault_orokolt_mappat_kap_nincs_rotacio(self):
        """Az azonosító a vaulttal utazik: egy másolat, egy letöltött vault ugyanazt hordozhatja (a `workspace.nyit` még nem futott, vagy a
        CLI/`bin/mos` útja soha nem fut). A jelölő azonosítója egyezik, de a jelölt vault egy MÁSIK, ma is létező mappa: a mappa nem
        „saját” — a másik vault mentéseit nem forgathatjuk, és a jelölőt sem írjuk át."""
        a = self.munkater("A-vault", ID_A)
        mentes.ment(a, allapot=False)
        backup = a.path("backup")
        eredeti_jel = (backup / mentes.JEL_NEV).read_bytes()
        for i in range(12):
            (backup / f"vault-20250{i + 1:02d}01-000000.bundle").write_bytes(b"A munkatere")
        d = self.munkater("D-vault", ID_A)                                         # a másolat az azonosítót megtartotta
        self.assertEqual(d.path("backup"), backup)
        self.assertEqual(mentes.tulajdonos(d), "orokolt")
        hibak: dict = {}
        self.assertEqual(len(mentes.ment(d, hibak=hibak)), 2)                      # a mentés megvan (a bundle és az állapotmásolat)
        self.assertEqual(len(list(backup.glob("vault-20250??01-000000.bundle"))), 12)   # semmi sem törlődött (ismeretlen fejű)
        self.assertEqual((backup / mentes.JEL_NEV).read_bytes(), eredeti_jel)      # az A jelölőjét nem írtuk át
        self.assertEqual(mentes.tulajdonos(a), "sajat")                            # az eredeti a saját mappáját forgatja tovább

    def test_az_athelyezett_vault_regi_helye_a_jeloloben_marad_es_az_orzes_a_masolatnal_is_megvan(self):
        a = self.munkater("A-vault", ID_A)
        mentes.ment(a, allapot=False)
        regi = str(a.path("vault").resolve())
        uj = self.t / "Athelyezett"
        shutil.move(str(a.path("vault")), str(uj))
        a2 = config.load({"MOS_ROOT": str(self.root), "HOME": str(self.home), "MOS_VAULT": str(uj)})
        self.assertEqual(mentes.tulajdonos(a2), "sajat")
        mentes.ment(a2, allapot=False)
        jel = json.loads((a2.path("backup") / mentes.JEL_NEV).read_text(encoding="utf-8"))
        self.assertEqual((jel["vault"], jel["vaultok"]), (str(uj.resolve()), [regi]))
        self.munkater("A-vault", ID_A)                                             # a régi helyen újra megjelenik egy azonos azonosítójú mappa
        self.assertEqual(mentes.tulajdonos(a2), "orokolt")
        self.assertEqual(mentes.tulajdonos(config.load({"MOS_ROOT": str(self.root), "HOME": str(self.home),
                                                         "MOS_VAULT": str(self.t / "A-vault")})), "orokolt")

    def test_az_azonosito_nelkuli_jelolo_ugyanarra_a_vaultra_sajat_es_azonositot_kap(self):
        a = self.munkater("A-vault", ID_A)
        jelolo(a.path("backup"), None, str(a.path("vault").resolve()))          # hordozhatóból érkezett: a vault azonosított
        self.assertEqual(mentes.tulajdonos(a), "sajat")
        mentes.ment(a, allapot=False)
        jel = json.loads((a.path("backup") / mentes.JEL_NEV).read_text(encoding="utf-8"))
        self.assertEqual(jel["munkater_id"], ID_A)
        b = self.munkater("B-vault", ID_B)
        jelolo(b.path("backup"), None, str(a.path("vault").resolve()))          # más vaulté volt
        self.assertEqual(mentes.tulajdonos(b), "idegen")

    def test_a_backup_gyoker_a_vaultban_elutasitva(self):
        vault = self.t / "A-vault"
        for rel in ("Mentesek", ".manifold/var/mentesek"):
            a = self.munkater("A-vault", ID_A, MOS_BACKUP_GYOKER=str(vault / rel))
            self.assertEqual(a.path("backup"), vault / rel / ID_A)
            with self.assertRaises(mentes.BackupUtHiba):
                mentes.ment(a)
            hibak: dict = {}
            self.assertEqual(mentes.ment(a, hibak=hibak), [])
            self.assertIn(mentes.UT_KULCS, hibak)
            with self.assertRaises(mentes.BackupUtHiba):
                mentes.allapot_masolat(a)
            self.assertFalse((vault / rel).exists(), rel)

    def test_a_vaulton_kivuli_backup_gyoker_rendben_es_a_gyoker_marad_a_telepiteske(self):
        a = self.munkater("A-vault", ID_A, MOS_BACKUP_GYOKER=str(self.t / "Kulso lemez" / "Manifold"))
        self.assertEqual(len(mentes.ment(a, allapot=False)), 1)
        self.assertTrue((self.t / "Kulso lemez" / "Manifold" / ID_A / mentes.JEL_NEV).is_file())

    def test_allapot_forrasok_viszik_a_munkater_fajljait(self):
        a = self.munkater("A-vault", ID_A)
        ir(a.path("workspace"), "schema.json", "{}")
        nevek = dict(mentes.allapot_forrasok(a))
        self.assertEqual(nevek["workspace/workspace.toml"], a.path("workspace") / "workspace.toml")
        self.assertEqual(nevek["workspace/schema.json"], a.path("workspace") / "schema.json")
        (a.path("workspace") / "schema.json").unlink()
        (a.path("workspace") / "schema.json").symlink_to("/etc/hosts")           # ellenséges vault: a link nem másolódik
        self.assertNotIn("workspace/schema.json", dict(mentes.allapot_forrasok(a)))

    def test_az_allapotmasolat_termekben_tartalmazza_a_munkater_fajljat(self):
        a = self.munkater("A-vault", ID_A)
        sqlite_fajl(a.path("router_db"))
        cel = mentes.allapot_masolat(a)
        self.assertTrue((cel / "workspace" / "workspace.toml").is_file())
        self.assertEqual((a.path("backup") / mentes.JEL_NEV).is_file(), True)
        self.assertEqual(mentes.tulajdonos(a), "sajat")


if __name__ == "__main__":
    unittest.main()
