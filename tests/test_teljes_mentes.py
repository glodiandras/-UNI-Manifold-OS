"""CX-012: teljes, verziózott, inkrementális mentés; média, WAL, rekurzív állapot, kihagyott modellek/venv/runtime,
más gyökérbe visszaállítás és a lemezfigyelő. Kizárólag álrendszeren (ideiglenes mappák)."""
import json
import os
import sqlite3
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch
from core import config, snapshot, teljes_mentes as m
from tests.helpers import alg_core, ir, tmpdir


class TeljesMentesTest(unittest.TestCase):
    def setUp(self):
        self.t = tmpdir(); self.addCleanup(self.t.cleanup)
        self.cfg, self.root, self.v = alg_core(self.t.name)
        self.cel = Path(self.t.name) / 'mentések'; self.cel.mkdir()
        ir(self.v, 'Média/árvíz.png', b'\x89PNG\r\n', 'wb')
        ir(self.v, 'tananyag.lock', 'ez is adat')
        ir(self.v, 'A.md', '# Önálló cím\n![[Média/árvíz.png]]\n')
        ir(self.root, 'var/state/mély/állapot.json', '{"megvan":true}')
        ir(self.root, 'var/fuzet/bejovo/pótolhatatlan.heic', b'eredeti', 'wb')
        ir(self.root, 'requirements.lock', 'rögzített függőségek')
        ir(self.root, 'var/tmp/átmeneti', 'kihagyandó')
        ir(self.root, 'var/models/hub/modell.safetensors', b'nagy modell', 'wb')
        ir(self.root, 'var/venv/pyvenv.cfg', 'home = /régi/gép')
        ir(self.root, 'runtime/python/bin/python3', b'bin', 'wb')
        self.repo = snapshot.repos(self.cfg)['vault']; self.repo.init(); self.repo.commit('alap', {'Mos-Forras': 'kezi'})

    def ment(self):
        return Path(m.ment(self.cfg, self.cel, proba=True, log=lambda _: None)['ut'])

    def test_teljes_mas_utvonalon_es_sqlite_wal(self):
        with sqlite3.connect(self.cfg.path('tanulas_db')) as db:
            db.execute('PRAGMA journal_mode=WAL'); db.execute('CREATE TABLE adat(sz TEXT)')
            db.execute('INSERT INTO adat VALUES (?)', ('WAL-ban is megvan',)); db.commit()
            (self.root / 'var/state/python').symlink_to('../../bin/mos')
            ment = self.ment()
            jegy = m.ellenoriz(ment)
        utak = {e['ut'] for e in jegy['elemek']}
        self.assertIn('adat/vault/tananyag.lock', utak)
        self.assertIn('adat/os/requirements.lock', utak)
        self.assertNotIn('adat/os/var/tmp/átmeneti', utak)
        self.assertNotIn('adat/os/var/tanulas.sqlite-wal', utak)
        uj = Path(self.t.name) / 'máshová/új rendszer'
        r = m.visszaallit(ment, uj)
        self.assertTrue(r['ok'])
        self.assertTrue(any('runtime fetch' in t for t in r['teendok']))
        c = config.load({'MOS_ROOT': str(uj / 'Manifold-OS'), 'HOME': str(uj / 'home')})
        self.assertEqual(c.path('vault').resolve(), uj / 'Manifold')
        self.assertEqual((c.path('vault') / 'Média/árvíz.png').read_bytes(), b'\x89PNG\r\n')
        self.assertEqual((c.path('state') / 'mély/állapot.json').read_text(), '{"megvan":true}')
        self.assertEqual((c.path('fuzet_bejovo') / 'pótolhatatlan.heic').read_bytes(), b'eredeti')
        with sqlite3.connect(c.path('tanulas_db')) as db:
            self.assertEqual(db.execute('SELECT sz FROM adat').fetchone()[0], 'WAL-ban is megvan')
        self.assertTrue((c.path('state') / 'python').is_symlink())
        rp = snapshot.repos(c)['vault']
        self.assertEqual(rp.git('config', 'core.worktree').stdout.strip(), str(c.path('vault')))
        self.assertEqual(rp.git('status', '--porcelain').stdout, '')
        self.assertFalse(m.allapot(self.cfg)['ellenorzott'])  # a próba nem teljes külső védelem

    def test_vaulton_beluli_cel_kis_nagybetus_alakban_is_elutasitva(self):
        """A3-27: a szöveges összevetést a kis-nagybetű-érzéketlen APFS-en egy átírt nagybetűs út kijátszaná; a `vaultkivul`
        fájlrendszer-azonosság szerint tilt (a hard link csak a mentendő gyökereken kívül állhat)."""
        (self.v / 'mentes').mkdir()
        cel = self.v.parent / self.v.name.swapcase() / 'mentes'
        if not cel.exists():
            self.skipTest('[indokolt] kis-nagybetű-érzékeny fájlrendszer: a változat nem ugyanaz a mappa')
        with self.assertRaises(m.MentesHiba):
            m.ment(self.cfg, cel, proba=True, log=lambda _: None)

    def test_modellek_venv_runtime_kimarad_es_a_jegyzek_megnevezi(self):
        (self.root / 'var/state/py').symlink_to('../../runtime/python/bin/python3')
        jegy = m.ellenoriz(self.ment())
        utak = {e['ut'] for e in jegy['elemek']}
        for elotag in ('adat/os/var/models', 'adat/os/var/venv', 'adat/os/runtime'):
            self.assertFalse(any(u == elotag or u.startswith(elotag + '/') for u in utak), elotag)
        kihagyva = {k['kulcs']: k['visszaallitas'] for k in jegy['kihagyva']}
        self.assertEqual(set(kihagyva), {'models', 'venv', 'runtime', 'index', 'staging', 'archive'})
        self.assertIn('models pull', kihagyva['models'])
        link = next(e for e in jegy['elemek'] if e['ut'] == 'adat/os/var/state/py')
        self.assertTrue(link['kihagyott_cel'])          # a runtime fetch után él újra

    def test_munkafak_atmeneti_mappak_index_es_staging_kimarad(self):
        """A külső lemez megtelt (B-javító 1–3): a `.claude/worktrees/` (munkafánként saját `var/` és APFS-klónok), a beágyazott
        `…/var/tmp`, a `var/runs` élő naplói, az újraépíthető `{index}` és a staging/archive nem kerülhet a mentésbe; a
        gyökér rejtett fájlja (`.gitignore`) és a `var/state` maradék tartalma igen."""
        for rp in ('.claude/worktrees/x/var/tmp/klon/nagy.bin', '.claude/worktrees/x/core/a.py', '.claude/settings.json',
                   'var/x/var/tmp/beagyazott.bin', 'var/x/var/runs/F-1.log', 'var/x/var/cache/c.bin',
                   'var/runs/core.log', 'var/runs/F-20261014-1.log', 'var/index/vault.sqlite', 'var/index/vektor.sqlite',
                   'modulok/ytdlp/staging/yt/video.mp4', 'archive/video-eredeti/eredeti.mkv',
                   'var/tmp/proba/K-1-proba/Manifold/A.md'):
            ir(self.root, rp, b'x', 'wb')
        ir(self.root, '.gitignore', 'var/\n')
        ir(self.root, 'modulok/ytdlp/archive/downloaded.txt', 'youtube abc\n')
        ir(self.root, 'var/x/adat.json', '{}')
        jegy = m.ellenoriz(self.ment())
        utak = {e['ut'] for e in jegy['elemek']}
        for elotag in ('adat/os/.claude', 'adat/os/var/x/var/tmp', 'adat/os/var/x/var/runs', 'adat/os/var/x/var/cache',
                       'adat/os/var/runs', 'adat/os/var/index', 'adat/os/modulok/ytdlp/staging', 'adat/os/archive',
                       'adat/os/var/tmp'):
            self.assertFalse([u for u in utak if u == elotag or u.startswith(elotag + '/')], elotag)
        self.assertIn('adat/os/.gitignore', utak)
        self.assertIn('adat/os/var/x/adat.json', utak)
        self.assertIn('adat/os/modulok/ytdlp/archive/downloaded.txt', utak)     # a letöltési archívum (152 KB) marad
        self.assertIn('vaultból', {k['kulcs']: k['visszaallitas'] for k in jegy['kihagyva']}['index'])

    def test_kihagy_lista_a_konfigbol(self):
        ir(self.root, 'modulok/ytdlp/staging/yt/video.mp4', b'v', 'wb')
        ir(self.root, 'modulok/ytdlp/archive/downloaded.txt', 'youtube abc\n')
        with patch.dict(self.cfg.data, {'teljes_mentes': {'kihagy': ['ytdlp_archivum']}}):
            jegy = m.ellenoriz(self.ment())
        utak = {e['ut'] for e in jegy['elemek']}
        self.assertIn('adat/os/modulok/ytdlp/staging/yt/video.mp4', utak)              # a lista szerint: most benne van
        self.assertNotIn('adat/os/modulok/ytdlp/archive/downloaded.txt', utak)
        self.assertEqual({k['kulcs'] for k in jegy['kihagyva']}, {'models', 'venv', 'runtime', 'index', 'ytdlp_archivum'})

    def test_kihagyott_kulso_gyoker_nem_lesz_forras(self):
        """Ha egy kihagyott kulcs (pl. az `archive`) a `{os}`-on kívül áll, nem válhat külön mentési gyökérré."""
        kint = Path(self.t.name) / 'külső archívum'
        ir(kint, 'video-eredeti/x.mkv', b'e', 'wb')
        self.cfg = config.load({'MOS_ROOT': str(self.root), 'MOS_ARCHIVE': str(kint), 'HOME': str(Path(self.t.name) / 'home')})
        self.assertNotIn('archive', m.forrasok(self.cfg))
        self.assertNotIn('video_eredeti', m.forrasok(self.cfg))

    def test_a_zar_alatt_nincs_index_sqlite(self):
        """81(d): rövid kör-zár — az index SQLite-jainak `.backup()`-ja nem futhat a zár alatt (és nincs a mentésben)."""
        self.cfg.path('index').mkdir(parents=True, exist_ok=True)
        db = sqlite3.connect(self.cfg.path('index') / 'vault.sqlite')
        db.execute('CREATE TABLE t(x)'); db.commit(); db.close()
        masolt = []
        eredeti = m._Iro.fajl

        def fajl(iro, p, rp):
            masolt.append(Path(p).name)
            return eredeti(iro, p, rp)
        with patch.object(m._Iro, 'fajl', fajl):
            self.ment()
        self.assertNotIn('vault.sqlite', masolt)

    def test_masodik_futas_valtozatlant_hard_linkel_valtozottat_masol(self):
        elso = self.ment()
        (self.v / 'A.md').write_text('# Új tartalom\n')
        os.utime(self.v / 'A.md', ns=(1, 2))
        masodik = self.ment()
        self.assertNotEqual(elso, masodik)
        self.assertEqual(len(m.kesz_valtozatok(self.cel)), 2)
        regi, uj = elso / 'adat/vault/Média/árvíz.png', masodik / 'adat/vault/Média/árvíz.png'
        # A teszt-tmp APFS/HFS köteten van: a hard link itt kötelező (exFAT-tartalék: külön teszt).
        self.assertEqual(regi.stat().st_ino, uj.stat().st_ino)
        self.assertEqual(regi.stat().st_nlink, 2)
        self.assertNotEqual((elso / 'adat/vault/A.md').stat().st_ino, (masodik / 'adat/vault/A.md').stat().st_ino)
        self.assertEqual((masodik / 'adat/vault/A.md').read_text(), '# Új tartalom\n')
        self.assertEqual((elso / 'adat/vault/A.md').read_text(), '# Önálló cím\n![[Média/árvíz.png]]\n')
        m.ellenoriz(elso); m.ellenoriz(masodik)
        self.assertEqual(json.loads((masodik / 'jegyzek.json').read_text())['elozo'], elso.name)

    def test_link_nelkuli_kotet_masolatra_esik_vissza(self):
        self.ment()
        with patch.object(m.os, 'link', side_effect=OSError(45, 'nem támogatott')):
            masodik = self.ment()
        m.ellenoriz(masodik)
        self.assertEqual((masodik / 'adat/vault/Média/árvíz.png').stat().st_nlink, 1)

    def test_megtartott_valtozatok_ritkitasa(self):
        with patch.dict(self.cfg.data, {'teljes_mentes': {'megtartott': 2}}):
            for _ in range(3):
                self.ment()
        self.assertEqual(len(m.kesz_valtozatok(self.cel)), 2)

    def test_serult_fajlt_az_ellenorzes_eszreveszi(self):
        ment = self.ment()
        p = ment / 'adat/vault/Média/árvíz.png'
        os.unlink(p); p.write_bytes(b'\x89PNG\rX')      # azonos méret, más tartalom
        with self.assertRaises(m.MentesHiba): m.ellenoriz(ment)
        with self.assertRaises(m.MentesHiba): m.visszaallit(ment, Path(self.t.name) / 'cél')
        self.assertFalse((Path(self.t.name) / 'cél').exists())

    def test_felbeszakadt_nem_siker_es_a_kovetkezo_futas_takarit(self):
        with patch.object(m, '_masol', side_effect=OSError('nincs hely')):
            with self.assertRaises(OSError): self.ment()
        reszek = list(self.cel.glob('Manifold-*'))
        self.assertTrue(reszek and all(p.name.endswith('.resz') for p in reszek))
        self.assertFalse(m.allapot(self.cfg)['ellenorzott'])
        self.assertEqual(m.kesz_valtozatok(self.cel), [])
        with self.assertRaises(m.MentesHiba): m.ellenoriz(reszek[0])
        idegen = self.cel / 'saját mappa.resz'; idegen.mkdir()
        ment = self.ment()
        self.assertFalse(any(p.exists() for p in reszek))
        self.assertTrue(idegen.is_dir())                  # csak a saját névmintánkat töröljük
        self.assertEqual(m.kesz_valtozatok(self.cel), [ment])

    def test_kesz_jelolo_nelkul_nem_mentes(self):
        ment = self.ment(); (ment / m.KESZ).unlink()
        with self.assertRaises(m.MentesHiba): m.ellenoriz(ment)
        self.assertEqual(m.kesz_valtozatok(self.cel), [])

    def test_visszaallitas_csak_ures_celba_es_a_celmappabol_a_legutobbi(self):
        ment = self.ment()
        with self.assertRaises(m.MentesHiba): m.visszaallit(ment, self.v)
        self.assertTrue((self.v / 'A.md').read_text().startswith('# Önálló'))
        nem_ures = Path(self.t.name) / 'foglalt'; ir(nem_ures, 'x.txt', 'marad')
        with self.assertRaises(m.MentesHiba): m.visszaallit(self.cel, nem_ures)
        self.assertEqual((nem_ures / 'x.txt').read_text(), 'marad')
        uj = Path(self.t.name) / 'üres'
        self.assertEqual(m.visszaallit(self.cel, uj)['forras'], str(ment))
        self.assertEqual((uj / 'Manifold/Média/árvíz.png').read_bytes(), b'\x89PNG\r\n')
        self.assertEqual((uj / 'Manifold/A.md').read_bytes(), (self.v / 'A.md').read_bytes())

    def test_fuggvenyek_nem_mentenek_onmagukba_es_nem_kovetnek_kulso_linket(self):
        with self.assertRaises(m.MentesHiba): m.ment(self.cfg, self.v, proba=True)
        with self.assertRaises(m.MentesHiba): m.ment(self.cfg, self.cel)
        (self.v / 'külső').symlink_to(self.cel)
        with self.assertRaises(m.MentesHiba): self.ment()

    def test_jegyzek_utvonal_kilepes_elutasitva(self):
        ment = self.ment()
        d = json.loads((ment / 'jegyzek.json').read_text())
        d['elemek'][0]['ut'] = '../kilépés'
        (ment / 'jegyzek.json').write_text(json.dumps(d))
        (ment / 'jegyzek.sha256').write_text(m.sha(ment / 'jegyzek.json'))
        with self.assertRaises(m.MentesHiba): m.ellenoriz(ment)

    def test_kulso_allapot_egyszer_es_aktiv_konfig(self):
        kulso = Path(self.t.name) / 'más állapot'
        kulso.mkdir(); ir(kulso, 'mély/b.json', '{}')
        forras = Path(self.t.name) / 'más.toml'
        forras.write_text(self.cfg.source.read_text().replace('ido_perc = 30', 'ido_perc = 77'))
        self.cfg = config.load({'MOS_ROOT': str(self.root), 'MOS_CONFIG': str(forras), 'MOS_STATE': str(kulso),
                                'HOME': str(Path(self.t.name) / 'home')})
        ment = self.ment(); cel = Path(self.t.name) / 'vissza'
        m.visszaallit(ment, cel)
        c = config.load({'MOS_ROOT': str(cel / 'Manifold-OS'), 'HOME': str(cel / 'home')})
        self.assertEqual(c.section('mentes')['ido_perc'], 77)
        self.assertEqual((c.path('state') / 'mély/b.json').read_text(), '{}')


class _Sor:
    def __init__(self):
        self.kuldott, self.fugg = [], False

    def fuggo(self, tipus):
        return self.fugg

    def submit(self, tipus, params):
        self.kuldott.append((tipus, params)); self.fugg = True
        return {}


class LemezFigyeloTest(unittest.TestCase):
    def setUp(self):
        self.t = tmpdir(); self.addCleanup(self.t.cleanup)
        self.cfg, self.root, _ = alg_core(self.t.name)
        self.cel = Path(self.t.name) / 'lemez'; self.cel.mkdir()
        self.most = 1_000_000.0
        self.sor = _Sor()

    def figyelo(self, **b):
        self.cfg.data['teljes_mentes'] = {'figyelo_be': True, 'cel': str(self.cel), 'figyelo_ora': 24, **b}
        f = m.LemezFigyelo(self.cfg, self.sor, ora=lambda: self.most, indulasi_kesleltetes_mp=180, log=lambda _: None)
        return f

    def kulso_kotet(self):
        # A teszt-tmp ugyanazon a köteten van: a „külön kötet” vizsgálatot az eszközszám cseréjével játsszuk el.
        valodi = Path.stat
        cel = self.cel

        def stat(p, *a, **k):
            s = valodi(p, *a, **k)
            if Path(p) == cel:
                return os.stat_result((s.st_mode, s.st_ino, s.st_dev + 1, *tuple(s)[3:]))
            return s
        return patch.object(Path, 'stat', stat)

    def test_alapbol_ki_es_az_indulasi_szunetben_nem_kuld(self):
        f = m.LemezFigyelo(self.cfg, self.sor, ora=lambda: self.most, indulasi_kesleltetes_mp=0, log=lambda _: None)
        self.most += 10
        with self.kulso_kotet(): self.assertFalse(f.tick())
        f = self.figyelo()
        with self.kulso_kotet(): self.assertFalse(f.tick())          # D8: az indulás után még nem
        self.assertEqual(self.sor.kuldott, [])

    def test_csatlakoztatott_kotet_regi_mentessel_sorba_all_egyszer(self):
        f = self.figyelo(); self.most += 200
        self.assertFalse(f.tick())                                   # ugyanaz a kötet: nem külső lemez
        with self.kulso_kotet():
            self.assertTrue(f.tick())
            self.assertFalse(f.tick())                               # már függ / egy órás szünet
        self.assertEqual(self.sor.kuldott, [('teljes_mentes', {'cel': str(self.cel)})])

    def test_friss_ellenorzott_mentesnel_nem_kuld(self):
        ido = (datetime.fromtimestamp(self.most) - timedelta(hours=2)).astimezone().isoformat()
        self.cfg.path('state').mkdir(parents=True, exist_ok=True)
        (self.cfg.path('state') / m.ALLAPOT).write_text(json.dumps({'ut': str(self.cel), 'ido': ido,
                                                                     'ellenorzott': True, 'kulso': True}))
        f = self.figyelo(); self.most += 200
        with self.kulso_kotet(): self.assertFalse(f.tick())
        f = self.figyelo(figyelo_ora=1); self.most += 200
        with self.kulso_kotet(): self.assertTrue(f.tick())

    def test_lecsatolt_kotet(self):
        f = self.figyelo(cel=str(Path(self.t.name) / 'nincs')); self.most += 200
        self.assertFalse(f.tick())
