import { EditorState } from '@codemirror/state';
import { EditorView } from '@codemirror/view';
import { history, undoDepth } from '@codemirror/commands';
import { forceParsing, syntaxTreeAvailable } from '@codemirror/language';
import { commonmarkLanguage, markdown } from '@codemirror/lang-markdown';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { nyelvFelismer } from '../src/lib/munkater/nyelvFelismeres';
import { automatikusNyelv, felismertNyelv, NYELV_KESLELTETES, nyelviMinta } from '../src/szerkeszto/nyelv';
import { OBSIDIAN_BOVITESEK } from '../src/szerkeszto/markdown/elemzo';

const nezetek: EditorView[] = [];
beforeEach(() => vi.useFakeTimers());
afterEach(() => {
  for (const v of nezetek.splice(0)) v.destroy();
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

function hid(postMessage: (adat: { szoveg: string }) => unknown) {
  vi.stubGlobal('webkit', { messageHandlers: { nyelv: { postMessage } } });
}

function nezet(szoveg = 'Ez egy magyar nyelvű jegyzet, amelyben a felhasználó szabadon írhat és gondolkodhat.', elemez = true, elozetesen = true) {
  const v = new EditorView({ state: EditorState.create({ doc: szoveg, extensions: [
    history(), automatikusNyelv(),
    elemez ? markdown({ base: commonmarkLanguage, extensions: OBSIDIAN_BOVITESEK }) : [],
  ] }) });
  if (elemez && elozetesen) expect(forceParsing(v, v.state.doc.length, 200)).toBe(true);
  nezetek.push(v);
  return v;
}

describe('helyi, automatikus nyelvfelismerés', () => {
  it('a prózaminta kihagyja a YAML-t, kódot, képletet és címet, a bekezdések és a link felirata megmaradnak', () => {
    const s = [
      '---', 'title: English technical metadata', '---',
      'Magyar szöveg a jegyzetben.', '', '```ts', 'const language = "english";', '```',
      '$$', '\\sum_{i=1}^{n} x_i', '$$',
      'Másik bekezdés [[Some/Path|saját felirat]] és [hivatkozás](https://example.test/english).',
    ].join('\n');
    const m = nyelviMinta(s);
    expect(m).toContain('Magyar szöveg');
    expect(m).toContain('Másik bekezdés saját felirat és hivatkozás');
    expect(m).not.toMatch(/metadata|language|sum_|https|Some\/Path/);
    expect(nyelviMinta('```cpp\nint main() { return 0; }\n```')).toBe('');
    expect(nyelviMinta('a'.repeat(100000)).length).toBe(8000);
  });

  it('héj nélkül sem kényszeríti angolra a jegyzetet és nincs újrapróbáló időzítő', async () => {
    const v = nezet();
    await vi.advanceTimersByTimeAsync(5000);
    expect(v.contentDOM.lang).toBe('');
    expect(await nyelvFelismer('szöveg')).toBeNull();
  });

  it('a gépelés késleltetve ismer fel, és a felismerés megőrzi a szöveget, kurzort és visszavonást', async () => {
    const ker = vi.fn(async () => ({ nyelv: 'hu', bizalom: 0.99 }));
    hid(ker);
    const v = nezet();
    await vi.advanceTimersByTimeAsync(1);
    expect(v.contentDOM.lang).toBe('hu');
    for (let i = 0; i < 10; i++) v.dispatch({ changes: { from: v.state.doc.length, insert: ' x' }, userEvent: 'input.type' });
    const szoveg = v.state.doc.toString();
    const kurzor = v.state.selection.toJSON();
    const vissza = undoDepth(v.state);
    await vi.advanceTimersByTimeAsync(NYELV_KESLELTETES - 1);
    expect(ker).toHaveBeenCalledTimes(1);
    ker.mockResolvedValueOnce({ nyelv: 'en', bizalom: 0.99 });
    await vi.advanceTimersByTimeAsync(2);
    expect(ker).toHaveBeenCalledTimes(2);
    expect(v.state.field(felismertNyelv)).toBe('en');
    expect(v.state.doc.toString()).toBe(szoveg);
    expect(v.state.selection.toJSON()).toEqual(kurzor);
    expect(undoDepth(v.state)).toBe(vissza);
  });

  it('vegyes vagy bizonytalan szövegnél az automatikus rendszerellenőrzést hagyja működni', async () => {
    const ker = vi.fn(async () => ({ nyelv: 'hu' as string | null, bizalom: 0.99, kevert: false }));
    hid(ker);
    const v = nezet();
    await vi.advanceTimersByTimeAsync(1);
    expect(v.contentDOM.lang).toBe('hu');
    ker.mockResolvedValueOnce({ nyelv: null, bizalom: 0, kevert: true });
    v.dispatch({ changes: { from: v.state.doc.length, insert: '\n\nThis paragraph is written in English.' } });
    await vi.advanceTimersByTimeAsync(NYELV_KESLELTETES + 1);
    expect(v.contentDOM.lang).toBe('');
    ker.mockResolvedValueOnce({ nyelv: 'en', bizalom: 0.4, kevert: false });
    v.dispatch({ changes: { from: 0, to: v.state.doc.length, insert: 'ambiguous' } });
    await vi.advanceTimersByTimeAsync(NYELV_KESLELTETES + 1);
    expect(v.contentDOM.lang).toBe('');
  });

  it('a bezárt nézetre érkező válasz nem ír a megsemmisített szerkesztőbe', async () => {
    let kesz!: (v: unknown) => void;
    hid(() => new Promise((k) => { kesz = k; }));
    const v = nezet();
    await vi.advanceTimersByTimeAsync(1);
    const dispatch = vi.spyOn(v, 'dispatch');
    v.destroy();
    nezetek.splice(nezetek.indexOf(v), 1);
    kesz({ nyelv: 'hu', bizalom: 0.99 });
    await vi.advanceTimersByTimeAsync(1);
    expect(dispatch).not.toHaveBeenCalled();
  });

  it('nagy jegyzet végén is felismeri az éppen írt nyelvet, korlátos prózamintából', async () => {
    const ker = vi.fn(async (_adat: { szoveg: string }) => ({ nyelv: 'hu', bizalom: 0.99 }));
    hid(ker);
    const szoveg = 'Earlier content.\n\n'.repeat(3000) + 'A jegyzet végén magyarul írt szöveg is bekerül a felismerési mintába.';
    const v = nezet(szoveg);
    v.dispatch({ selection: { anchor: szoveg.length } });
    await vi.advanceTimersByTimeAsync(NYELV_KESLELTETES + 1);
    const minta = ker.mock.calls.at(-1)![0].szoveg;
    expect(minta).toContain('magyarul írt szöveg');
    expect(minta.length).toBeLessThanOrEqual(8000);
    expect(v.contentDOM.lang).toBe('hu');
  });

  it('a háttérelemzés elkészültekor gépelés és kurzormozgás nélkül újra megpróbálja a nagy jegyzetet', async () => {
    const ker = vi.fn(async ({ szoveg }: { szoveg: string }) => ({ nyelv: szoveg ? 'hu' : null, bizalom: szoveg ? 0.99 : 0 }));
    hid(ker);
    const szoveg = 'Magyar nyelvű bekezdés a jegyzetben, amely a nyelvfelismeréshez elegendő összefüggő szöveget tartalmaz.\n\n'.repeat(500);
    const v = nezet(szoveg, true, false);
    expect(syntaxTreeAvailable(v.state, 12000)).toBe(false);
    const kurzor = v.state.selection.toJSON();
    await vi.advanceTimersByTimeAsync(1);
    expect(ker.mock.calls.map(([adat]) => adat.szoveg)).toEqual(['']);
    await vi.advanceTimersByTimeAsync(1000);
    expect(syntaxTreeAvailable(v.state, v.state.doc.length)).toBe(true);
    await vi.advanceTimersByTimeAsync(NYELV_KESLELTETES + 1);
    expect(ker.mock.calls.at(-1)![0].szoveg).toContain('Magyar nyelvű bekezdés');
    expect(v.contentDOM.lang).toBe('hu');
    expect(v.state.doc.toString()).toBe(szoveg);
    expect(v.state.selection.toJSON()).toEqual(kurzor);
    expect(undoDepth(v.state)).toBe(0);
  });

  it.each([
    ['kerített kód', '```ts\n', '// English comment in a fenced code block.\n', '```'],
    ['behúzott kód', '', '    English comment in an indented code block.\n', ''],
    ['soron belüli kód', '`', 'English comment inside inline code. ', '`'],
    ['frontmatter', '---\n', 'description: English metadata only.\n', '---'],
    ['képlet', '$$\n', '\\text{English description inside a formula.}\n', '$$'],
    ['HTML', '<div>\n', 'English description inside an HTML block.\n', '</div>'],
    ['HTML-megjegyzés', '<!--\n', 'English description inside an HTML comment.\n', '-->'],
  ])('hosszú %s belsejébe eső kurzorablak nem lesz próza', async (_nev, nyit, sor, zar) => {
    const ker = vi.fn(async (_adat: { szoveg: string }) => ({ nyelv: null, bizalom: 0 }));
    hid(ker);
    const szoveg = nyit + sor.repeat(1400) + zar;
    expect(szoveg.length).toBeGreaterThan(24000);
    const v = nezet(szoveg);
    v.dispatch({ selection: { anchor: Math.floor(szoveg.length / 2) } });
    await vi.advanceTimersByTimeAsync(NYELV_KESLELTETES + 1);
    expect(ker).toHaveBeenCalled();
    expect(ker.mock.calls.at(-1)![0].szoveg).toBe('');
    expect(v.contentDOM.lang).toBe('');
  });

  it('ismeretlen szintaktikai környezetnél nem küldi el prózaként a kurzor körüli kódot', async () => {
    const ker = vi.fn(async (_adat: { szoveg: string }) => ({ nyelv: null, bizalom: 0 }));
    hid(ker);
    const szoveg = '```ts\n' + '// English comment in a fenced code block.\n'.repeat(1400) + '```';
    const v = nezet(szoveg, false);
    v.dispatch({ selection: { anchor: Math.floor(szoveg.length / 2) } });
    await vi.advanceTimersByTimeAsync(NYELV_KESLELTETES + 1);
    expect(ker.mock.calls.at(-1)![0].szoveg).toBe('');
  });

  it('a natív hívás korlátos és időtúllépésnél vagy hibás válasznál csendben automatikus marad', async () => {
    const ker = vi.fn((_adat: { szoveg: string }) => new Promise(() => {}));
    hid(ker);
    const fuggoben = nyelvFelismer('x'.repeat(100000));
    expect(ker.mock.calls[0][0].szoveg.length).toBe(8000);
    await vi.advanceTimersByTimeAsync(3001);
    expect(await fuggoben).toBeNull();
    for (const rossz of [{ nyelv: '../hu', bizalom: 0.99 }, { nyelv: 'hu', bizalom: Infinity }, { nyelv: 'hu', bizalom: 2 }, null]) {
      hid(async () => rossz);
      expect(await nyelvFelismer('szöveg')).toBeNull();
    }
  });
});
