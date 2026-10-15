// A `/` menü sablonjai és beszúrása (C09): a környezet felismerése (üres sor, üres listaelem, idézet belseje,
// szöveg mellett, egyéb), minden elem pontos kimenete, a kurzor és a hibátlan Markdown.

import type { EditorSelection } from '@codemirror/state';
import { describe, expect, it } from 'vitest';
import { perjelBeszur, perjelKornyezet, sablonElemek } from '../src/szerkeszto/notion/sablonok';
import { allapot, hibatlan, szerkezet } from './notion-segedek';

const MA = new Date(2026, 9, 1, 12); // 2026-10-01

/** A `|` jelöli a `/szűrő` végét (a kurzort); az `elem` azonosítója a választott elem. */
function beszur(doc: string, elem: string): { szoveg: string; kurzor: EditorSelection['main'] } | null {
  const veg = doc.indexOf('|');
  const forras = doc.replace('|', '');
  const s = allapot(forras);
  const from = forras.lastIndexOf('/', veg);
  const e = sablonElemek().find((x) => x.id === elem)!;
  const r = perjelBeszur(s, from, veg, e, MA);
  if (!r) return null;
  const uj = s.update({ changes: r.changes, selection: r.selection }).state;
  return { szoveg: uj.doc.toString(), kurzor: uj.selection.main };
}

const ki = (doc: string, elem: string) => beszur(doc, elem)?.szoveg ?? null;

describe('környezet', () => {
  const k = (doc: string) => {
    const veg = doc.indexOf('|');
    const forras = doc.replace('|', '');
    return perjelKornyezet(allapot(forras), forras.lastIndexOf('/', veg), veg).kontextus;
  };

  it('üres sor, üres listaelem, idézet belseje, szöveg mellett, egyéb', () => {
    expect(k('Elöl\n\n/h|\n\nHátul')).toBe('doc-ures');
    expect(k('/|')).toBe('doc-ures');
    expect(k('- /|')).toBe('lista-ures');
    expect(k('- a\n\t1. /ta|')).toBe('lista-ures');
    expect(k('> /|')).toBe('idezet-ures');
    expect(k('> [!note]\n> /ko|')).toBe('idezet-ures');
    expect(k('Szöveg /|')).toBe('szoveg');
    expect(k('/|szöveg'.replace('|', ''))).toBe('szoveg');
    expect(k('Sor egy\n/|')).toBe('szoveg'); // többsoros bekezdés része
    expect(k('- elem /|')).toBe('egyeb');
    expect(k('> szöveg /|')).toBe('egyeb');
  });
});

describe('blokkok üres sorra', () => {
  it('fejezet, idézet, lista, számozott, feladat', () => {
    expect(ki('/h|', 'h2')).toBe('## ');
    expect(ki('A\n\n/|\n\nB', 'h1')).toBe('A\n\n# \n\nB');
    expect(ki('/|', 'idezet')).toBe('> ');
    expect(ki('/|', 'lista')).toBe('- ');
    expect(ki('/|', 'szamozott')).toBe('1. ');
    expect(ki('/|', 'feladat')).toBe('- [ ] ');
  });

  it('callout típusonként és összecsukható; a kurzor a törzsben, illetve a cím kijelölve', () => {
    expect(ki('/|', 'callout-warning')).toBe('> [!warning]\n> ');
    expect(ki('/|', 'callout-note')).toBe('> [!note]\n> ');
    const r = beszur('/|', 'toggle')!;
    expect(r.szoveg).toBe('> [!note]- Cím\n> ');
    expect(r.szoveg.slice(r.kurzor.from, r.kurzor.to)).toBe('Cím');
    const c = beszur('/|', 'callout-tip')!;
    expect(c.kurzor.head).toBe(c.szoveg.length);
  });

  it('kód, matek, Mermaid, Bases, elválasztó, táblázat', () => {
    expect(ki('/|', 'kod')).toBe('```\n\n```');
    expect(beszur('/|', 'kod')!.kurzor.head).toBe(4);
    expect(ki('/|', 'matek')).toBe('$$\n\n$$');
    expect(ki('/|', 'mermaid')).toBe('```mermaid\ngraph TD\n  A --> B\n```');
    expect(ki('/|', 'base')).toBe('```base\nviews:\n  - type: table\n    name: Táblázat\n```');
    const t = ki('/|', 'tablazat')!;
    expect(t).toBe(
      '| Oszlop 1 | Oszlop 2 | Oszlop 3 |\n| -------- | -------- | -------- |\n|          |          |          |\n|          |          |          |',
    );
  });

  it('az elválasztó után üres sorra áll a kurzor (nem lesz belőle felirat)', () => {
    const r = beszur('A\n\n/|\n\nB', 'elvalaszto')!;
    expect(r.szoveg).toBe('A\n\n---\n\nB');
    expect(r.szoveg.slice(0, r.kurzor.head)).toBe('A\n\n---\n');
    const v = beszur('A\n\n/|', 'elvalaszto')!;
    expect(v.szoveg).toBe('A\n\n---\n');
  });

  it('a táblázat jelzi, hol kezdődik (a fókuszhoz)', () => {
    const forras = 'A\n\n/|\n';
    const veg = forras.indexOf('|');
    const s = allapot(forras.replace('|', ''));
    const e = sablonElemek().find((x) => x.id === 'tablazat')!;
    expect(perjelBeszur(s, 3, veg, e, MA)!.tabla).toBe(2);
  });
});

describe('környezetfüggő beírás', () => {
  it('üres listaelem: a jelölő cserélődik', () => {
    expect(ki('- /|', 'szamozott')).toBe('1. ');
    expect(ki('- a\n\t- /|', 'feladat')).toBe('- a\n\t- [ ] ');
    expect(ki('1. /|', 'lista')).toBe('- ');
    expect(ki('- /|', 'h1')).toBeNull(); // listaelemben fejezet nem választható
  });

  it('idézet belsejében minden sor megkapja az előtagot', () => {
    expect(ki('> /|', 'kod')).toBe('> ```\n> \n> ```'.replace('> \n', '>\n'));
    // a callout fejléce és a táblázat között előtagos üres sor áll (különben az elválasztó sor a fejléc setext-aláhúzása lenne)
    const t = ki('> [!tip]\n> /|', 'tablazat')!.split('\n');
    expect(t[1]).toBe('>');
    expect(t.slice(2).every((s) => s.startsWith('> |'))).toBe(true);
    expect(ki('> /|', 'callout-info')).toBe('> > [!info]\n> > ');
  });

  it('szöveg mellett: a `/szűrő` törlődik, a blokk üres sorral a bekezdés mögé kerül', () => {
    expect(ki('Szöveg /h|\n\nVége', 'h2')).toBe('Szöveg\n\n## \n\nVége');
    expect(ki('Szöveg /k|', 'kod')).toBe('Szöveg\n\n```\n\n```');
    expect(ki('# Cím /e|', 'elvalaszto')).toBe('# Cím\n\n---\n');
  });

  it('listaelemben vagy idézetben álló szöveg mellett blokk nem választható', () => {
    expect(ki('- elem /|', 'kod')).toBeNull();
    expect(ki('> szöveg /|', 'h1')).toBeNull();
  });
});

// C29.7b (a T034 maradéka): a `/` sor alatt közvetlenül álló táblázatot (a `/` alatti sor táblázatsor, a bekezdést a táblázat
// megszakítja, így a környezet `doc-ures`) az új blokk nem nyelheti el — a táblázat-sablon sorai a meglévő táblázat fejlécét
// sorként olvasnák magukba.
describe('`/` közvetlenül egy meglévő táblázat fölött', () => {
  const TABLA = '| a | b |\n|---|---|\n| 1 | 2 |';
  const blokkElemek = sablonElemek().filter((e) => !e.sablon(MA).beszurt);

  it('minden blokkelem után a meglévő táblázat ép és külön marad (3 sora, nem kerül a sablon alá)', () => {
    let kiprobalt = 0;
    for (const e of blokkElemek) {
      const r = beszur('/|\n' + TABLA, e.id);
      if (!r) continue;
      kiprobalt++;
      const sz = szerkezet(r.szoveg);
      const cimke = `${e.id}: ${JSON.stringify(r.szoveg)}`;
      expect(sz.setext, cimke).toBe(0);
      expect(sz.db.Table, `${cimke} — a táblázatok száma`).toBe(e.id === 'tablazat' ? 2 : 1);
      expect(r.szoveg.endsWith(TABLA), `${cimke} — a meglévő táblázat sorai a végén, érintetlenül`).toBe(true);
      if (e.id !== 'tablazat') expect([sz.db.TableHeader, sz.db.TableRow], cimke).toEqual([1, 1]);
    }
    expect(kiprobalt).toBeGreaterThan(15);
  });

  it('pontos kimenet: üres sor a sablon és a táblázat között; az elválasztó saját üres sora nem duplázódik', () => {
    expect(ki('/|\n' + TABLA, 'kod')).toBe('```\n\n```\n\n' + TABLA);
    expect(ki('A\n\n/|\n' + TABLA, 'h2')).toBe('A\n\n## \n\n' + TABLA);
    expect(ki('/|\n' + TABLA, 'elvalaszto')).toBe('---\n\n' + TABLA);
  });

  it('az üres sorral már elválasztott táblázat mellé nem kerül újabb üres sor', () => {
    expect(ki('/|\n\n' + TABLA, 'kod')).toBe('```\n\n```\n\n' + TABLA);
  });
});

// T034: a beszúrás nem olvaszthatja össze a szomszédos sorokat — idézetben előtagos üres sor áll a sablon előtt/után,
// szöveg mellett csak a `/szűrő` tűnik el, üres listaelemben a meglévő jelölő marad.
describe('kontextus × elem: nincs összeolvadás', () => {
  /** Az elem sablonja nem soron belüli (a `beszurt` elemek külön úton mennek). */
  const blokkElemek = sablonElemek().filter((e) => !e.sablon(MA).beszurt);

  interface Kontextus {
    nev: string;
    doc: string;
    /** a `/` során kívüli nem üres sorok: sorrendben, szó szerint megmaradnak */
    marad: string[];
    /** callout-kontextus: a külső idézet callout marad */
    callout: boolean;
  }
  const IDEZET: Kontextus[] = [
    { nev: 'idézet, fölötte nem üres sor', doc: '> Alfa\n> /|', marad: ['> Alfa'], callout: false },
    { nev: 'callout fejléc címmel', doc: '> [!note] T\n> /|', marad: ['> [!note] T'], callout: true },
    { nev: 'idézet, alatta nem üres sor', doc: '> /|\n> Béta', marad: ['> Béta'], callout: false },
    { nev: 'callout fejléc és törzs között', doc: '> [!note]\n> /|\n> törzs', marad: ['> [!note]', '> törzs'], callout: true },
  ];

  for (const k of IDEZET) {
    it(`${k.nev}: minden blokkelem után egy idézet marad, nincs setext, a szomszéd sor ép`, () => {
      let kiprobalt = 0;
      for (const e of blokkElemek) {
        const r = beszur(k.doc, e.id);
        if (!r) continue;
        kiprobalt++;
        const sz = szerkezet(r.szoveg);
        const cimke = `${e.id}: ${JSON.stringify(r.szoveg)}`;
        expect(sz.setext, cimke).toBe(0);
        expect(sz.felso, cimke).toEqual(['Blockquote']);
        if (k.callout) expect(sz.callout >= 1, `${cimke} — a külső idézet callout marad`).toBe(true);
        // a nem a `/` sorából való sorok szó szerint megmaradnak, sorrendben
        const sorok = r.szoveg.split('\n');
        let p = 0;
        for (const m of k.marad) {
          p = sorok.indexOf(m, p);
          expect(p, `${cimke} — hiányzó sor: ${m}`).toBeGreaterThanOrEqual(0);
          p++;
        }
        if (e.id === 'tablazat') {
          expect([sz.tabla, sz.db.TableHeader, sz.db.TableRow], `${cimke} — a táblázat 3 sorú, nem nyel el szomszédot`).toEqual([1, 1, 2]);
        }
      }
      expect(kiprobalt).toBeGreaterThan(15);
    });
  }

  it('pontos kimenetek: üres `>` sor a sablon előtt és után; az elválasztó után a kurzor `>` előtagú üres sorra áll', () => {
    expect(ki('> Alfa\n> /|', 'elvalaszto')).toBe('> Alfa\n>\n> ---\n> ');
    expect(ki('> Alfa\n> /|', 'kod')).toBe('> Alfa\n>\n> ```\n>\n> ```');
    expect(ki('> /|\n> Béta', 'tablazat')!.split('\n').slice(-2)).toEqual(['>', '> Béta']);
    expect(ki('> /|\n> Béta', 'elvalaszto')).toBe('> ---\n> \n> Béta');
    expect(ki('> [!note]\n> /|\n> törzs', 'kod')).toBe('> [!note]\n>\n> ```\n>\n> ```\n>\n> törzs');
    expect(ki('> [!note]\n> /|\n> törzs', 'idezet')).toBe('> [!note]\n>\n> > \n>\n> törzs');
    const r = beszur('> [!note]\n> /|\n> törzs', 'kod')!;
    expect(r.szoveg.slice(0, r.kurzor.head).split('\n').length - 1).toBe(3); // a kerítés belső sora
  });

  it('a már előtagos üres sorral elválasztott szomszéd mellé nem kerül újabb üres sor', () => {
    expect(ki('> Alfa\n>\n> /|', 'kod')).toBe('> Alfa\n>\n> ```\n>\n> ```');
    expect(ki('> /|\n>\n> Béta', 'kod')).toBe('> ```\n>\n> ```\n>\n> Béta');
    expect(ki('> Alfa\n> /|\n>\n> Béta', 'elvalaszto')).toBe('> Alfa\n>\n> ---\n>\n> Béta');
  });

  it('beágyazott idézetben az előtag a teljes `> > `', () => {
    expect(ki('> > Alfa\n> > /|', 'kod')).toBe('> > Alfa\n> >\n> > ```\n> >\n> > ```');
  });

  it('szöveg mellett: a többsoros bekezdés egyben marad, a sorából csak a `/szűrő` tűnik el', () => {
    expect(ki('a\n/|\nc', 'kod')).toBe('a\nc\n\n```\n\n```');
    expect(ki('a\nb\n/|', 'h2')).toBe('a\nb\n\n## ');
    expect(ki('/|\nc', 'idezet')).toBe('c\n\n> ');
    for (const e of blokkElemek) {
      const r = beszur('a\n/|\nc', e.id);
      if (!r) continue;
      expect(r.szoveg.startsWith('a\nc\n\n'), `${e.id}: ${JSON.stringify(r.szoveg)}`).toBe(true);
      expect(szerkezet(r.szoveg).felso[0], e.id).toBe('Paragraph');
    }
  });

  it('szöveg mellett a sor végi szóköz és a `/szűrő` utáni szöveg megmarad (csak a `/` előtti egy szóköz esik ki, ha nincs mögötte semmi)', () => {
    expect(ki('Szöveg  /h|\n\nVége', 'h2')).toBe('Szöveg \n\n## \n\nVége');
    expect(ki('Szöveg /h| tovább', 'h2')).toBe('Szöveg  tovább\n\n## ');
    expect(ki('Szöveg /h|', 'h2')).toBe('Szöveg\n\n## ');
  });

  it('üres listaelem: azonos típusnál a meglévő jelölő, a sorszám és a szóköz marad', () => {
    expect(ki('* a\n* /|', 'lista')).toBe('* a\n* ');
    expect(ki('+ a\n\t+ /|', 'lista')).toBe('+ a\n\t+ ');
    expect(ki('1) a\n2) /|', 'szamozott')).toBe('1) a\n2) ');
    expect(ki('1. a\n2. /|', 'szamozott')).toBe('1. a\n2. ');
    expect(ki('3. /|', 'szamozott')).toBe('3. ');
    expect(ki('-   /|', 'lista')).toBe('-   ');
  });

  it('üres listaelem: a feladat bármely jelölőn csak a `[ ] `-t fűzi hozzá; típusváltásnál `-` / `1.`', () => {
    expect(ki('* a\n* /|', 'feladat')).toBe('* a\n* [ ] ');
    expect(ki('1) a\n2) /|', 'feladat')).toBe('1) a\n2) [ ] ');
    expect(ki('3. /|', 'feladat')).toBe('3. [ ] ');
    expect(ki('- [x] /|', 'feladat')).toBe('- [ ] ');
    expect(ki('* a\n* /|', 'szamozott')).toBe('* a\n1. ');
    expect(ki('1) a\n2) /|', 'lista')).toBe('1) a\n- ');
    expect(ki('- [ ] /|', 'lista')).toBe('- ');
  });

  it('minden listaelem-kontextus × lista-elem: a lista és a szomszéd elem szövege megmarad, hibátlan elemzés', () => {
    for (const doc of ['* a\n* /|', '1) a\n2) /|', '- a\n\t- /|', '3. a\n4. /|']) {
      for (const id of ['lista', 'szamozott', 'feladat']) {
        const szoveg = ki(doc, id)!;
        expect(hibatlan(szoveg), `${id}: ${JSON.stringify(szoveg)}`).toBe(true);
        expect(szoveg.split('\n')[0], `${id}: ${JSON.stringify(szoveg)}`).toBe(doc.split('\n')[0]);
      }
    }
  });
});

describe('soron belüli elemek', () => {
  it('beágyazás: a kurzor a `![[` és `]]` között, bármely sorban', () => {
    const r = beszur('Lásd /be|', 'beagyazas')!;
    expect(r.szoveg).toBe('Lásd ![[]]');
    expect(r.kurzor.head).toBe(r.szoveg.indexOf(']]'));
    expect(ki('- elem /be|', 'beagyazas')).toBe('- elem ![[]]');
    expect(ki('> sor /be|', 'beagyazas')).toBe('> sor ![[]]');
  });

  it('dátum: ma, holnap, tegnap, ÉÉÉÉ-HH-NN', () => {
    expect(ki('Határidő: /d|', 'datum-ma')).toBe('Határidő: 2026-10-01');
    expect(ki('/d|', 'datum-holnap')).toBe('2026-10-02');
    expect(ki('/d|', 'datum-tegnap')).toBe('2026-09-30');
    expect(ki('- /d| és még', 'datum-ma')).toBe('- 2026-10-01 és még');
  });
});

describe('a „Sablon…” elem (C32b)', () => {
  it('csak a `/szűrő` törlődik, a szöveg többi része és a kurzor a helyén; a művelet a sablon-választó', () => {
    const e = sablonElemek().find((x) => x.id === 'sablon-valaszto')!;
    expect(e.muvelet).toBe('sablon-valaszto');
    const r = beszur('Elöl /sab| hátul', 'sablon-valaszto')!;
    expect(r.szoveg).toBe('Elöl  hátul');
    expect(r.kurzor.head).toBe(5);
    expect(beszur('/sab|', 'sablon-valaszto')!.szoveg).toBe('');
    expect(beszur('- /sab|', 'sablon-valaszto')!.szoveg).toBe('- ');
  });
});

describe('a menü elemei', () => {
  it('a callout-típusok a regiszterből jönnek, mindegyik érvényes; minden kimenet hibátlanul elemződik', () => {
    const elemek = sablonElemek();
    expect(elemek.filter((e) => e.id.startsWith('callout-')).length).toBeGreaterThanOrEqual(13);
    expect(new Set(elemek.map((e) => e.id)).size).toBe(elemek.length);
    for (const e of elemek) {
      const r = beszur('A\n\n/|\n\nB', e.id);
      if (!r) continue;
      expect(hibatlan(r.szoveg), e.id).toBe(true);
    }
  });
});
