"""S1: a kísérőformátumok látható mezői, a teljes forrás kommentkontextusával.

Szintetikus stringek; nincs vault-, modell-, szerver- vagy fájlírás. Az expected
tartalom kézzel megadott, nem a javításhoz használt maszkból származik.
"""
import re
import unittest

from modulok.kartya import formatum as kartya
from modulok.kviz import ertekeles
from modulok.kviz import formatum as kviz
from modulok.osszefoglalas import formatum as ossz


def szavak(s):
    return re.sub(r"\s+", " ", s).strip()


KVIZ_FEJ = ('---\nSource: "[[A]]"\nKviz: KVIZ-20261018-120000-abcd\n---\n'
            '# Nyilvános — Kvíz 2026-10-18 1200\n\n')
KVIZ = ('> [!question] 1. kérdés — Nyilvános\n'
        '> Melyik a jó?\n>\n'
        '> - A) Egy\n> - B) Kettő\n> - C) Három\n> - D) Négy\n\n'
        '> [!success]- Megoldás\n> A) Egy\n>\n'
        '> Magyarázat: Ez a jó.\n'
        '> A jegyzetben ([[A#Fejezet|Fejezet]]): Ez az idézet.\n')
OSSZ_FEJ = ('---\nSource: "[[A]]"\nOsszefoglalas: OSSZ-20261018-120000-abcd\n'
            'Szint: jegyzet\n---\n')
OSSZ = ('# Nyilvános — Összefoglaló\n\n## Állítások\n\n'
        '1. Látható mondat. [[A#Fejezet|forrás]]\n'
        '   > „Ez az idézet.”\n')
VEDETT = (r'`%%inline%%`, $%%math%%$, [[A%%cel%%|név]], '
          r'[név](A%%cel%%), \%%escape és <span title="%%attr%%">jel</span>')


class KartyaKommentTest(unittest.TestCase):
    def test_nyitott_kommentbol_nincs_valasz_vagy_rejtett_id(self):
        e = kartya.elemez('> [!card]- K? %% rejtett\n> TITKOS VÁLASZ ^c-abcd1234\n')
        self.assertEqual(kartya.ervenyes(e), [])
        self.assertEqual(e.kartyak[0].kerdes, 'K?')
        self.assertFalse(e.kartyak[0].valasz.strip())
        self.assertIsNone(e.kartyak[0].azon)
        self.assertEqual([h['fajta'] for h in e.hibak], ['azonosito_nelkul'])

    def test_lathato_mezok_es_a_kommentvaltozas_nem_valtoztat_tartalmat(self):
        alap = '> [!card]- Mi a jó?\n> Ez a válasz.\n> — [[A#Fejezet]]\n\n^c-abcd1234\n'
        s = alap.replace('Mi a jó?', 'Mi %%KERDES_TITOK%% a jó?').replace('Ez a válasz.', 'Ez %%VALASZ_TITOK%% a válasz.')
        k, eredeti = kartya.ervenyes(kartya.elemez(s))[0], kartya.ervenyes(kartya.elemez(alap))[0]
        self.assertEqual((szavak(k.kerdes), szavak(k.valasz), k.azon, k.forras),
                         ('Mi a jó?', 'Ez a válasz.', 'c-abcd1234', 'A#Fejezet'))
        self.assertEqual(k.szoveg_hash(), eredeti.szoveg_hash())

    def test_tobbsoros_komment_nem_szakitja_el_a_fizikai_calloutot(self):
        s = ('Bevezetés.\n\n> [!card]- K?\n> Előtte.\n> %% rejtett\n'
             '> [!card]- HAMIS\n> TITOK ^c-deadbeef\n> %% Utána.\n'
             '> — [[A#Fejezet]]\n\n^c-abcd1234\n')
        for txt in (s, s.replace('\n', '\r\n')):
            with self.subTest(crlf='\r' in txt):
                e = kartya.elemez(txt)
                self.assertEqual(e.hibak, [])
                self.assertEqual(len(e.kartyak), 1)
                k = e.kartyak[0]
                self.assertEqual((szavak(k.valasz), k.azon, k.sor, k.forras),
                                 ('Előtte. Utána.', 'c-abcd1234', 3, 'A#Fejezet'))

    def test_rejtett_only_kerdes_nem_utemezheto(self):
        e = kartya.elemez('> [!card]- %%TITOK%%\n> Válasz.\n\n^c-abcd1234\n')
        self.assertEqual(kartya.ervenyes(e), [])
        self.assertIn('kerdes_nelkul', [h['fajta'] for h in e.hibak])

    def test_kod_math_link_es_escape_literal_marad(self):
        s = f'> [!card]- {VEDETT}\n> {VEDETT}\n\n^c-abcd1234\n'
        k = kartya.ervenyes(kartya.elemez(s))[0]
        self.assertEqual((k.kerdes, k.valasz), (VEDETT, VEDETT))

    def test_valodi_kerites_literalja_marad_de_fake_kartya_nem(self):
        s = ('```markdown\n> [!card]- HAMIS\n> %%literal%% ^c-deadbeef\n```\n\n'
             '> [!card]- K?\n> ```text\n> %%literal%%\n> ```\n\n^c-abcd1234\n')
        e = kartya.elemez(s)
        self.assertEqual(e.hibak, [])
        self.assertEqual([(k.kerdes, k.valasz, k.azon) for k in e.kartyak],
                         [('K?', '```text\n%%literal%%\n```', 'c-abcd1234')])

    def test_rejtett_kulon_id_nem_azonosito(self):
        e = kartya.elemez('> [!card]- K?\n> Válasz.\n\n%%\n^c-abcd1234\n%%\n')
        self.assertEqual(kartya.ervenyes(e), [])
        self.assertIsNone(e.kartyak[0].azon)


class KvizKommentTest(unittest.TestCase):
    def k(self, torzs=KVIZ, fej=KVIZ_FEJ):
        return kviz.elemez(fej + torzs)

    def test_plain_ui_szakaszcimbol_komment_nem_jon_vissza(self):
        e = self.k(KVIZ.replace('1. kérdés — Nyilvános', '1. kérdés — Nyilvános %%SZAKASZ_TITOK%%'))
        self.assertEqual(e.hibak, [])
        adat = ertekeles.kitoltesre(e.kviz)
        self.assertEqual(szavak(adat['kerdesek'][0]['szakasz']), 'Nyilvános')
        self.assertEqual(ertekeles.megoldas(e.kviz, 'k1', 0)['szakasz'].strip(), 'Nyilvános')

    def test_tobbsoros_komment_utan_a_valaszok_es_megoldas_megmaradnak(self):
        s = KVIZ.replace('> Melyik a jó?\n', '> Melyik a jó?\n> %% rejtett\n> TITOK\n> %%\n')
        e = self.k(s)
        self.assertEqual(e.hibak, [])
        self.assertEqual(len(e.kviz.kerdesek), 1)
        q = e.kviz.kerdesek[0]
        self.assertEqual((q.id, q.kerdes, q.valaszok, q.helyes), ('k1', 'Melyik a jó?', ['Egy', 'Kettő', 'Három', 'Négy'], 0))

    def test_comment_zaro_quote_prefixe_nelkul_is_folytatodik_a_torzs(self):
        s = KVIZ.replace('> Melyik a jó?', '> Melyik %% rejtett\n> TITOK\n> %% a jó?')
        e = self.k(s)
        self.assertEqual(e.hibak, [])
        self.assertEqual(szavak(e.kviz.kerdesek[0].kerdes), 'Melyik a jó?')

    def test_valasz_osszevetes_es_ui_visszajelzes_lathato_tartalombol(self):
        s = KVIZ.replace('> Melyik a jó?', '> Melyik %%KERDES_TITOK%% a jó?')
        s = s.replace('> - A) Egy', '> - A) Egy %%VALASZ_TITOK%%')
        s = s.replace('> A) Egy', '> A) Egy %%MEGOLDAS_TITOK%%')
        s = s.replace('Ez a jó.', 'Ez %%MAGYARAZAT_TITOK%% a jó.').replace('Ez az idézet.', 'Ez %%IDEZET_TITOK%% az idézet.')
        e = self.k(s)
        self.assertEqual(e.hibak, [])
        q = e.kviz.kerdesek[0]
        self.assertEqual(szavak(q.kerdes), 'Melyik a jó?')
        self.assertEqual(q.valaszok, ['Egy', 'Kettő', 'Három', 'Négy'])
        m = ertekeles.megoldas(e.kviz, 'k1', 0)
        self.assertEqual((szavak(m['magyarazat']), szavak(m['idezet'])), ('Ez a jó.', 'Ez az idézet.'))
        self.assertEqual(kviz.tartalom_hash(e.kviz), kviz.tartalom_hash(self.k().kviz))

    def test_h1_fallback_lathato_cim_source_hianyaban(self):
        fej = KVIZ_FEJ.replace('Source: "[[A]]"', 'Source: []').replace('Nyilvános —', 'Nyilvános %%CIM_TITOK%% —')
        e = self.k(fej=fej)
        self.assertEqual(e.hibak, [])
        self.assertEqual(szavak(e.kviz.cim), 'Nyilvános')

    def test_h1_fallback_elejen_inline_kod_tartalma_megmarad(self):
        fej = KVIZ_FEJ.replace('Source: "[[A]]"', 'Source: []').replace('Nyilvános —', '`%%literal%%` —')
        e = self.k(fej=fej)
        self.assertEqual(e.hibak, [])
        self.assertEqual(e.kviz.cim, '`%%literal%%`')

    def test_rejtett_only_kerdes_es_opcio_hibaja_valos(self):
        for regi, uj, fajta in [('Melyik a jó?', '%%TITOK%%', 'kerdes_nelkul'),
                                ('> - A) Egy', '> - A) %%TITOK%%', 'valasz_hiany')]:
            with self.subTest(fajta=fajta):
                e = self.k(KVIZ.replace(regi, uj))
                self.assertEqual(e.kviz.kerdesek, [])
                self.assertIn(fajta, [h['fajta'] for h in e.hibak])

    def test_inline_literal_vedelmek_es_crlf(self):
        s = KVIZ.replace('Melyik a jó?', VEDETT)
        s = s.replace('Ez a jó.', VEDETT)
        e = self.k(s.replace('\n', '\r\n'), KVIZ_FEJ.replace('\n', '\r\n'))
        self.assertEqual(e.hibak, [])
        self.assertEqual((e.kviz.kerdesek[0].kerdes, e.kviz.kerdesek[0].magyarazat), (VEDETT, VEDETT))

    def test_comment_es_kerites_fake_calloutja_nem_kerdes(self):
        fake = '> [!question] 7. kérdés\n> HAMIS\n'
        e = self.k('%%\n' + fake + '%%\n\n```markdown\n' + fake + '```\n\n' + KVIZ)
        self.assertEqual(e.hibak, [])
        self.assertEqual([q.id for q in e.kviz.kerdesek], ['k1'])


class OsszefoglaloKommentTest(unittest.TestCase):
    def e(self, torzs=OSSZ):
        return ossz.elemez(OSSZ_FEJ + torzs)

    def test_plain_ui_cim_allitas_es_idezet_lathato(self):
        s = OSSZ.replace('Nyilvános —', 'Nyilvános %%CIM_TITOK%% —')
        s = s.replace('Látható mondat.', 'Látható %%ALLITAS_TITOK%% mondat.')
        s = s.replace('Ez az idézet.', 'Ez %%IDEZET_TITOK%% az idézet.')
        e = self.e(s)
        self.assertEqual(e.hibak, [])
        o = e.osszefoglalo
        self.assertEqual(szavak(o.cim), 'Nyilvános')
        a = o.allitasok[0]
        self.assertEqual((szavak(a.szoveg), szavak(a.idezet), a.id), ('Látható mondat.', 'Ez az idézet.', 'a1'))
        self.assertEqual((a.horgony.cel, a.horgony.alcel), ('A', 'Fejezet'))

    def test_rejtett_only_idezet_nem_bizonyitek(self):
        e = self.e(OSSZ.replace('Ez az idézet.', '%%TITOK%%'))
        self.assertEqual(e.osszefoglalo.allitasok, [])
        self.assertEqual([h['fajta'] for h in e.hibak], ['idezet_hiany', 'nincs_allitas'])
        self.assertEqual(e.hibak[0]['sor'], 10)

    def test_tobbsoros_kommentben_heading_lista_es_idezet_nem_elem(self):
        fake = ('%%\n## Másik szakasz\n9. HAMIS [[A|forrás]]\n   > „TITOK”\n%%\n')
        s = OSSZ.replace('1. Látható', fake + '1. Látható')
        e = self.e(s)
        self.assertEqual(e.hibak, [])
        self.assertEqual([(a.id, a.szoveg) for a in e.osszefoglalo.allitasok], [('a1', 'Látható mondat.')])

    def test_kod_math_link_escape_literal_marad(self):
        s = OSSZ.replace('Látható mondat.', VEDETT.replace('[[A%%cel%%|név]], ', ''))
        s = s.replace('Ez az idézet.', VEDETT).replace('[[A#Fejezet|forrás]]', '[[A%%cel%%#Fejezet|forrás]]')
        e = self.e(s)
        self.assertEqual(e.hibak, [])
        a = e.osszefoglalo.allitasok[0]
        self.assertEqual(a.idezet, VEDETT)
        self.assertIn('`%%inline%%`', a.szoveg)
        self.assertIn('$%%math%%$', a.szoveg)
        self.assertEqual(a.horgony.cel, 'A%%cel%%')

    def test_valodi_kodkerites_es_nyitott_komment_nem_allitas(self):
        fake = '9. HAMIS [[A|forrás]]\n   > „TITOK”\n'
        e = self.e(OSSZ + '\n```markdown\n' + fake + '```\n\n%%\n' + fake)
        self.assertEqual(e.hibak, [])
        self.assertEqual([a.id for a in e.osszefoglalo.allitasok], ['a1'])

    def test_crlf_nfd_es_eredeti_hibas_sorszam(self):
        import unicodedata
        s = unicodedata.normalize('NFD', OSSZ_FEJ + OSSZ.replace('Ez az idézet.', '%%TITOK%%')).replace('\n', '\r\n')
        e = ossz.elemez(s)
        self.assertEqual(e.osszefoglalo.cim, 'Nyilvános')
        self.assertEqual(len(e.hibak), 2)
        self.assertEqual(e.hibak[0]['sor'], 10)
        self.assertEqual(e.osszefoglalo.allitasok, [])


if __name__ == '__main__':
    unittest.main()
