// 01-rendering-05/06, 05-editing-03: címsor- és listaelem-összecsukás a szerkesztőben (LP, Forrás) és az Olvasóban.
import { ensureSyntaxTree, foldedRanges } from '@codemirror/language';
import { EditorState } from '@codemirror/state';
import { EditorView } from '@codemirror/view';
import { afterEach, describe, expect, it } from 'vitest';
import { bovitmenyek } from '../src/szerkeszto/beallitas';
import {
  hajtasKevesebb, hajtasTobb, hajtasValt, hajtasVisszaallit, hajthatoTartomany, hajtottSorok, MAX_HAJTOTT, mindetHajt, mindetKibont, osszesHajthato,
} from '../src/szerkeszto/hajtogatas';
import { hajtasParancsok } from '../src/szerkeszto/hajtasParancsok';
import { dokumentumRenderel } from '../src/szerkeszto/olvaso/html';
import { olvasoHajtas } from '../src/szerkeszto/olvaso/hajtas';
import { LustaRajzolo } from '../src/szerkeszto/olvaso/lusta';
import type { SzerkesztoPeldany } from '../src/szerkeszto/szerkesztok.svelte';

const nezetek: EditorView[] = [];
afterEach(() => { for (const v of nezetek.splice(0)) v.destroy(); document.body.textContent = ''; });

function nezet(doc: string, mod: 'elo' | 'forras' = 'elo', kurzor = doc.length): EditorView {
  const parent = document.createElement('div'); document.body.append(parent);
  const view = new EditorView({ parent, state: EditorState.create({ doc, selection: { anchor: kurzor }, extensions: bovitmenyek({ mod, ut: 'Host.md', cimke: 'Note', csakOlvashato: false }) }) });
  ensureSyntaxTree(view.state, doc.length, 5000); nezetek.push(view); return view;
}
const allapot = (doc: string) => EditorState.create({ doc, extensions: bovitmenyek({ mod: 'forras', ut: 'Host.md', cimke: 'Note', csakOlvashato: false }) });
const sor = (s: EditorState, n: number) => s.doc.line(n).from;
const szoveg = (s: EditorState, r: { from: number; to: number } | null) => (r ? s.sliceDoc(r.from, r.to) : null);
const csukott = (v: EditorView) => { const ki: string[] = []; foldedRanges(v.state).between(0, v.state.doc.length, (a, b) => { ki.push(v.state.sliceDoc(a, b)); }); return ki; };

const DOK = [
  '# Egy', //1
  'Bevezető', //2
  '', //3
  '## Kettő', //4
  'Szöveg', //5
  '', //6
  '### Három', //7
  'Mély', //8
  '', //9
  '## Négy', //10
  '- Szülő', //11
  '  - Gyerek', //12
  '    - Unoka', //13
  '- Magányos', //14
  'lusta folytatás', //15
  '', //16
  '# Öt', //17
  '', //18
].join('\n');

describe('a hajtható tartományok', () => {
  it('a felső szintű címsor a következő azonos vagy magasabb szintű címsorig hajt, a záró üres sorok nélkül', () => {
    const s = allapot(DOK);
    expect(szoveg(s, hajthatoTartomany(s, sor(s, 1)))).toBe(DOK.slice(DOK.indexOf('\nBevezető'), DOK.indexOf('lusta folytatás') + 'lusta folytatás'.length));
    expect(szoveg(s, hajthatoTartomany(s, sor(s, 4)))).toBe('\nSzöveg\n\n### Három\nMély');
    expect(szoveg(s, hajthatoTartomany(s, sor(s, 7)))).toBe('\nMély');
    expect(hajthatoTartomany(s, sor(s, 17))).toBeNull(); // üres szakasz
    expect(hajthatoTartomany(s, sor(s, 2))).toBeNull(); // bekezdés
    expect(hajthatoTartomany(s, sor(s, 3))).toBeNull(); // üres sor
  });

  it('a gyermekes listaelem hajt, a gyermektelen és a lusta folytatás nem', () => {
    const s = allapot(DOK);
    expect(szoveg(s, hajthatoTartomany(s, sor(s, 11)))).toBe('\n  - Gyerek\n    - Unoka');
    expect(szoveg(s, hajthatoTartomany(s, sor(s, 12)))).toBe('\n    - Unoka');
    expect(hajthatoTartomany(s, sor(s, 13))).toBeNull();
    expect(hajthatoTartomany(s, sor(s, 14))).toBeNull();
  });

  it('setext-cím, idézetbe ágyazott lista és feladat; idézetben / listában álló címsor nem felső szintű', () => {
    const doc = 'Cím\n===\nTörzs\n\n> - [ ] Feladat\n>   - al\n\n- # Listacím\n  szöveg';
    const s = allapot(doc);
    expect(szoveg(s, hajthatoTartomany(s, sor(s, 1)))).toBe('\n===\nTörzs\n\n> - [ ] Feladat\n>   - al\n\n- # Listacím\n  szöveg');
    expect(szoveg(s, hajthatoTartomany(s, sor(s, 5)))).toBe('\n>   - al');
    expect(szoveg(s, hajthatoTartomany(s, sor(s, 8)))).toBe('\n  szöveg'); // listaelemként, nem címsorként
  });

  it('kódblokk, frontmatter és táblázat nem hajtható (csak címsor és lista)', () => {
    const doc = '---\na: 1\n---\n```js\nx\ny\n```\n| a |\n|---|\n| b |';
    const s = allapot(doc);
    expect(osszesHajthato(s)).toEqual([]);
  });
});

describe('összecsukás a szerkesztőben', () => {
  it.each(['elo', 'forras'] as const)('%s: a gomb a hajtható sorokon, kattintásra hajt és bont; a szöveg nem változik', (mod) => {
    const v = nezet(DOK, mod, 0);
    const gombok = () => [...v.dom.querySelectorAll<HTMLButtonElement>('.cm-hajto')];
    expect(gombok().length).toBe(osszesHajthato(v.state).length);
    const negy = gombok().find((b) => b.closest('.cm-line')?.textContent?.includes('Négy'))!;
    expect(negy.getAttribute('aria-expanded')).toBe('true');
    negy.click();
    expect(csukott(v)).toEqual([DOK.slice(DOK.indexOf('\n- Szülő'), DOK.indexOf('lusta folytatás') + 'lusta folytatás'.length)]);
    expect(v.dom.querySelector('.cm-foldPlaceholder')).not.toBeNull();
    expect(v.dom.textContent).not.toContain('Gyerek');
    const ujra = gombok().find((b) => b.closest('.cm-line')?.textContent?.includes('Négy'))!;
    expect(ujra.getAttribute('aria-expanded')).toBe('false');
    expect(ujra.classList.contains('csukva')).toBe(true);
    ujra.click();
    expect(csukott(v)).toEqual([]);
    expect(v.state.doc.toString()).toBe(DOK);
  });

  it('a mind / kibont / több / kevesebb parancs a beágyazott hajtásokat is kezeli', () => {
    const v = nezet(DOK, 'elo', 0);
    expect(mindetHajt(v)).toBe(true);
    expect(foldedRanges(v.state).size).toBe(osszesHajthato(v.state).length);
    expect(hajtasKevesebb(v)).toBe(true); // csak a legkülső (# Egy) nyílik ki
    expect(csukott(v)).not.toContain(szoveg(v.state, hajthatoTartomany(v.state, sor(v.state, 1))));
    expect(csukott(v)).toContain('\nMély');
    expect(mindetKibont(v)).toBe(true);
    expect(foldedRanges(v.state).size).toBe(0);
    expect(hajtasTobb(v)).toBe(true); // először a legbelsők
    expect(csukott(v).sort()).toEqual(['\n    - Unoka', '\nMély'].sort());
    expect(hajtasTobb(v)).toBe(true);
    expect(csukott(v)).toContain('\n  - Gyerek\n    - Unoka');
    expect(v.state.doc.toString()).toBe(DOK);
  });

  it('a váltás a kurzor soránál, vagy a kurzort tartalmazó szakaszon; a kurzor a hajtás elé kerül', () => {
    const v = nezet(DOK, 'forras', DOK.indexOf('Mély') + 2);
    expect(hajtasValt(v)).toBe(true);
    expect(csukott(v)).toEqual(['\nMély']);
    expect(v.state.selection.main.head).toBe(sor(v.state, 7));
    expect(hajtasValt(v)).toBe(true);
    expect(csukott(v)).toEqual([]);
  });

  it('a hajtás alatti táblázat és képletblokk-widget nem tör (LP), a forrás érintetlen', () => {
    const doc = '# A\n| x | y |\n|---|---|\n| 1 | 2 |\n\n$$\nx^2\n$$\n\n# B';
    const v = nezet(doc, 'elo', doc.length);
    expect(mindetHajt(v)).toBe(true);
    expect(v.dom.querySelector('.cm-foldPlaceholder')).not.toBeNull();
    expect(v.dom.querySelector('table')).toBeNull();
    mindetKibont(v);
    expect(v.dom.querySelector('table')).not.toBeNull();
    expect(v.state.doc.toString()).toBe(doc);
  });

  it('a nézet-állapot sorszámokat tárol; a visszaállítás az elavult és hibás értékeket elhagyja', () => {
    const v = nezet(DOK, 'elo', 0);
    mindetHajt(v);
    const mentett = hajtottSorok(v.state);
    expect(mentett).toEqual([1, 4, 7, 10, 11, 12]);
    const w = nezet(DOK, 'forras', 0);
    hajtasVisszaallit(w, [...mentett, 2, 999, -1, 'x', 1.5, 4]);
    expect(hajtottSorok(w.state)).toEqual(mentett);
    hajtasVisszaallit(nezet(DOK), { nem: 'tömb' });
    // a kurzor egy visszaállított hajtás belsejében: a kurzor a hajtás elé kerül, a hajtás megmarad
    const k = nezet(DOK, 'forras', DOK.indexOf('Mély'));
    hajtasVisszaallit(k, [7]);
    expect(hajtottSorok(k.state)).toEqual([7]);
    expect(k.state.selection.main.head).toBe(k.state.doc.line(7).to);
  });

  it('a tárolt lista korlátos (a fül nézet-állapota 2 KB alatt marad)', () => {
    const doc = Array.from({ length: MAX_HAJTOTT + 30 }, (_, i) => `# H${i}\nx`).join('\n');
    const v = nezet(doc, 'forras', 0);
    mindetHajt(v);
    const h = hajtottSorok(v.state);
    expect(h.length).toBe(MAX_HAJTOTT);
    expect(JSON.stringify({ mod: 'elo', sor: 99999, kurzor: 9999999, hajtott: h }).length).toBeLessThan(2048);
  });

  it('a parancsok a palettában: a váltás Olvasóban nem érhető el, a többi igen', () => {
    const v = nezet(DOK, 'elo', 0);
    let mod: 'elo' | 'olvaso' = 'elo';
    const p = { nezet: () => v, mod: () => mod } as unknown as SzerkesztoPeldany;
    const ps = hajtasParancsok(() => p);
    expect(ps.map((x) => x.id)).toEqual(['szerkeszto.hajtas-valt', 'szerkeszto.hajt-mind', 'szerkeszto.kibont-mind', 'szerkeszto.hajt-tobb', 'szerkeszto.hajt-kevesebb']);
    expect(ps.every((x) => x.elerheto!())).toBe(true);
    mod = 'olvaso';
    expect(ps.map((x) => x.elerheto!())).toEqual([false, true, true, true, true]);
    void ps[1].futtat();
    expect(foldedRanges(v.state).size).toBeGreaterThan(0);
  });
});

describe('összecsukás az Olvasóban', () => {
  function olvaso(doc: string) {
    const v = nezet(doc, 'elo', 0);
    const gyoker = document.createElement('article'); document.body.append(gyoker);
    gyoker.append(dokumentumRenderel(ensureSyntaxTree(v.state, doc.length, 5000)!, { olvas: (a, b) => doc.slice(a, b), ut: 'Host.md', lusta: LustaRajzolo.azonnali() }));
    olvasoHajtas(gyoker, v);
    return { v, gyoker };
  }
  const lathato = (e: Element | null) => !!e && (e as HTMLElement).style.display !== 'none';

  it('a címsor-gomb a szakaszt rejti, a szerkesztő állapotába ír, a lábjegyzet-szakasz látszik', () => {
    const doc = '# A\nEgy[^1]\n\n## B\nKettő\n\n# C\nHárom\n\n[^1]: Jegyzet';
    const { v, gyoker } = olvaso(doc);
    const h1 = gyoker.querySelector('h1')!;
    const b = h1.querySelector<HTMLButtonElement>('button.olvaso-hajto')!;
    expect(b.getAttribute('aria-expanded')).toBe('true');
    b.click();
    expect(hajtottSorok(v.state)).toEqual([1]);
    const p = [...gyoker.querySelectorAll('p')];
    expect(lathato(p.find((x) => x.textContent?.startsWith('Egy'))!)).toBe(false);
    expect(lathato(gyoker.querySelector('h2'))).toBe(false);
    expect(lathato(p.find((x) => x.textContent === 'Három')!)).toBe(true);
    expect(lathato(gyoker.querySelector('section.labjegyzetek'))).toBe(true);
    expect((gyoker.querySelector('h2') as HTMLElement).hidden).toBe(true); // az Olvasó-keresés a rejtett szakaszt kihagyja
    expect(h1.querySelector('button.olvaso-hajto')!.getAttribute('aria-expanded')).toBe('false');
    expect(v.state.doc.toString()).toBe(doc);
    // a szerkesztőből jövő kibontást a frissítés követi
    mindetKibont(v); olvasoHajtas(gyoker, v);
    expect(lathato(gyoker.querySelector('h2'))).toBe(true);
  });

  it('a gyermekes listaelem a beágyazott listát rejti; gyermektelen elemen nincs gomb; a beágyazás tartalma kimarad', () => {
    const doc = '- Szülő\n  - Gyerek\n- Egyedül';
    const { v, gyoker } = olvaso(doc);
    const [szulo, gyerek, egyedul] = [...gyoker.querySelectorAll('li')];
    expect(szulo.querySelector(':scope > button.olvaso-hajto')).not.toBeNull();
    expect(gyerek.querySelector(':scope > button.olvaso-hajto')).toBeNull();
    expect(egyedul.querySelector(':scope > button.olvaso-hajto')).toBeNull();
    szulo.querySelector<HTMLButtonElement>(':scope > button.olvaso-hajto')!.click();
    expect(lathato(szulo.querySelector('ul'))).toBe(false);
    expect(lathato(szulo.firstElementChild!.nextElementSibling)).toBe(true); // az első blokk
    expect(hajtottSorok(v.state)).toEqual([1]);
    const embed = dokumentumRenderel(ensureSyntaxTree(v.state, doc.length, 5000)!, { olvas: (a, b) => doc.slice(a, b), ut: 'X.md', lusta: LustaRajzolo.azonnali(), beagyazas: { lanc: [], melyseg: 1 } });
    expect(embed.querySelector('li[data-from]')).toBeNull();
  });
});
