"""S1: a frontend és az index közös, forrást/eltolásokat megőrző %% komment-szemantikája."""
import json
import re
import sqlite3
import statistics
import time
from pathlib import Path
import unittest
from unittest import mock

from core import automatika, szoveg_tisztit
from core.index import elemzo, feloldas, kereses, linkek, maszk, tar
from core.index.hibrid import frissites, hasonlo, kereso, vektortar
from tests.helpers import tmpdir
from tests.index_segedek import alvault, index_indit
from tests.hibrid_segedek import AlBeagyazo


def _kodpont(txt: str, utf16: int) -> int:
    return len(txt.encode("utf-16-le")[:utf16 * 2].decode("utf-16-le"))


class KozosFixtureTest(unittest.TestCase):
    def test_a_ts_elemzovel_egyezo_tartomany_es_valtozatlan_forras(self):
        adatok = json.loads((Path(__file__).parent / "adat/megjegyzes_index.json").read_text())
        for eset in adatok:
            with self.subTest(eset["nev"]):
                txt = eset["szoveg"]
                eredeti = txt.encode("utf-8")
                vart = [(_kodpont(txt, a), _kodpont(txt, b)) for a, b in eset["utf16_szakaszok"]]
                kapott = maszk.megjegyzesek(txt)
                self.assertEqual(kapott, vart)
                self.assertEqual([txt[a:b] for a, b in kapott], eset["megjegyzesek"])
                lathato = maszk.megjegyzes_nelkul(txt)
                self.assertEqual(len(lathato), len(txt))
                self.assertEqual([(i, c) for i, c in enumerate(lathato) if c in "\r\n"], [(i, c) for i, c in enumerate(txt) if c in "\r\n"])
                self.assertEqual(txt.encode("utf-8"), eredeti)


class KommentFogyasztoTest(unittest.TestCase):
    def test_egy_maszk_a_link_graf_atnevezes_es_emlites_utjan(self):
        txt = '😀 [[Visible]] Mention\r\nBefore %%[[Hidden]] [hidden](Hidden.md) Mention\r\n\r\n# Hidden\r\n- [ ] hidden #hidden\r\n```py\r\nfake code\r\n```\r\n%% after [shown](Visible.md) Mention\r\n'
        norm = txt.replace("\r\n", "\n")
        vart = ["Visible", "Visible.md"]
        self.assertEqual(feloldas.jegyzet_celok(norm), vart)
        self.assertEqual([l.cel for l in elemzo.elemez(norm).linkek], vart)
        talalatok = linkek.jegyzet_talalatok(txt)
        self.assertEqual([l.cel for l in talalatok], vart)
        self.assertEqual([txt[l.kezd:l.veg] for l in talalatok], vart)  # nyers CRLF/Unicode-cserehely
        emlitesek = kereses.emlites_talalatok(norm, [re.compile(r"Mention")])
        self.assertEqual([(e["sor"], e["oszlop"]) for e in emlitesek], [(1, 14), (9, 29)])

    def test_fts_es_strukturalt_adatok_nem_tartalmazzak_a_rejtett_reszt(self):
        txt = '# Visible\n- [ ] task %%sensitiveword 📅 2030-01-01%% visible\nBefore %%hidden\n\n# Hidden\n- [ ] hidden #hidden [[Hidden]]\n```python\n# fake\n```\n$$hiddenmath$$\n%% after\n\n```js\nreal code\n```\n# Visible2\n#visible\n'
        j = elemzo.elemez(txt)
        self.assertNotIn("sensitiveword", j.tartalom)
        self.assertNotIn("hidden", j.tartalom)
        self.assertEqual([x.cel for x in j.linkek], [])
        self.assertEqual([x["szoveg"] for x in j.fejezetek], ["Visible", "Visible2"])
        self.assertEqual([x["cimke"] for x in j.cimkek], ["visible"])
        self.assertEqual(len(j.feladatok), 1)
        self.assertNotIn("sensitiveword", j.feladatok[0]["szoveg"])
        self.assertEqual(j.feladatok[0]["datumok"], {})
        self.assertEqual(j.kepletek, [])
        self.assertEqual(j.kodblokkok, [{"nyelv": "js", "sor_kezd": 13, "sor_veg": 15}])

    def test_canvas_szoveg_es_kivonat_ugyanazt_a_kommentet_rejti(self):
        text = '[[Visible]] before %%hidden\n```\n[[Hidden]]\n%% after'
        adat = {"nodes": [{"id": "text", "text": text}, {"id": "file", "file": "Visible.md"}]}
        eredeti = json.dumps(adat, ensure_ascii=False)
        j = elemzo.elemez_canvas(adat, None)
        self.assertNotIn("hidden", j.tartalom)
        self.assertNotIn("Hidden", j.tartalom)
        self.assertEqual([x.cel for x in j.linkek], ["Visible", "Visible.md"])
        self.assertEqual(feloldas.canvas_celok(adat), ["Visible", "Visible.md"])
        self.assertEqual(json.dumps(adat, ensure_ascii=False), eredeti)
        self.assertEqual(szoveg_tisztit.egyszeru('Before %%hidden\n\n# hidden\n```\n%% after'), 'Before after')
        self.assertEqual(szoveg_tisztit.egyszeru('Before %%unclosed\n\nHidden'), 'Before')
        self.assertEqual(szoveg_tisztit.egyszeru('`%%literal%%` and [[A%%B|alias]]'), '%%literal%% and alias')

    def test_lezaratlan_es_nagy_egysoros_komment_skala(self):
        # Abszolút időkorlát helyett méretnövelési arány; a nagy eset hosszú sor, sok korábbi kód/comment jelölővel.
        # Ez fogja a soronként újraszeletelést és a bekezdésvége jelölőnkénti újrakeresését is.
        def mer(n):
            txt = ('`%%protected` %%hidden%% visible ' * n) + '%%open\n\n' + ('# Hidden [[Hidden]]\n' * n)
            idok = []
            for _ in range(5):
                kezdet = time.perf_counter()
                kapott = maszk.megjegyzesek(txt)
                idok.append(time.perf_counter() - kezdet)
            return max(statistics.median(idok), 0.001), txt, kapott
        mer(500)  # az interpreter/cache bemelegítése nem része a méretnövelési aránynak
        kicsi, _, _ = mer(2000)
        nagy, txt, kapott = mer(8000)
        self.assertEqual(len(kapott), 8001)
        self.assertEqual(kapott[-1], (txt.index('%%open'), len(txt)))
        self.assertLess(nagy / kicsi, 8)


class KommentMigracioTest(unittest.TestCase):
    def test_v6_invalidation_ujraepites_es_masodik_sync_noop(self):
        with tmpdir() as tmp:
            forras = '[[Visible]] %%secretword [[Hidden]] #hidden\n\n# Hidden\n- [ ] hidden\n%% visibleword\n'
            canvas = json.dumps({"nodes": [{"id": "n", "text": 'visibleword %%secretword [[Hidden]]%% [[Visible]]'}]})
            cfg, vault = alvault(tmp, {'.obsidian/app.json': '{}', 'Source.md': forras, 'Visible.md': '# Target\n', 'Hidden.md': '# Target\n', 'Deleted.md': 'deleted', 'Board.canvas': canvas, 'image.png': b'\x89PNG\r\n'})
            # Érvényes régi cache: a v6 pontosan a komment nélküli scanner-hívást használta. Az indexet a szokásos
            # út építi fel, nem kézzel gyártott FTS/link-sorokkal bizonyítjuk az újraelemzés szükségét.
            with mock.patch.object(maszk, 'megjegyzesek', return_value=[]):
                ix, _ = index_indit(cfg)
                try:
                    self.assertEqual(ix.kereses('secretword')["osszes"], 2)
                    (vault / 'Deleted.md').unlink()
                    self.assertTrue(ix.frissit(['Deleted.md']))
                    db = ix.db_ut
                finally:
                    ix.leallit()
            eredeti = {p.name: p.read_bytes() for p in vault.iterdir() if p.is_file()}
            c = tar.nyit(db, iro=True)
            elotte = {r['ut']: dict(r) for r in c.execute('SELECT * FROM fajl')}
            c.execute('PRAGMA user_version = 6')
            c.close()
            c = tar.nyit(db, iro=True)
            try:
                self.assertEqual(c.execute('PRAGMA user_version').fetchone()[0], 7)
                for r in c.execute('SELECT * FROM fajl'):
                    with self.subTest(r['ut']):
                        regi = elotte[r['ut']]
                        for kulcs in ('id', 'torolve', 'ctime_ns', 'indexelve'):
                            self.assertEqual(r[kulcs], regi[kulcs])
                        if r['tipus'] in ('md', 'canvas'):
                            self.assertIsNone(r['hash']); self.assertIsNone(r['mtime_ns'])
                        else:
                            self.assertEqual((r['hash'], r['mtime_ns']), (regi['hash'], regi['mtime_ns']))
            finally:
                c.close()
            with mock.patch.object(elemzo, 'elemez', wraps=elemzo.elemez) as md, mock.patch.object(elemzo, 'elemez_canvas', wraps=elemzo.elemez_canvas) as cv:
                ix, _ = index_indit(cfg)
                try:
                    self.assertEqual((md.call_count, cv.call_count), (3, 1))
                    self.assertEqual(ix.kereses('secretword')["osszes"], 0)
                    self.assertEqual(ix.kereses('visibleword')["osszes"], 2)
                    self.assertEqual(ix.visszahivatkozasok('Hidden.md')["forrasok"], [])
                    self.assertEqual({r['ut'] for r in ix.visszahivatkozasok('Visible.md')["forrasok"]}, {'Source.md', 'Board.canvas'})
                    c = tar.nyit(db)
                    kesz = {r['ut']: dict(r) for r in c.execute('SELECT * FROM fajl')}; c.close()
                    self.assertEqual({ut: r['id'] for ut, r in kesz.items()}, {ut: r['id'] for ut, r in elotte.items()})
                    self.assertEqual(kesz['Deleted.md']['torolve'], elotte['Deleted.md']['torolve'])
                    md.reset_mock(); cv.reset_mock()
                    self.assertTrue(ix.frissit(list(kesz)))
                    self.assertEqual((md.call_count, cv.call_count), (0, 0))
                    c = tar.nyit(db)
                    uj = {r['ut']: dict(r) for r in c.execute('SELECT * FROM fajl')}; c.close()
                    self.assertEqual(uj, kesz)
                finally:
                    ix.leallit()
            self.assertEqual({p.name: p.read_bytes() for p in vault.iterdir() if p.is_file()}, eredeti)


class KommentVektorCacheTest(unittest.TestCase):
    def test_valtozatlan_fajlhash_ujraepiti_a_d1_cachet_es_addig_nem_ad_regi_darabot(self):
        with tmpdir() as tmp:
            cfg, vault = alvault(tmp, {'.obsidian/app.json': '{}', 'Source.md': '# Source\nvisibleword %%secretword%%\n', 'Other.md': '# Other\nvisibleword\n'})
            with mock.patch.object(maszk, 'megjegyzesek', return_value=[]):
                ix, _ = index_indit(cfg)
            t = vektortar.Vektortar(Path(cfg.path('index')) / 'vektor.sqlite', motor='python')
            try:
                b = AlBeagyazo()
                with mock.patch.object(frissites, 'DARABOLAS_VERZIO', 'd1'):
                    frissites.frissit(ix._olvaso, t, b)
                hash_regi = t.jegyzet_hash('Source.md')
                self.assertTrue(any('secretword' in d.szoveg for d in t.darabok(ut='Source.md')))
                db = ix.db_ut
                ix.leallit()
                c = tar.nyit(db, iro=True); c.execute('PRAGMA user_version = 6'); c.close()
                eredeti = {p.name: p.read_bytes() for p in vault.iterdir() if p.is_file()}
                ix, _ = index_indit(cfg)
                try:
                    with ix._olvaso() as c:
                        self.assertEqual(c.execute("SELECT hash FROM fajl WHERE ut='Source.md'").fetchone()[0], hash_regi)
                    b.hivasok.clear()
                    # A régi tár read-only kapcsolaton is elavult; nincs írás és nincs kérdés-beágyazás a fallbackhez.
                    olvaso = vektortar.Vektortar(t.ut, csak_olvas=True, motor='python')
                    try:
                        class ProbeTiltott:
                            @property
                            def dim(self):
                                raise AssertionError('old cache fallback must not request a dimension/model probe')
                        self.assertEqual(kereso.HibridKereso(ix._olvaso, olvaso, ProbeTiltott()).miert_lexikai(), 'mas_modell_vektorai')
                        k = kereso.HibridKereso(ix._olvaso, olvaso, b)
                        r = k.keres('secretword')
                        self.assertEqual((r['mod'], r['ok'], r['osszes']), ('lexikai', 'mas_modell_vektorai', 0))
                        self.assertNotIn('secretword', k.legjobb_szoveg('Source.md', 'visibleword'))
                        jeloltek = k.darab_jeloltek('visibleword')
                        self.assertTrue(jeloltek)
                        self.assertTrue(all('secretword' not in j.darab.szoveg for j in jeloltek))
                        r = hasonlo.hasonlok(ix._olvaso, olvaso, 'Source.md')
                        self.assertEqual((r['allapot'], r['elavult'], r['talalatok']), ('nincs_vektor', True, []))
                        self.assertEqual(b.hivasok, [])
                    finally:
                        olvaso.close()
                    e = frissites.frissit(ix._olvaso, t, b)
                    self.assertTrue(e.ujraepites)
                    self.assertEqual(e.beagyazott_jegyzet, 2)
                    self.assertEqual(t.jegyzet_hash('Source.md'), hash_regi)
                    self.assertTrue(frissites.aktualis_darabolas(t.modell_kulcs()))
                    friss_darabok = t.darabok(ut='Source.md')
                    self.assertTrue(friss_darabok)
                    self.assertTrue(all('secretword' not in d.szoveg for d in friss_darabok))
                    b.hivasok.clear()
                    self.assertTrue(frissites.frissit(ix._olvaso, t, b).terv.ures)
                    self.assertEqual(b.hivasok, [])
                    self.assertEqual({p.name: p.read_bytes() for p in vault.iterdir() if p.is_file()}, eredeti)
                finally:
                    ix.leallit()
            finally:
                t.close()
                ix.leallit()

    def test_automatika_v2_cache_csak_a_vektorindexet_ervenyteleniti_a_meglevo_kapu_alatt(self):
        with tmpdir() as tmp:
            cfg, _ = alvault(tmp, {'.obsidian/app.json': '{}', 'Source.md': 'visible'})
            db = automatika.ut(cfg); db.parent.mkdir(parents=True, exist_ok=True)
            c = sqlite3.connect(db)
            c.executescript('BEGIN;' + automatika.MIGRACIOK[0] + automatika.MIGRACIOK[1] + 'PRAGMA user_version=2; COMMIT;')
            for fogyaszto, ut, tiltva in [('vektorindex', 'Source.md', None), ('vektorindex', 'Blocked.md', 'user-disabled'), ('kartya', 'Source.md', None)]:
                c.execute('INSERT INTO allapot(fogyaszto,ut,hash,alap,kimenet,tiltva,adat) VALUES (?,?,?,?,?,?,?)', (fogyaszto, ut, 'same-hash', '["preserved"]', 'Output.md', tiltva, '{"preserved":true}'))
            c.commit(); c.close()
            t = automatika.Tar(cfg)
            regi = t.sor('kartya', 'Source.md')
            self.assertEqual(t.sorok('kartya')['Source.md']['hash'], 'same-hash')
            self.assertIsNone(t.sorok('vektorindex')['Source.md']['hash'])
            self.assertEqual(t.sorok('vektorindex')['Blocked.md']['tiltva'], 'user-disabled')
            # Létező D8/kikapcsolt fogyasztó mellett nem indít új munkát. A hívható kapu és a feladatsor változatlan.
            ora, be = [1000.0], [False]
            idx = mock.Mock(); idx.fajl_allapot.return_value = {'Source.md': ('same-hash', 0, 7, 'Source.md'), 'Blocked.md': ('same-hash', 0, 7, 'Blocked.md'), 'Output.md': ('output-hash', 0, 7, 'Output.md')}
            queue = mock.Mock(); queue.fuggo.return_value = False; queue.submit.return_value = {'id': 'synthetic-vector-task'}
            fogyaszto = automatika.Fogyaszto('vektorindex', 'vektorindex', szuro=lambda ut: ut in ('Source.md', 'Blocked.md'), kuszob=0, csend_perc=2, onallo=True, engedelyezett=lambda cfg: be[0])
            with mock.patch.dict(automatika.REGISZTER, {'vektorindex': fogyaszto}, clear=True), mock.patch('core.mentes.migracio_elott') as mentes:
                u = automatika.Utemezo(cfg, idx, queue, ora=lambda: ora[0], indulasi_kesleltetes_mp=180)
                self.assertEqual(u.utem(), {'szunet': True}); queue.submit.assert_not_called()
                ora[0] += 181
                u.utem(); queue.submit.assert_not_called()
                be[0] = True
                u._teljes = True
                r = u.utem()
                queue.submit.assert_called_once_with('vektorindex', {})
                self.assertEqual(r['fogyasztok']['vektorindex']['bekuldve'], ['Source.md'])
                mentes.assert_called_once()
                u._teljes = True
                u.utem(); queue.submit.assert_called_once()
            self.assertEqual(t.sor('kartya', 'Source.md'), regi)
            self.assertEqual(t.sor('vektorindex', 'Blocked.md')['tiltva'], 'user-disabled')
            self.assertEqual(t.sor('vektorindex', 'Source.md')['alap'], '["preserved"]')
            c = sqlite3.connect(db); self.assertEqual(c.execute('PRAGMA user_version').fetchone()[0], 3); c.close()


if __name__ == "__main__":
    unittest.main()
