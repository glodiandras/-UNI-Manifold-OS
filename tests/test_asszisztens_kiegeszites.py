"""CX-011: nincs önálló vaultírás, a kikapcsolás és a törlés a folyó választ is érvényteleníti."""
import threading
import unittest
from core.asszisztens.allapot import Allapot
from core.asszisztens.kiegeszites import Kiegeszites
from tests.helpers import alg_core, tmpdir


class KiegeszitesTest(unittest.TestCase):
    def setUp(self):
        self.t = tmpdir(); self.addCleanup(self.t.cleanup)
        cfg, _, self.v = alg_core(self.t.name)
        self.cfg = cfg
        self.be = True; self.db = 0
        self.a = Allapot(cfg)
        self.k = Kiegeszites(self.a, lambda: self.be, self.general)

    def general(self, *_):
        self.db += 1
        return {'szoveg': ' és ellenőrzöm.'}

    def ker(self, azon='kiegeszites-0001'):
        return self.k.ker({'azon': azon, 'elotte': 'Megoldom a feladatot', 'utana': ''})

    def test_elfogadas_tanul_torol_felejt_es_vaultot_nem_ir(self):
        self.ker(); self.assertEqual(self.k.mintak()['mintak'], [])
        self.assertTrue(self.k.elfogad('kiegeszites-0001')['ok'])
        self.assertEqual(self.ker('kiegeszites-0002')['forras'], 'helyi minta')
        self.assertEqual(self.db, 1)
        self.k.torol(); self.assertEqual(self.k.mintak()['mintak'], [])
        self.assertFalse(self.k.elfogad('kiegeszites-0002')['ok'])
        self.assertEqual(list(self.v.glob('*.md')), [])

    def test_kikapcsolva_nem_indit_es_nem_tanul(self):
        self.be = False
        self.assertEqual(self.ker()['szoveg'], '')
        self.assertEqual(self.db, 0)
        self.assertFalse(self.a.ut.exists())

    def test_elavult_valasz_es_korai_megszakitas(self):
        indult, vege = threading.Event(), threading.Event()
        self.k.general = lambda *_: (indult.set(), vege.wait(2), {'szoveg': 'régi'})[-1]
        ki = []
        t = threading.Thread(target=lambda: ki.append(self.ker())); t.start()
        self.assertTrue(indult.wait(1))
        self.k.elvet('kiegeszites-0001'); vege.set(); t.join(3)
        self.assertEqual(ki[0]['szoveg'], '')
        self.k.elvet('kiegeszites-0002')
        self.assertEqual(self.ker('kiegeszites-0002')['szoveg'], '')

    def test_azon_es_hossz_korlatozott(self):
        from core.utvonalak import HttpError
        with self.assertRaises(HttpError): self.k.ker({'azon': 'x', 'elotte': 'y'})
        with self.assertRaises(HttpError): self.k.ker({'azon': 'kiegeszites-0001', 'elotte': 'x' * 6001})

    def test_kezzel_elfogadott_minta_modell_nelkul(self):
        self.k.tanit({'elotte': 'Megoldom a feladatot', 'szoveg': ' és ellenőrzöm.'})
        self.assertEqual(self.ker()['forras'], 'helyi minta')
        self.assertEqual(self.db, 0)
        self.assertEqual(list(self.v.glob('*.md')), [])

    def test_modell_alapbol_kikapcsolt_kalibracio_elott(self):
        from types import SimpleNamespace
        from unittest.mock import patch
        from core.kiegeszites_modell import general
        with patch('core.kiegeszites_modell.beallitas.betolt', side_effect=AssertionError('modellútvonal')):
            r = general(SimpleNamespace(cfg=self.cfg), 'Megoldom a feladatot', '', 'kiegeszites-0001')
        self.assertEqual(r['szoveg'], '')
        self.assertIn('ki van kapcsolva', r['ok'])


class KiegeszitesModokTest(unittest.TestCase):
    """J2: a kifejtés és az összefoglalás, a hangolás (Esc = elutasítás, átírás = kis súlyú jel, néma helyzetben modell sem fut),
    a szövegminta soronkénti törlése."""

    def setUp(self):
        from core.asszisztens.hangolo import Hangolo
        self.t = tmpdir(); self.addCleanup(self.t.cleanup)
        self.cfg, _, self.v = alg_core(self.t.name)
        self.a = Allapot(self.cfg)
        self.h = Hangolo(self.cfg, self.a)
        self.hivasok = []
        self.k = Kiegeszites(self.a, lambda: True, self.general, hangolo=self.h)

    def general(self, elotte, utana, azon, mod='folytat', kijeloles=''):
        self.hivasok.append((mod, kijeloles))
        return {'szoveg': 'Összefoglaló mondat.', 'proba': mod != 'folytat'}

    def test_kijeloles_modok_proba_jellel_es_minta_nelkul(self):
        r = self.k.ker({'azon': 'kiegeszites-0001', 'elotte': 'Bevezetés. ', 'mod': 'osszefoglal', 'kijeloles': 'Hosszú szöveg.', 'kezi': True})
        self.assertEqual((r['szoveg'], r['mod'], r['proba']), ('Összefoglaló mondat.', 'osszefoglal', True))
        self.assertEqual(self.hivasok, [('osszefoglal', 'Hosszú szöveg.')])
        self.assertTrue(self.k.elfogad('kiegeszites-0001')['ok'])
        self.assertEqual(self.k.mintak()['mintak'], [], 'az összefoglalás nem lesz szövegminta')
        self.assertEqual(self.h.lista()[0]['kulcs'], 'kiegeszites|osszefoglal')
        r = self.k.ker({'azon': 'kiegeszites-0002', 'elotte': 'x', 'mod': 'kifejt', 'kijeloles': ' '})
        self.assertEqual(r['szoveg'], '')
        self.assertIn('Jelöld ki', r['ok'])
        from core.utvonalak import HttpError
        with self.assertRaises(HttpError):
            self.k.ker({'azon': 'kiegeszites-0003', 'elotte': 'x', 'mod': 'atir'})
        with self.assertRaises(HttpError):
            self.k.ker({'azon': 'kiegeszites-0003', 'elotte': 'x', 'mod': 'kifejt', 'kijeloles': 'x' * 4001})

    def test_esc_elutasit_atiras_kis_suly_folyo_keres_nem_szamit(self):
        self.k.ker({'azon': 'kiegeszites-0001', 'elotte': 'Megoldom a feladatot'})
        self.k.elvet('kiegeszites-0001', True)
        self.k.ker({'azon': 'kiegeszites-0002', 'elotte': 'Megoldom a feladatot'})
        self.k.elvet('kiegeszites-0002', False)
        self.k.elvet('kiegeszites-0099', True)                    # nem látott kérés: nem számít
        sor = self.h.lista()[0]
        self.assertEqual((sor['kulcs'], sor['elfogad'], sor['elutasit']), ('kiegeszites|folytat', 0.0, 1.3))

    def test_nema_helyzetben_az_automatikus_keres_nem_hiv_modellt(self):
        for _ in range(5):
            self.h.rogzit('kiegeszites', 'folytat', 'elutasit')
        r = self.k.ker({'azon': 'kiegeszites-0001', 'elotte': 'Megoldom a feladatot'})
        self.assertTrue(r['nema'])
        self.assertEqual(self.hivasok, [])
        r = self.k.ker({'azon': 'kiegeszites-0002', 'elotte': 'Megoldom a feladatot', 'kezi': True})
        self.assertEqual(r['szoveg'], 'Összefoglaló mondat.')
        self.assertEqual(r['allas']['szint'], 'nema')

    def test_szovegminta_soronkent_torolheto(self):
        self.k.tanit({'elotte': 'Megoldom a feladatot', 'szoveg': ' és ellenőrzöm.'})
        self.k.tanit({'elotte': 'Az atommag részei', 'szoveg': ': proton, neutron.'})
        self.assertTrue(self.k.torol_minta('Megoldom a feladatot')['ok'])
        self.assertEqual([m['elotte'] for m in self.k.mintak()['mintak']], ['Az atommag részei'])
        self.assertFalse(self.k.torol_minta('nincs ilyen')['ok'])


class KiegeszitesModellutTest(unittest.TestCase):
    """J2: a modellút csak a `modell = true` mellett; kalibrált sorral a mért kérés (`folytat`) a `kiegeszites` feladattal, a nem mért
    módok és a kifejezett próba-modell `proba`-ként; a core modellt nem tölt (a worker kapja a kérést); a munkakeret a korlát."""

    def setUp(self):
        from types import SimpleNamespace
        self.t = tmpdir(); self.addCleanup(self.t.cleanup)
        self.cfg, _, _ = alg_core(self.t.name)
        self.cfg.data.setdefault('asszisztens', {}).setdefault('kiegeszites', {})['modell'] = True
        self.kuldott = []
        self.megszakitva = []
        self.app = SimpleNamespace(cfg=self.cfg, worker=SimpleNamespace(biztosit=lambda: 'http://worker'),
                                   _worker_megszakit=self.megszakitva.append)

    def futtat(self, dontes=None, hiba=None, feladatok=None, **kw):
        """`feladatok`: router-feladat → Dontes vagy kivétel (J4: a kijelölés-módok saját feladata); különben csak a
        `kiegeszites` feladatot fogadja (`dontes` / `hiba`), a többire kalibrált sor nincs."""
        from unittest.mock import patch
        from core import kiegeszites_modell as KM
        from core.modell import beallitas as B
        from core.modell.router import RoutingHiba
        self.kert = []

        def keres(u, ut, body, timeout=None):
            self.kuldott.append(body)
            return {'choices': [{'message': {'content': ' a válasz'}}], 'proba': bool(body.get('proba'))}

        def valaszt(self_, feladat, keret, kizart_csalad=None):
            self.kert.append(feladat)
            tabla = feladatok if feladatok is not None else {'kiegeszites': hiba or dontes}
            ki = tabla.get(feladat, RoutingHiba(f'nincs kalibrált: {feladat}'))
            if isinstance(ki, Exception):
                raise ki
            return ki

        b = B.betolt(self.cfg, {})
        with patch.object(KM.kalibracio, 'megnyit', return_value=type('T', (), {'close': lambda s: None})()), \
                patch.object(KM.Router, 'valaszt', valaszt), patch.object(KM.kliens, 'keres', keres), \
                patch.object(KM.beallitas, 'betolt', return_value=b):
            return KM.general(self.app, 'A víz kémiai képlete ', '.', 'kiegeszites-0001', **kw), b

    def test_kalibralt_folytatas_a_mert_kerest_kuldi(self):
        from core.modell.router import Dontes
        from core.modell import eval as E
        b0 = __import__('core.modell.beallitas', fromlist=['betolt']).betolt(self.cfg, {})
        m = b0.modell('qwen3_vl_4b')
        r, b = self.futtat(Dontes(m))
        self.assertEqual((r['szoveg'], r['proba'], r['modell']), (' a válasz', False, 'qwen3_vl_4b'))
        body = self.kuldott[0]
        self.assertEqual(body['feladat'], 'kiegeszites')
        self.assertNotIn('model', body)
        self.assertEqual((body['mod'], body['keret']), ('interaktiv', b.keret_gb('munka')))
        # a mért kérés: a `mos eval … kiegeszites` tétele ugyanerre a bemenetre ugyanígy oldódik fel
        from core.kiegeszites_modell import keres as KK
        vart = E.keres_beallitas(b, m, 'kiegeszites', KK('folytat', 'A víz kémiai képlete ', '.'))
        self.assertEqual({k: body[k] for k in vart}, vart)

    def test_kalibralatlan_kijeloles_mod_proba_a_folytatas_modelljevel(self):
        """J4: a kijelölés-mód saját feladatának kalibrált sora nélkül a folytatás kalibrált modellje próbaként fut rá, a mód
        mért kérésével (a mód feladatának mérés-beállítása)."""
        from core.modell.router import Dontes
        from core.modell import eval as E
        from core.kiegeszites_modell import keres as KK
        b0 = __import__('core.modell.beallitas', fromlist=['betolt']).betolt(self.cfg, {})
        m = b0.modell('qwen3_vl_4b')
        r, b = self.futtat(Dontes(m), mod='osszefoglal', kijeloles='Hosszú szöveg.')
        self.assertTrue(r['proba'])
        self.assertEqual(self.kert, ['osszefoglal_kijeloles', 'kiegeszites'])
        self.assertEqual((self.kuldott[0]['model'], self.kuldott[0]['proba']), ('qwen3_vl_4b', True))
        self.assertNotIn('feladat', self.kuldott[0])
        vart = E.keres_beallitas(b, m, 'osszefoglal_kijeloles', KK('osszefoglal', 'A víz kémiai képlete ', '.', 'Hosszú szöveg.'))
        self.assertEqual({k: self.kuldott[0][k] for k in vart}, vart)

    def test_kalibralt_kijeloles_mod_eles_a_sajat_feladataval(self):
        """J4: a mód saját feladatának kalibrált sora élesíti a módot: `feladat` a kérésben, nincs `proba`, és a kérés bájtra
        az, amit a `mos eval <modell> <feladat>` az aranyhalmaz tételére küld."""
        import json
        from core.modell.router import Dontes
        from core.modell import eval as E
        from core.kiegeszites_modell import keres as KK
        b0 = __import__('core.modell.beallitas', fromlist=['betolt']).betolt(self.cfg, {})
        m = b0.modell('qwen35_4b')
        for mod, feladat in (('kifejt', 'kifejtes'), ('osszefoglal', 'osszefoglal_kijeloles')):
            self.kuldott.clear()
            r, b = self.futtat(feladatok={feladat: Dontes(m)}, mod=mod, kijeloles='A kijelölt rész.')
            self.assertEqual((r['proba'], r['modell']), (False, 'qwen35_4b'))
            self.assertEqual(self.kert, [feladat])                 # a folytatás feladatához nem nyúl
            body = self.kuldott[0]
            self.assertEqual(body['feladat'], feladat)
            self.assertNotIn('model', body)
            self.assertNotIn('proba', body)
            vart = E.keres_beallitas(b, m, feladat, KK(mod, 'A víz kémiai képlete ', '', 'A kijelölt rész.'))
            self.assertEqual(json.dumps({k: body[k] for k in vart}, ensure_ascii=False, sort_keys=True),
                             json.dumps(vart, ensure_ascii=False, sort_keys=True))
            self.assertIs(body['gondolkodas'], False)                 # [meres.feladat.<f>]: az éles kérés is ezt kapja

    def test_a_folytatas_csak_a_kiegeszites_feladaton(self):
        from core.modell.router import Dontes
        b0 = __import__('core.modell.beallitas', fromlist=['betolt']).betolt(self.cfg, {})
        r, _ = self.futtat(feladatok={'kifejtes': Dontes(b0.modell('qwen35_4b'))})
        self.assertEqual(self.kert, ['kiegeszites'])
        self.assertIn('méréssel ellenőrzött', r['ok'])
        self.assertEqual(self.kuldott, [])

    def test_kalibralatlan_csak_a_proba_modell_es_csak_a_keretben(self):
        from core.modell.router import RoutingHiba
        r, _ = self.futtat(hiba=RoutingHiba('nincs kalibrált'))
        self.assertEqual(r['szoveg'], '')
        self.assertIn('méréssel ellenőrzött', r['ok'])
        self.assertEqual(self.kuldott, [])
        self.cfg.data['asszisztens']['kiegeszites']['proba_modell'] = 'qwen3_vl_4b'
        r, _ = self.futtat(hiba=RoutingHiba('nincs kalibrált'))
        self.assertTrue(r['proba'])
        self.assertEqual(self.kuldott[-1]['model'], 'qwen3_vl_4b')
        self.cfg.data['asszisztens']['kiegeszites']['proba_modell'] = 'gemma4_12b'      # csak a távol-keretbe fér
        n = len(self.kuldott)
        r, b = self.futtat(hiba=RoutingHiba('nincs kalibrált'))
        self.assertGreater(b.modell('gemma4_12b').csucs_gb, b.keret_gb('munka'))
        self.assertIn('munkakeretbe', r['ok'])
        self.assertEqual(len(self.kuldott), n)

    def test_worker_hiba_megszakit(self):
        from unittest.mock import patch
        from core import kiegeszites_modell as KM
        from core.modell.router import Dontes
        b = __import__('core.modell.beallitas', fromlist=['betolt']).betolt(self.cfg, {})

        def rossz(*a, **k):
            raise KM.kliens.KliensHiba(503, 'leállt')
        with patch.object(KM.kalibracio, 'megnyit', return_value=type('T', (), {'close': lambda s: None})()), \
                patch.object(KM.Router, 'valaszt', lambda *a, **k: Dontes(b.modell('qwen3_vl_4b'))), \
                patch.object(KM.kliens, 'keres', rossz):
            r = KM.general(self.app, 'x', '', 'kiegeszites-0001')
        self.assertEqual(r['szoveg'], '')
        self.assertEqual(self.megszakitva, ['KIEG-kiegeszites-0001'])


class AranyhalmazTest(unittest.TestCase):
    """J2: a `kiegeszites` aranyhalmaz a `mos eval` szerződése szerint betölthető, a tétel kérése az éles `folytat` kérés."""

    def test_feladat_modul_es_pontozo(self):
        import importlib.util
        from tests.helpers import REPO
        from core.kiegeszites_modell import keres
        spec = importlib.util.spec_from_file_location('kieg_arany', REPO / 'modulok' / 'eval' / 'kiegeszites' / 'feladat.py')
        mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
        tetelek = list(mod.tetelek(None))
        self.assertGreaterEqual(len(tetelek), 12)
        self.assertEqual(mod.ROUTER_FELADAT, 'kiegeszites')
        t = tetelek[1]
        self.assertEqual(t['keres'], keres('folytat', t['vart']['elotte'], t['vart']['utana']))
        jo = [{'valasz': t['vart']['elfogadhato'][0], 'vart': t['vart']} for t in tetelek]
        self.assertEqual(mod.pontoz(jo)['pontszam'], 1.0)
        rossz = [{'valasz': '```kód```', 'vart': t['vart']} for t in tetelek]
        self.assertEqual(mod.pontoz(rossz)['pontszam'], 0.0)
        self.assertFalse(mod.formatum_ok(tetelek[0]['vart']['elotte'] + 'x', tetelek[0]['vart']))
