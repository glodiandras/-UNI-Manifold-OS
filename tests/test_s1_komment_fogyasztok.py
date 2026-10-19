"""S1: a közös kommentmaszk fogyasztói látható tartalmat olvasnak, nyers forrást írnak."""
from __future__ import annotations

import hashlib
import unittest

from core import automatika, vaultio
from core.gepi_iras import szakasz_beszur
from core.index import elemzo
from core.utvonalak import HttpError
from modulok.kapuk import forras as F
from modulok.kartya import horgony as H


class ForrasKommentTest(unittest.TestCase):
    def test_rejtett_idezet_nem_bizonyitek_a_lathato_pontos(self):
        md = '# C\n\n## Fejezet\nVisible source sentence. %%Unique Hidden Evidence%% End.\n\n%% Standalone secret evidence. %%\n'
        f = F.ForrasSzoveg.jegyzetbol(md)
        self.assertIsNone(f.keres('Unique Hidden Evidence', kuszob=1.0))
        self.assertIsNone(f.keres('Standalone secret evidence', kuszob=1.0))
        t = f.keres('Visible source sentence', kuszob=1.0)
        self.assertIsNotNone(t)
        self.assertEqual(f.szoveg[slice(*t.hely)], 'Visible source sentence')
        self.assertEqual(f.szakaszok[t.szakasz].cim, 'Fejezet')

    def test_kommentben_fake_fence_fejlec_matek_nem_tartalom(self):
        md = '# C\nVisible before. %%hidden\n```py\n# Hidden heading\n$$\nsecret\n%% Visible after.\n\n## Actual\nActual paragraph.\n\n```py\n# Code heading\nprint("%%literal%% <!--literal-->")\n```\n'
        sz = F.elokeszit(md)
        self.assertEqual([s.cim for s in sz], [None, 'Actual'])
        txt = '\n'.join(s.szoveg for s in sz)
        self.assertNotIn('secret', txt)
        self.assertNotIn('Hidden heading', txt)
        self.assertIn('Visible after.', txt)
        self.assertIn('print("%%literal%% <!--literal-->")', txt)
        self.assertIn('# Code heading', txt)

    def test_h1_komment_html_es_kod_utan_az_elso_lathato(self):
        for rejtett in ('%%\n# Hidden\n%%\n', '<!--\n# Hidden\n-->\n', '```md\n# Hidden\n```\n'):
            with self.subTest(rejtett=rejtett):
                self.assertEqual(F.h1_cim(rejtett + '# Public\n'), 'Public')

    def test_inline_komment_nincs_a_cimben_vagy_horgonyban(self):
        md = '# Public %%secret%%\n\n## Section %%private%%\nParagraph.\n'
        f = F.ForrasSzoveg.jegyzetbol(md)
        self.assertEqual(f.cim, 'Public')
        self.assertEqual([(s.cim, s.ut, s.horgony) for s in f.szakaszok], [('Section', ('Section',), 'Section')])
        self.assertNotIn('secret', F.h1_cim('# Public %%secret%% Tail\n'))

    def test_inline_kod_teljes_cime_es_literaljai_megmaradnak(self):
        cim = '`%%literal%% <!--literal-->`'
        self.assertEqual(F.h1_cim(f'# {cim}\n'), cim)
        sz = F.elokeszit(f'# C\n\n## {cim}\nParagraph.\n')
        self.assertEqual(sz[0].cim, cim)
        self.assertEqual(F.h1_cim('# `code` Public\n'), '`code` Public')

    def test_nyitott_bekezdes_vegeig_rejtett_de_nyitott_heading_literal(self):
        f = F.ForrasSzoveg.jegyzetbol('# C\nVisible. %%unclosed\n\n## Hidden\nUnique secret evidence.\n')
        self.assertEqual(f.szoveg, 'Visible.')
        self.assertIsNone(f.keres('Unique secret evidence', kuszob=1.0))
        sz = F.elokeszit('# C\n\n## Heading %%literal\nParagraph.\n')
        self.assertEqual(sz[0].cim, 'Heading %%literal')

    def test_vedett_matek_link_es_escape_literal_nem_komment(self):
        md = '# C\n\n`%%code%%` $%%math%%$ [[A%%B|alias]] [label](A%%B) \\%%escaped\n'
        txt = F.ForrasSzoveg.jegyzetbol(md).szoveg
        for literal in ('`%%code%%`', '$%%math%%$', 'alias', 'label', '\\%%escaped'):
            with self.subTest(literal=literal):
                self.assertIn(literal, txt)

    def test_frontmatter_bom_crlf_unicode(self):
        md = '\ufeff---\r\nname: "%%YAML%%"\r\n---\r\n# Árvíz 😀 %%secret%%\r\n\r\nÉgő házak.\r\n'
        f = F.ForrasSzoveg.jegyzetbol(md)
        self.assertEqual((f.cim, f.szoveg), ('Árvíz 😀', 'Égő házak.'))

    def test_automatika_mondathalmazt_komment_only_edit_nem_valtoztat(self):
        alap = '# C\nVisible sentence.\n\n%% Hidden first sentence. %%\n'
        uj = alap.replace('Hidden first sentence.', 'Different hidden content.\n$$\n')
        self.assertEqual(automatika.mondatok(alap), frozenset({'visible sentence.'}))
        self.assertEqual(automatika.mondatok(uj), automatika.mondatok(alap))


class HorgonyKommentTest(unittest.TestCase):
    def test_hidden_szoegyezes_nincs_es_nincs_iras(self):
        md = 'Visible %%Unique Hidden Evidence%% ending.\n'
        self.assertIsNone(H.keres(md, 'Unique Hidden Evidence', min_fedes=1.0))
        uj, azon = H.horgonyoz(md, ['Unique Hidden Evidence'])
        self.assertEqual((uj.encode(), azon), (md.encode(), [None]))
        self.assertEqual(H.keres(md, 'Visible ending', min_fedes=1.0), (0, 0))

    def test_hidden_es_kodbeli_dollar_nem_nyit_matek_allapotot(self):
        for blokk in ('%% hidden\n$$\n%%\n', '```text\n$$\n```\n'):
            with self.subTest(blokk=blokk):
                md = 'First visible.\n' + blokk + 'Second visible paragraph.\n'
                self.assertEqual(H.keres(md, 'Second visible paragraph', min_fedes=1.0), (4, 4))

    def test_valodi_matek_tovabbra_nem_horgonyozhato(self):
        md = '$$\nUnique equation evidence\n$$\n\nVisible sentence.\n'
        self.assertIsNone(H.keres(md, 'Unique equation evidence', min_fedes=1.0))
        self.assertEqual(H.keres(md, 'Visible sentence', min_fedes=1.0), (4, 4))

    def test_zart_komment_utan_lathato_id_raw_crlf_bajtokkal(self):
        md = '\ufeff---\r\nx: 1\r\n---\r\n# C\r\n\r\nÁrvíz 😀 visible sentence. %%private%%\r\n'
        uj, azon = H.horgonyoz(md, ['Árvíz visible sentence'])
        self.assertIsNotNone(azon[0])
        self.assertEqual(uj.replace(f' ^{azon[0]}', '').encode(), md.encode())
        self.assertNotIn('\n', uj.replace('\r\n', ''))
        j = elemzo.elemez(uj.replace('\r\n', '\n'))
        self.assertIn(azon[0], [b['azon'] for b in j.blokkok])
        self.assertEqual(H.horgonyoz(uj, ['Árvíz visible sentence']), (uj, azon))

    def test_nyitott_kommentbe_nem_ir_es_rejtett_id_nem_reuse(self):
        for elotag in ('', '> ', '- '):
            for farok in ('%%unclosed secret', '%%unclosed secret ^hidden'):
                with self.subTest(elotag=elotag, farok=farok):
                    md = elotag + 'Visible sentence. ' + farok
                    self.assertEqual(H.keres(md, 'Visible sentence', min_fedes=1.0), (0, 0))
                    uj, azon = H.horgonyoz(md, ['Visible sentence', 'Visible sentence'])
                    self.assertEqual((uj.encode(), azon), (md.encode(), [None, None]))

    def test_meglevo_lathato_id_reuse(self):
        md = 'Visible sentence. %%secret%% ^sajat\n'
        self.assertEqual(H.horgonyoz(md, ['Visible sentence']), (md, ['sajat']))

    def test_rejtett_foglalt_id_nem_utkozik_az_ujjal(self):
        mondat = 'Visible sentence.'
        foglalt = 'm-' + hashlib.sha1(mondat.encode()).hexdigest()[:4]
        md = f'{mondat}\n\n%%\n^{foglalt}\n%%\n'
        uj, azon = H.horgonyoz(md, [mondat])
        self.assertIsNotNone(azon[0])
        self.assertNotEqual(azon[0], foglalt)
        self.assertEqual(uj.replace(f' ^{azon[0]}', ''), md)


class GepiFejezetKommentTest(unittest.TestCase):
    def test_lathato_cim_eredeti_range_crlf_unicode_es_noop(self):
        md = '\ufeff---\r\nx: 1\r\n---\r\n# C 😀\r\n## Gyakorlás %%private%%\r\nrégi 😀\r\n## Más\r\nmarad\r\n'
        for hova, vart in (
            ('eleje', md.replace('%%private%%\r\n', '%%private%%\r\núj\r\n')),
            ('vege', md.replace('régi 😀\r\n', 'régi 😀\r\núj\r\n')),
        ):
            with self.subTest(hova=hova):
                uj = szakasz_beszur(md, 'Gyakorlás', 'új', hova=hova, letrehoz=True)
                self.assertEqual(uj.encode(), vart.encode())
                self.assertIs(szakasz_beszur(uj, 'Gyakorlás', 'új', hova=hova), uj)

    def test_komment_fake_fence_es_fejlec_nem_cel_vagy_hatar(self):
        md = '# C\n%% hidden\n```\n## Gyakorlás\n%%\n## Gyakorlás %%private%%\nrégi\n%% hidden\n## Más\n%%\nmarad\n## Valódi\nx\n'
        vart = md.replace('marad\n## Valódi', 'marad\núj\n## Valódi')
        self.assertEqual(szakasz_beszur(md, 'Gyakorlás', 'új'), vart)

    def test_valodi_kod_fejlece_nem_cel_es_inline_kod_cim_megmarad(self):
        md = '```md\n## Gyakorlás\n```\n\n## `Gyakorlás` %%private%%\nrégi\n'
        self.assertEqual(szakasz_beszur(md, '`Gyakorlás`', 'új'), md + 'új\n')

    def test_lathato_cim_utkozes_409_es_szint_egyertelmusit(self):
        md = '## Gy %%a%%\nx\n## Gy %%b%%\ny\n'
        with self.assertRaises(HttpError) as cm:
            szakasz_beszur(md, 'Gy', 'új', letrehoz=True)
        self.assertEqual(cm.exception.code, 409)
        md = '# Gy %%a%%\nx\n## Gy %%b%%\ny\n'
        self.assertEqual(szakasz_beszur(md, '## Gy', 'új'), md + 'új\n')

    def test_nyitott_heading_literal_es_vegyes_sorveg_elutasitott(self):
        md = '## Gy %%literal\nrégi\n'
        self.assertEqual(szakasz_beszur(md, 'Gy %%literal', 'új'), md + 'új\n')
        with self.assertRaises(vaultio.Invalid):
            szakasz_beszur('## Gy %%private%%\r\nrégi\n', 'Gy', 'új')


if __name__ == '__main__':
    unittest.main()
