// A valódi KaTeX-képlethiba a jobb panelen (C30b-mag): a képletek kiszedése a szintaxisfából, a valódi renderelő hibája
// (amit a core szerkezeti próbája nem lát), az időkeretes, megszakítható ellenőrzés és az összevonás a core tételeivel.

import { ensureSyntaxTree } from '@codemirror/language';
import { EditorState } from '@codemirror/state';
import { describe, expect, it } from 'vitest';
import type { HigieniaTetel } from '../src/lib/asszisztens/tipusok';
import { kepletekEllenoriz, kepletekKiszed, kepletHiba, kepletTarUrit } from '../src/szerkeszto/asszisztens/keplet';
import { KLIENS_ELOTAG, osszevon } from '../src/szerkeszto/asszisztens/kepletHibak.svelte';
import { markdownNyelv } from '../src/szerkeszto/beallitas';

function kiszed(doc: string) {
  const s = EditorState.create({ doc, extensions: [markdownNyelv()] });
  const fa = ensureSyntaxTree(s, s.doc.length, 5000)!;
  return kepletekKiszed(fa, s.doc);
}

describe('képletek kiszedése', () => {
  it('soron belüli, megjelenítési és blokk-képlet, sorszámmal; a kódban álló nem képlet', () => {
    const doc = ['Az $a+b$ és $$c^2$$ itt.', '', '$$', '\\frac{1}{2}', '$$', '', '```', '$kod$', '```', '', '`$x$`'].join('\n');
    expect(kiszed(doc)).toEqual([
      { tex: 'a+b', display: false, sor: 1 },
      { tex: 'c^2', display: true, sor: 1 },
      { tex: '\\frac{1}{2}', display: true, sor: 3 },
    ]);
  });

  it('a lezáratlan és az üres képlet kimarad', () => {
    expect(kiszed('Ár: $5 és még $ szöveg')).toEqual([]);
  });
});

describe('a valódi KaTeX hibája', () => {
  it('a szerkezetileg ép, de a KaTeX-nek érthetetlen képlet hibás; az ép nem', () => {
    kepletTarUrit();
    // a core szerkezeti próbája (zárójelpár, begin/end) ezt átengedi
    expect(kepletHiba('\\foo{x}', false)).toMatch(/undefined control sequence/i);
    expect(kepletHiba('\\frac{1}{2}', false)).toBeNull();
    expect(kepletHiba('\\left{1\\right}', true)).not.toBeNull();
  });

  it('a vault MathJax-tűrő esetei (zárójel nélküli operátor-index) nem hibák', () => {
    expect(kepletHiba('K_\\max = 840', false)).toBeNull();
  });

  it('az eredmény gyorsítótárazott, és az üzenet rövid, egysoros', () => {
    const a = kepletHiba('\\bar{', false);
    expect(a).toBe(kepletHiba('\\bar{', false));
    expect(a!.length).toBeLessThanOrEqual(160);
    expect(a).not.toMatch(/\n/);
  });
});

describe('az ellenőrzés időkeretes és megszakítható', () => {
  const sok = (n: number) => Array.from({ length: n }, (_, i) => ({ tex: i % 10 === 0 ? `\\foo${i}{x}` : `x_${i}^2 + y`, display: false, sor: i + 1 }));

  it('hibás képleteket sorral ad vissza', async () => {
    kepletTarUrit();
    const hibak = await kepletekEllenoriz(sok(30));
    expect(hibak!.map((h) => h.sor)).toEqual([1, 11, 21]);
  });

  it('nagy listánál a szeletek közt átadja a vezérlést (a főszál nem blokkolódik végig)', async () => {
    kepletTarUrit();
    let atadasok = 0;
    await kepletekEllenoriz(sok(600), { szeletMs: 1, atad: async () => void atadasok++ });
    expect(atadasok).toBeGreaterThan(2);
  });

  it('megszakítva nincs eredmény, és a további képleteket nem számolja', async () => {
    kepletTarUrit();
    let atadasok = 0;
    const ki = await kepletekEllenoriz(sok(600), {
      szeletMs: 1,
      atad: async () => void atadasok++,
      megszakit: () => atadasok >= 1,
    });
    expect(ki).toBeNull();
    expect(atadasok).toBe(1);
  });

  it('5000 soros jegyzet képletei: egy szelet nem tart a keretnél hosszabb ideig (mért költség)', async () => {
    kepletTarUrit();
    const sorok: string[] = [];
    for (let i = 0; i < 5000; i++) sorok.push(i % 8 === 0 ? `Az $x_{${i}}^2 + \\frac{a}{b}$ képlet.` : `Sima sor ${i}.`);
    const t0 = performance.now();
    const lista = kiszed(sorok.join('\n'));
    const kiszedesMs = performance.now() - t0;
    const szeletek: number[] = [];
    let utolso = performance.now();
    await kepletekEllenoriz(lista, {
      szeletMs: 12,
      atad: async () => {
        const most = performance.now();
        szeletek.push(most - utolso);
        await new Promise<void>((ok) => setTimeout(ok, 0));
        utolso = performance.now();
      },
    });
    const leghosszabb = Math.max(0, ...szeletek);
    console.info(`[C30b-mag] 5000 sor, ${lista.length} képlet: kiszedés ${kiszedesMs.toFixed(1)} ms, leghosszabb szelet ${leghosszabb.toFixed(1)} ms (${szeletek.length} szelet)`);
    expect(lista.length).toBe(625);
    // egy szelet a 12 ms-os keret + egy képlet költsége; terhelt gépen bőven alatta marad az 50 ms-nak
    expect(leghosszabb).toBeLessThan(50);
  });
});

describe('az összevonás a core tételeivel', () => {
  const core = (sor: number | null, fajta: HigieniaTetel['fajta'] = 'hibas_keplet'): HigieniaTetel => ({
    azonosito: `${fajta}:${sor}`, fajta, szint: 'hiba', ut: 'A.md', sor, uzenet: `core ${fajta} ${sor}`,
  });
  const kliens = (sor: number): HigieniaTetel => ({
    azonosito: `${KLIENS_ELOTAG}A.md:${sor}:0`, fajta: 'hibas_keplet', szint: 'hiba', ut: 'A.md', sor, uzenet: 'A KaTeX nem tudja megjeleníteni: x',
  });

  it('az azonos sorú core-beli hibás képlet helyére a valódi KaTeX-üzenet kerül; a többi marad, sor szerint', () => {
    const ki = osszevon([core(9), core(3, 'torott_link'), core(5)], [kliens(5), kliens(2)]);
    expect(ki.map((t) => [t.sor, t.azonosito.startsWith(KLIENS_ELOTAG)])).toEqual([
      [2, true],
      [3, false],
      [5, true],
      [9, false],
    ]);
  });

  it('kliens-tétel nélkül a core listája változatlan; a sor nélküli tétel a végére kerül', () => {
    const t = [core(null, 'arva_jegyzet'), core(4, 'torott_link')];
    expect(osszevon(t, [])).toEqual(t);
    expect(osszevon(t, [kliens(1)]).map((x) => x.sor)).toEqual([1, 4, null]);
  });

  it('a kliens-tétel azonosítója nem ütközhet a core-ével (nincs a riportban / a statisztikában)', () => {
    expect(KLIENS_ELOTAG).toBe('kliens-keplet:');
    expect(kliens(1).azonosito.startsWith('hibas_keplet:')).toBe(false);
  });
});
