// A táblázat modellje (C09): beolvasás, igazított kimenet, a cella-, sor- és oszlopműveletek, a képletes és
// `\|` cellák, az idézetben álló táblázat; a kimenet a Markdown-elemzőn át ugyanazt a táblázatot adja.

import { EditorState } from '@codemirror/state';
import type { SyntaxNode } from '@lezer/common';
import { describe, expect, it } from 'vitest';
import { teljesFa } from './notion-segedek';
import { markdownNyelv } from '../src/szerkeszto/beallitas';
import {
  cellaForras,
  cellaIr,
  oszlopBeszur,
  oszlopDuplikal,
  oszlopIgazit,
  oszlopMozgat,
  oszlopSzam,
  oszlopTorol,
  sorBeszur,
  sorDuplikal,
  sorMozgat,
  sorTorol,
  szelesseg,
  szerializal,
  type Tabla,
  tablaNodebol,
  ujTabla,
} from '../src/szerkeszto/notion/tablazat/modell';

function beolvas(doc: string): { tabla: Tabla; from: number; to: number } {
  const s = EditorState.create({ doc, extensions: [markdownNyelv()] });
  let n: SyntaxNode | null = null;
  teljesFa(s).iterate({
    enter(x) {
      if (x.name === 'Table' && !n) n = x.node;
    },
  });
  const r = n && tablaNodebol(s, n);
  if (!r) throw new Error('nincs táblázat');
  return r;
}

const ki = (t: Tabla) => szerializal(t).join('\n');

describe('beolvasás és igazított kimenet', () => {
  it('a cellák, az igazítás és az előtag; a kimenet oszlopszélességre igazított', () => {
    const { tabla } = beolvas('| a | b |\n|---|:-:|\n| 1 | 22 |\n');
    expect(tabla.sorok).toEqual([['a', 'b'], ['1', '22']]);
    expect(tabla.igazitas).toEqual(['', 'kozep']);
    expect(ki(tabla)).toBe('| a   |  b  |\n| --- | :-: |\n| 1   | 22  |');
  });

  it('az igazítások: bal, jobb; a jobb igazítás balról kipárnáz', () => {
    const { tabla } = beolvas('| Név | Érték |\n|:--|--:|\n| alma | 5 |\n');
    expect(tabla.igazitas).toEqual(['bal', 'jobb']);
    expect(ki(tabla)).toBe('| Név  | Érték |\n| :--- | ----: |\n| alma |     5 |');
  });

  it('a szélesség: az ékezetes betű 1, a kombináló jel 0, a CJK 2', () => {
    expect(szelesseg('árvíztűrő')).toBe(9);
    expect(szelesseg('é')).toBe(1);
    expect(szelesseg('漢字')).toBe(4);
  });

  it('a már igazított kimenet újraolvasva ugyanaz a modell (körbejárás)', () => {
    const { tabla } = beolvas('| a | b | c |\n|:--|:-:|--:|\n| x | y | z |\n| 1 | 2 | 3 |\n');
    const szoveg = ki(tabla);
    expect(beolvas(szoveg + '\n').tabla).toEqual(tabla);
    expect(ki(beolvas(szoveg + '\n').tabla)).toBe(szoveg);
  });

  it('idézetben álló táblázat: az előtag minden sorban megmarad', () => {
    const { tabla, from } = beolvas('> [!note]\n> | a | b |\n> |---|---|\n> | 1 | 2 |\n');
    expect(tabla.elotag).toBe('> ');
    expect(from).toBe(10);
    expect(ki(sorBeszur(tabla, 2))).toBe('> | a   | b   |\n> | --- | --- |\n> | 1   | 2   |\n> |     |     |');
  });

  it('a képletben álló | nem cellahatár; a kimenet meghagyja', () => {
    const { tabla } = beolvas('| f | érték |\n|---|---|\n| $|A|$ | 3 |\n');
    expect(tabla.sorok[1]).toEqual(['$|A|$', '3']);
    expect(ki(tabla)).toBe('| f     | érték |\n| ----- | ----- |\n| $|A|$ | 3     |');
  });
});

describe('cella', () => {
  it('a képleten kívüli | → \\|, a képletben marad; sortörés → <br>', () => {
    expect(cellaForras('a|b')).toBe('a\\|b');
    expect(cellaForras('$|x|$ és a|b')).toBe('$|x|$ és a\\|b');
    expect(cellaForras('már \\| kész')).toBe('már \\| kész');
    expect(cellaForras('egy\nkettő')).toBe('egy<br>kettő');
    expect(cellaForras('  szóköz  ')).toBe('szóköz');
  });

  it('a cella átírása újraigazít, és a kimenet ugyanazt a táblázatot adja', () => {
    const { tabla } = beolvas('| a | b |\n|---|---|\n| 1 | 2 |\n');
    const t = cellaIr(tabla, 1, 0, 'hosszú szöveg|csővel');
    const hosszu = 'hosszú szöveg\\|csővel';
    expect(ki(t)).toBe(
      `| ${'a'.padEnd(hosszu.length)} | b   |\n| ${'-'.repeat(hosszu.length)} | --- |\n| ${hosszu} | 2   |`,
    );
    expect(beolvas(ki(t) + '\n').tabla).toEqual(t);
  });
});

describe('listába és idézetbe ágyazott táblázat: az első sor előtagja csak az első sor előtt áll (T124)', () => {
  /** [az első sor előtagja, a többi sor előtagja] */
  const ELOTAGOK: [string, string][] = [
    ['- ', '  '],
    ['* ', '  '],
    ['+ ', '  '],
    ['1. ', '   '],
    ['1) ', '   '],
    ['> ', '> '],
    ['> - ', '>   '],
  ];

  it('listajelölős táblázat: a cella átírása táblázatot ad, nem három listaelemet', () => {
    const { tabla } = beolvas('- | a | b |\n  |---|---|\n  | 1 | 2 |\n');
    expect(tabla.elotag).toBe('- ');
    expect(tabla.folytatas).toBe('  ');
    expect(ki(cellaIr(tabla, 1, 0, 'x'))).toBe('- | a   | b   |\n  | --- | --- |\n  | x   | 2   |');
  });

  it('minden előtagnál: a beolvasás–kiírás körút bájtra azonos, és az átírt táblázat ugyanaz a táblázat marad', () => {
    for (const [elso, tobbi] of ELOTAGOK) {
      const forras = `${elso}| a   | b   |\n${tobbi}| --- | --- |\n${tobbi}| 1   | 2   |`;
      const { tabla } = beolvas(forras + '\n');
      expect([tabla.elotag, tabla.folytatas], elso).toEqual([elso, tobbi]);
      expect(ki(tabla), `${elso}: körút`).toBe(forras);
      const uj = ki(cellaIr(tabla, 1, 1, 'xy'));
      expect(uj, `${elso}: átírás`).toBe(`${elso}| a   | b   |\n${tobbi}| --- | --- |\n${tobbi}| 1   | xy  |`);
      const ujra = beolvas(uj + '\n').tabla;
      expect(ujra.sorok, elso).toEqual([['a', 'b'], ['1', 'xy']]);
      expect([ujra.elotag, ujra.folytatas], elso).toEqual([elso, tobbi]);
    }
  });

  it('a sorműveletek és az új sor is a folytatás-előtagot viszik', () => {
    const { tabla } = beolvas('- | a | b |\n  |---|---|\n  | 1 | 2 |\n');
    expect(ki(sorBeszur(tabla, 2))).toBe('- | a   | b   |\n  | --- | --- |\n  | 1   | 2   |\n  |     |     |');
    expect(ki(sorDuplikal(tabla, 1))).toBe('- | a   | b   |\n  | --- | --- |\n  | 1   | 2   |\n  | 1   | 2   |');
    expect(ki(oszlopBeszur(tabla, 2))).toBe('- | a   | b   | Oszlop 3 |\n  | --- | --- | -------- |\n  | 1   | 2   |          |');
  });
});

describe('a fejlécnél hosszabb sor extra cellái megmaradnak (T124)', () => {
  const FORRAS = '| a | b |\n|---|---|\n| 1 | 2 | 3 |\n| 4 | 5 |\n';

  it('a beolvasás megtartja az extra cellát, a rövid sort párnázza', () => {
    const { tabla } = beolvas(FORRAS);
    expect(tabla.sorok).toEqual([['a', 'b'], ['1', '2', '3'], ['4', '5']]);
    expect(tabla.igazitas).toEqual(['', '']);
    expect(beolvas('| a | b |\n|---|---|\n| 1 |\n').tabla.sorok).toEqual([['a', 'b'], ['1', '']]);
  });

  it('egy másik cella átírása nem törli a fejlécen túli cellát; az extra cella nyersen a sor végére íródik', () => {
    const { tabla } = beolvas(FORRAS);
    expect(ki(cellaIr(tabla, 2, 0, 'x'))).toBe('| a   | b   |\n| --- | --- |\n| 1   | 2   | 3 |\n| x   | 5   |');
    expect(ki(cellaIr(tabla, 1, 0, 'y'))).toBe('| a   | b   |\n| --- | --- |\n| y   | 2   | 3 |\n| 4   | 5   |');
  });

  it('a sorműveletek természetesen viszik az extra cellát; az oszlopműveletek az új oszlopszám mögött hagyják', () => {
    const { tabla } = beolvas(FORRAS);
    expect(ki(sorMozgat(tabla, 1, 3))).toBe('| a   | b   |\n| --- | --- |\n| 4   | 5   |\n| 1   | 2   | 3 |');
    expect(ki(sorDuplikal(tabla, 1))).toBe('| a   | b   |\n| --- | --- |\n| 1   | 2   | 3 |\n| 1   | 2   | 3 |\n| 4   | 5   |');
    expect(ki(sorTorol(tabla, 2))).toBe('| a   | b   |\n| --- | --- |\n| 1   | 2   | 3 |');
    expect(oszlopSzam(tabla)).toBe(2);
    expect(oszlopBeszur(tabla, 1).sorok[1]).toEqual(['1', '', '2', '3']);
    expect(oszlopSzam(oszlopBeszur(tabla, 1))).toBe(3);
    expect(oszlopTorol(tabla, 0).sorok[1]).toEqual(['2', '3']);
    expect(oszlopSzam(oszlopTorol(tabla, 0))).toBe(1);
    expect(oszlopMozgat(tabla, 0, 2).sorok[1]).toEqual(['2', '1', '3']);
    expect(oszlopDuplikal(tabla, 0).sorok[1]).toEqual(['1', '1', '2', '3']);
  });

  it('a kimenet újraolvasva ugyanaz a táblázat (körút)', () => {
    const { tabla } = beolvas(FORRAS);
    const t = cellaIr(tabla, 2, 0, 'x');
    expect(beolvas(ki(t) + '\n').tabla.sorok).toEqual(t.sorok);
  });
});

describe('sor- és oszlopműveletek', () => {
  const alap = () => beolvas('| a | b |\n|---|---|\n| 1 | 2 |\n| 3 | 4 |\n').tabla;

  it('sor beszúrása, törlése, duplikálása; a fejléc nem törölhető és elé nem szúrható', () => {
    expect(sorBeszur(alap(), 1).sorok).toEqual([['a', 'b'], ['', ''], ['1', '2'], ['3', '4']]);
    expect(sorBeszur(alap(), 99).sorok.at(-1)).toEqual(['', '']);
    expect(sorBeszur(alap(), 0).sorok[1]).toEqual(['', '']);
    expect(sorTorol(alap(), 1).sorok).toEqual([['a', 'b'], ['3', '4']]);
    expect(sorTorol(alap(), 0)).toEqual(alap());
    expect(sorDuplikal(alap(), 1).sorok).toEqual([['a', 'b'], ['1', '2'], ['1', '2'], ['3', '4']]);
  });

  it('sor áthelyezése', () => {
    expect(sorMozgat(alap(), 1, 3).sorok.map((s) => s[0])).toEqual(['a', '3', '1']);
    expect(sorMozgat(alap(), 2, 1).sorok.map((s) => s[0])).toEqual(['a', '3', '1']);
    expect(sorMozgat(alap(), 1, 2)).toEqual(alap());
  });

  it('oszlop beszúrása (új fejléc), törlése (az utolsó nem), duplikálása, áthelyezése, igazítása', () => {
    const t = oszlopBeszur(alap(), 2);
    expect(t.sorok).toEqual([['a', 'b', 'Oszlop 3'], ['1', '2', ''], ['3', '4', '']]);
    expect(oszlopBeszur(alap(), 0).sorok[0]).toEqual(['Oszlop 3', 'a', 'b']);
    expect(oszlopTorol(alap(), 0).sorok).toEqual([['b'], ['2'], ['4']]);
    expect(oszlopTorol(oszlopTorol(alap(), 0), 0).sorok).toEqual([['b'], ['2'], ['4']]);
    expect(oszlopDuplikal(alap(), 0).sorok[1]).toEqual(['1', '1', '2']);
    const m = oszlopIgazit(oszlopMozgat(oszlopIgazit(alap(), 0, 'jobb'), 0, 2), 0, 'kozep');
    expect(m.sorok[1]).toEqual(['2', '1']);
    expect(m.igazitas).toEqual(['kozep', 'jobb']);
  });

  it('az új táblázat és minden művelet eredménye érvényes, ugyanazt adó táblázat', () => {
    let t = ujTabla(3, 2);
    expect(ki(t)).toBe(
      '| Oszlop 1 | Oszlop 2 | Oszlop 3 |\n| -------- | -------- | -------- |\n|          |          |          |\n|          |          |          |',
    );
    for (const f of [(x: Tabla) => oszlopBeszur(x, 1), (x: Tabla) => sorDuplikal(x, 1), (x: Tabla) => oszlopIgazit(x, 0, 'jobb'), (x: Tabla) => cellaIr(x, 1, 1, 'a|b')]) {
      t = f(t);
      expect(beolvas(ki(t) + '\n').tabla.sorok).toEqual(t.sorok);
      expect(beolvas(ki(t) + '\n').tabla.igazitas).toEqual(t.igazitas);
    }
  });
});

describe('üres cellák (a Lezer nem ad nekik csomópontot)', () => {
  it('a modell és az olvasó is a helyükön tartja az üres cellákat', async () => {
    const forras = '| a |  | c |\n|---|---|---|\n|  | y |  |\n';
    expect(beolvas(forras).tabla.sorok).toEqual([['a', '', 'c'], ['', 'y', '']]);
    const { obsidianElemzo } = await import('../src/szerkeszto/markdown/elemzo');
    const { dokumentumRenderel } = await import('../src/szerkeszto/olvaso/html');
    const { LustaRajzolo } = await import('../src/szerkeszto/olvaso/lusta');
    const d = document.createElement('div');
    d.appendChild(dokumentumRenderel(obsidianElemzo.parse(forras), { olvas: (a, b) => forras.slice(a, b), ut: null, lusta: LustaRajzolo.azonnali(), elotag: 'p' }));
    const sorok = [...d.querySelectorAll('tr')].map((tr) => [...tr.children].map((c) => c.textContent));
    expect(sorok).toEqual([['a', '', 'c'], ['', 'y', '']]);
  });
});
