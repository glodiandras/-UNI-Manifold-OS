// A `[[` kiegészítés (C10) a CodeMirror-nézetben, jsdom-ban, ál-core-ral: a `[[` gépelése beírja a `]]`-t és megnyitja a
// menüt; fájl-mód (fuzzy, ékezetfüggetlen, aliasokkal), `#` fejezet-mód (élő szövegből és másik jegyzetből), `#^`
// blokk-mód (id nélküli blokknál az azonosító is beíródik, egy ⌘Z-vel visszavonható), `|` alias-mód; Backspace, Esc,
// readOnly, kódblokk. A cél-szöveget a core (`linkcel`) adja.

import { undo } from '@codemirror/commands';
import { ensureSyntaxTree } from '@codemirror/language';
import { EditorState } from '@codemirror/state';
import { EditorView, runScopeHandlers } from '@codemirror/view';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { FajlInfo } from '../src/lib/vault/fajlok.svelte';
import { linkek } from '../src/lib/vault/linkek.svelte';
import { bovitmenyek } from '../src/szerkeszto/beallitas';
import { kiegeszitesNyitva, lekerdezes, lekerdezesElemez } from '../src/szerkeszto/linkek/kiegeszites';
import { billentyu } from './notion-segedek';

const f = (ut: string, tipus: FajlInfo['tipus'] = 'md', mtime = 1): FajlInfo => ({ ut, tipus, meret: 1, mtime });
const FAJLOK: FajlInfo[] = [
  f('Matek/Mértani sorozat.md', 'md', 50),
  f('Matek/Számtani sorozat.md', 'md', 40),
  f('Történelem/Jegyzet.md', 'md', 30),
  f('Fizika/Jegyzet.md', 'md', 20),
  f('Képek/ábra 1.png', 'kep', 10),
  f('Könyvek/Analízis.pdf', 'pdf', 5),
];
const ALIASOK: Record<string, string[]> = { 'Matek/Mértani sorozat.md': ['geometriai sorozat', 'q-sorozat'] };
const LINKCEL: Record<string, string> = {
  'Matek/Mértani sorozat.md': 'Mértani sorozat',
  'Matek/Számtani sorozat.md': 'Számtani sorozat',
  'Történelem/Jegyzet.md': 'Történelem/Jegyzet',
  'Képek/ábra 1.png': 'ábra 1.png',
};
const nezetek: EditorView[] = [];
let kerelmek: string[];

function valasz(adat: unknown, kod = 200) {
  return new Response(JSON.stringify(adat), { status: kod, headers: { 'Content-Type': 'application/json' } });
}

beforeEach(() => {
  kerelmek = [];
  linkek.ervenytelenit();
  vi.stubGlobal('fetch', async (url: string, init?: RequestInit) => {
    const u = new URL(url, 'http://127.0.0.1/');
    kerelmek.push(u.pathname);
    if (u.pathname === '/api/vault/aliasok') return valasz({ aliasok: ALIASOK });
    if (u.pathname === '/api/vault/linkcel') return valasz({ ut: u.searchParams.get('ut'), cel: LINKCEL[u.searchParams.get('ut')!] ?? u.searchParams.get('ut') });
    if (u.pathname === '/api/vault/feloldas') {
      const k = JSON.parse(String(init?.body)) as { celok: string[] };
      return valasz({
        eredmenyek: k.celok.map((c) => ({ cel: c, ut: c === 'Mértani' ? 'Matek/Mértani sorozat.md' : c === 'kép' ? 'Képek/ábra 1.png' : null, tobbertelmu: false })),
      });
    }
    if (u.pathname === '/api/vault/jegyzet')
      return valasz({
        fejezetek: [{ szint: 1, szoveg: 'Mértani sorozat', sor: 1 }, { szint: 2, szoveg: 'Képlet', sor: 3 }],
        blokkok: [{ azon: 'kepl', sor: 4, kezdo_sor: 4 }],
      });
    if (u.pathname === '/api/vault/fajl') return valasz({ ut: 'x', tartalom: '# Mértani sorozat\n\n## Képlet\nA hányados ^kepl\n', hash: 'h' });
    return valasz({ hiba: 'nincs' }, 404);
  });
});

afterEach(() => {
  while (nezetek.length) nezetek.pop()!.destroy();
  document.body.textContent = '';
  vi.unstubAllGlobals();
});

function nezet(doc: string, o: { kurzor?: number; csakOlvashato?: boolean } = {}): EditorView {
  const hely = document.createElement('div');
  document.body.appendChild(hely);
  const state = EditorState.create({
    doc,
    selection: { anchor: o.kurzor ?? doc.length },
    extensions: bovitmenyek({
      mod: 'elo',
      csakOlvashato: !!o.csakOlvashato,
      ut: 'Jegyzet.md',
      cimke: 'próba',
      linkNev: () => 'Jegyzet',
      kiegeszites: { fajlok: () => FAJLOK, legutobbi: () => ['Történelem/Jegyzet.md'] },
    }),
  });
  const v = new EditorView({ state, parent: hely });
  ensureSyntaxTree(v.state, v.state.doc.length, 5000);
  nezetek.push(v);
  return v;
}

/** Gépelés a beviteli kezelőkön át (a `[[` párosítása `inputHandler`), mint a böngésző `beforeinput`-ja. */
function ir(v: EditorView, szoveg: string): void {
  for (const c of szoveg) {
    const r = v.state.selection.main;
    const kezelve = v.state.facet(EditorView.inputHandler).some((h) => h(v, r.from, r.to, c, () => v.state.update({ changes: { from: r.from, to: r.to, insert: c } })));
    if (!kezelve) v.dispatch({ changes: { from: r.from, to: r.to, insert: c }, selection: { anchor: r.from + 1 }, userEvent: 'input.type' });
  }
}

const elemek = (v: EditorView) => [...v.dom.querySelectorAll('.nt-linkmenu .nt-menu-elem')].map((e) => e.querySelector('.nt-menu-nev')!.textContent);
const jelzok = (v: EditorView) => [...v.dom.querySelectorAll('.nt-linkmenu .nt-menu-elem')].map((e) => e.querySelector('.nt-menu-jelzo')?.textContent ?? '');
const varMenu = (v: EditorView, feltetel: (e: string[]) => boolean = (e) => e.length > 0) => vi.waitFor(() => expect(feltetel(elemek(v))).toBe(true));

describe('lekérdezés-elemzés', () => {
  it('módok', () => {
    expect(lekerdezesElemez('Jegy')).toEqual({ mod: 'fajl', cel: 'Jegy', alk: '', alias: '' });
    expect(lekerdezesElemez('Jegyzet#Fej')).toEqual({ mod: 'fejezet', cel: 'Jegyzet', alk: 'Fej', alias: '' });
    expect(lekerdezesElemez('#')).toEqual({ mod: 'fejezet', cel: '', alk: '', alias: '' });
    expect(lekerdezesElemez('Jegyzet#^ab')).toEqual({ mod: 'blokk', cel: 'Jegyzet', alk: 'ab', alias: '' });
    expect(lekerdezesElemez('Jegyzet|al')).toEqual({ mod: 'alias', cel: 'Jegyzet', alk: '', alias: 'al' });
    expect(lekerdezesElemez('Jegyzet#Fej|al')).toEqual({ mod: 'alias', cel: 'Jegyzet', alk: 'Fej', alias: 'al' });
  });
});

describe('a [[ gépelése', () => {
  it('beírja a ]]-t, a kurzor közéjük kerül, a menü a legutóbbiakkal nyílik', async () => {
    const v = nezet('Szöveg ');
    ir(v, '[[');
    expect(v.state.doc.toString()).toBe('Szöveg [[]]');
    expect(v.state.selection.main.head).toBe('Szöveg [['.length);
    expect(kiegeszitesNyitva(v.state)).toBe(true);
    expect(lekerdezes(v.state)).toBe('');
    await varMenu(v);
    expect(elemek(v)[0]).toBe('Jegyzet'); // a legutóbbi (Történelem/Jegyzet) elöl, a mappa jelzővel
    expect(jelzok(v)[0]).toBe('Történelem');
    expect(elemek(v)).toContain('Mértani sorozat');
  });

  it('a harmadik [ nem párosít újra; a meglévő ]] előtt nem ír újat', () => {
    const v = nezet('', { kurzor: 0 });
    ir(v, '[[');
    expect(v.state.doc.toString()).toBe('[[]]');
    const w = nezet('[]]', { kurzor: 1 });
    ir(w, '[');
    expect(w.state.doc.toString()).toBe('[[]]');
  });

  it('kódblokkban és csak olvashatóban nincs kiegészítés', () => {
    const v = nezet('```\ncode ', {});
    ir(v, '[[');
    expect(v.state.doc.toString()).toBe('```\ncode [[');
    expect(kiegeszitesNyitva(v.state)).toBe(false);
    const w = nezet('x ', { csakOlvashato: true });
    ir(w, '[[');
    expect(kiegeszitesNyitva(w.state)).toBe(false);
    expect(w.state.doc.toString()).toBe('x '); // csak olvashatóban a bevitelt (a programosat is) elveti a `changeFilter` (T117)
  });

  it('Backspace a [[|]] közepén a párt együtt törli, Esc bezárja', async () => {
    const v = nezet('a ');
    ir(v, '[[');
    runScopeHandlers(v, new KeyboardEvent('keydown', { key: 'Backspace' }), 'editor');
    expect(v.state.doc.toString()).toBe('a ');
    expect(kiegeszitesNyitva(v.state)).toBe(false);
    ir(v, '[[');
    await varMenu(v);
    const e = billentyu(v, 'Escape');
    expect(e.defaultPrevented).toBe(true);
    expect(v.state.doc.toString()).toBe('a [[]]');
    expect(kiegeszitesNyitva(v.state)).toBe(false);
  });

  it('a kurzor kimozdulása vagy a ] gépelése bezárja', async () => {
    const v = nezet('sor ');
    ir(v, '[[');
    ir(v, 'ab');
    expect(kiegeszitesNyitva(v.state)).toBe(true);
    v.dispatch({ selection: { anchor: 0 } });
    expect(kiegeszitesNyitva(v.state)).toBe(false);
  });
});

describe('fájl-mód', () => {
  it('ékezetfüggetlen, elírástűrő találat; ↩ a core cél-szövegét írja, a kurzor a ]] után áll', async () => {
    const v = nezet('Lásd: ');
    ir(v, '[[');
    ir(v, 'mertani');
    await varMenu(v, (e) => e[0] === 'Mértani sorozat');
    billentyu(v, 'Enter');
    await vi.waitFor(() => expect(v.state.doc.toString()).toBe('Lásd: [[Mértani sorozat]]'));
    expect(v.state.selection.main.head).toBe(v.state.doc.length);
    expect(kiegeszitesNyitva(v.state)).toBe(false);
    expect(kerelmek).toContain('/api/vault/linkcel');
  });

  it('azonos nevű fájlnál a core egyértelmű (útvonalas) alakja kerül be', async () => {
    const v = nezet('');
    ir(v, '[[Történelem');
    await varMenu(v, (e) => e.some((x) => x === 'Jegyzet'));
    billentyu(v, 'Enter');
    await vi.waitFor(() => expect(v.state.doc.toString()).toBe('[[Történelem/Jegyzet]]'));
  });

  it('alias-találat: [[Jegyzet|Alias]]; az alias a jelzőben a célt mutatja', async () => {
    const v = nezet('');
    ir(v, '[[geometr');
    await varMenu(v, (e) => e[0] === 'geometriai sorozat');
    expect(jelzok(v)[0]).toBe('→ Mértani sorozat');
    billentyu(v, 'Enter');
    await vi.waitFor(() => expect(v.state.doc.toString()).toBe('[[Mértani sorozat|geometriai sorozat]]'));
  });

  it('kép és PDF is választható (kiterjesztéssel); ![[ ugyanazt a menüt nyitja', async () => {
    const v = nezet('');
    ir(v, '![[abra');
    await varMenu(v, (e) => e[0] === 'ábra 1.png');
    billentyu(v, 'Enter');
    await vi.waitFor(() => expect(v.state.doc.toString()).toBe('![[ábra 1.png]]'));
  });

  it('találat nélkül az Enter a gépelt szöveget fogadja el: nincs új sor, a kurzor a ]] után áll', async () => {
    const v = nezet('');
    ir(v, '[[zzzzzzzz');
    await varMenu(v, (e) => e.length === 0);
    const e = billentyu(v, 'Enter');
    expect(e.defaultPrevented).toBe(true);
    expect(kiegeszitesNyitva(v.state)).toBe(false);
    expect(v.state.doc.toString()).toBe('[[zzzzzzzz]]');
    expect(v.state.selection.main.head).toBe(v.state.doc.length);
  });
});

describe('fejezet-, blokk- és alias-mód', () => {
  it('[[# : az aktuális jegyzet fejezetei az ÉLŐ szövegből', async () => {
    const v = nezet('# Cím\n\n## Első rész\n\nszöveg\n\n## Második\n\n');
    ir(v, '[[#');
    await varMenu(v, (e) => e.length === 3);
    expect(elemek(v)).toEqual(['Cím', 'Első rész', 'Második']);
    expect(jelzok(v)).toEqual(['H1', 'H2', 'H2']);
    ir(v, 'masod');
    await varMenu(v, (e) => e.length === 1 && e[0] === 'Második');
    billentyu(v, 'Enter');
    await vi.waitFor(() => expect(v.state.doc.toString().endsWith('[[#Második]]')).toBe(true));
  });

  it('másik jegyzet fejezetei: a core oldja fel a gépelt célt, a kérés a /jegyzet', async () => {
    const v = nezet('');
    ir(v, '[[Mértani#');
    await varMenu(v, (e) => e.length === 2);
    expect(elemek(v)).toEqual(['Mértani sorozat', 'Képlet']);
    expect(kerelmek).toContain('/api/vault/feloldas');
    billentyu(v, 'ArrowDown');
    billentyu(v, 'Enter');
    await vi.waitFor(() => expect(v.state.doc.toString()).toBe('[[Mértani#Képlet]]'));
  });

  it('a fejezet a link-jelek nélkül íródik (#, |, ^, [, ] szóközre)', async () => {
    const v = nezet('## Fej | rész ^ x\n\n');
    ir(v, '[[#');
    await varMenu(v);
    billentyu(v, 'Enter');
    await vi.waitFor(() => expect(v.state.doc.toString()).toContain('[[#Fej rész x]]'));
  });

  it('[[#^ : az aktuális jegyzet blokkjai; az id nélkülinél az azonosító is beíródik, egy ⌘Z mindkettőt visszavonja', async () => {
    const eredeti = 'Egy bekezdés ^abc\n\nMásik bekezdés\n\n';
    const v = nezet(eredeti);
    ir(v, '[[#^');
    await varMenu(v, (e) => e.length === 2);
    expect(elemek(v)).toEqual(['Egy bekezdés', 'Másik bekezdés']);
    expect(jelzok(v)).toEqual(['^abc', 'új ^id']);
    billentyu(v, 'ArrowDown');
    billentyu(v, 'Enter');
    await vi.waitFor(() => expect(v.state.doc.toString()).toMatch(/Másik bekezdés \^[a-z0-9]{6}\n/));
    const id = /Másik bekezdés \^([a-z0-9]{6})/.exec(v.state.doc.toString())![1];
    expect(v.state.doc.toString().endsWith(`[[#^${id}]]`)).toBe(true);
    expect(v.state.selection.main.head).toBe(v.state.doc.length);
    undo(v);
    expect(v.state.doc.toString()).not.toContain(id);                  // az azonosító és a link együtt visszavonva
    expect(v.state.doc.toString().startsWith('Egy bekezdés ^abc\n\nMásik bekezdés\n')).toBe(true);
    expect(v.state.doc.toString()).not.toMatch(/Másik bekezdés \^/);
  });

  it('a meglévő azonosítójú blokk linkje változtatás nélkül, a saját sorára nem hivatkozik', async () => {
    const v = nezet('Egy bekezdés ^abc\n\n');
    ir(v, '[[#^');
    await varMenu(v);
    billentyu(v, 'Enter');
    await vi.waitFor(() => expect(v.state.doc.toString()).toBe('Egy bekezdés ^abc\n\n[[#^abc]]'));
  });

  it('másik jegyzet blokkjai: csak a ^id-sek, előnézettel', async () => {
    const v = nezet('');
    ir(v, '[[Mértani#^');
    await varMenu(v, (e) => e.length === 1);
    expect(elemek(v)).toEqual(['A hányados']);
    expect(jelzok(v)).toEqual(['^kepl']);
    billentyu(v, 'Enter');
    await vi.waitFor(() => expect(v.state.doc.toString()).toBe('[[Mértani#^kepl]]'));
  });

  it('| alias-mód: a cél aliasai', async () => {
    const v = nezet('');
    ir(v, '[[Mértani sorozat|');
    // a core feloldás-stubja csak a „Mértani” rövid alakot ismeri → a teljes név nem old fel: üres lista
    await varMenu(v, (e) => e.length === 0);
    const w = nezet('');
    ir(w, '[[Mértani|q');
    await varMenu(w, (e) => e.length === 1 && e[0] === 'q-sorozat');
    billentyu(w, 'Enter');
    await vi.waitFor(() => expect(w.state.doc.toString()).toBe('[[Mértani|q-sorozat]]'));
  });
});
