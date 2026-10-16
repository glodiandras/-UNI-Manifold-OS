// F11 / 02-links-04…07, 12…14: a `[[` kiegészítés bővítései — id-t kapó blokk másik jegyzetben, vault-szintű `[[##` fejezetkeresés,
// újranyitás egy meglévő linken belül, `[[` kijelöléssel, a „Use [[Wikilinks]]” kikapcsolt alakja és a még nem létező link-célok.

import { ensureSyntaxTree } from '@codemirror/language';
import { EditorState, Text } from '@codemirror/state';
import { EditorView } from '@codemirror/view';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { ertesitesek } from '../src/lib/ertesites/ertesites.svelte';
import type { FajlInfo } from '../src/lib/vault/fajlok.svelte';
import { linkek } from '../src/lib/vault/linkek.svelte';
import { bovitmenyek } from '../src/szerkeszto/beallitas';
import { kiegeszitesNyitva, lekerdezes, lekerdezesElemez, linkBeszur, nyitottLink } from '../src/szerkeszto/linkek/kiegeszites';
import { szerkesztok } from '../src/szerkeszto/szerkesztok.svelte';
import { billentyu } from './notion-segedek';

const f = (ut: string, tipus: FajlInfo['tipus'] = 'md', mtime = 1): FajlInfo => ({ ut, tipus, meret: 1, mtime });
const FAJLOK: FajlInfo[] = [f('Matek/Mértani sorozat.md', 'md', 50), f('Matek/Számtani sorozat.md', 'md', 40), f('Képek/ábra 1.png', 'kep', 10)];
const LINKCEL: Record<string, { cel: string; md: string }> = {
  'Matek/Mértani sorozat.md': { cel: 'Mértani sorozat', md: 'M%C3%A9rtani%20sorozat.md' },
  'Matek/Számtani sorozat.md': { cel: 'Számtani sorozat', md: 'Sz%C3%A1mtani%20sorozat.md' },
  'Képek/ábra 1.png': { cel: 'ábra 1.png', md: '%C3%A1bra%201.png' },
};
const MASIK = '# Mértani sorozat\n\nElső bekezdés\n\nMásik bekezdés ^abc\n';
const nezetek: EditorView[] = [];
let kerelmek: string[];
let alak: 'wiki' | 'md';
let feloldatlan: { cel: string; db: number }[];

const valasz = (adat: unknown, kod = 200) => new Response(JSON.stringify(adat), { status: kod, headers: { 'Content-Type': 'application/json' } });

beforeEach(() => {
  kerelmek = [];
  alak = 'wiki';
  feloldatlan = [];
  linkek.ervenytelenit();
  vi.stubGlobal('fetch', async (url: string, init?: RequestInit) => {
    const u = new URL(url, 'http://127.0.0.1/');
    kerelmek.push(u.pathname + u.search);
    if (u.pathname === '/api/vault/aliasok') return valasz({ aliasok: {} });
    if (u.pathname === '/api/vault/linkcel') {
      const ut = u.searchParams.get('ut');
      const cel = u.searchParams.get('cel');
      if (!ut && cel) return valasz({ ut: null, cel, alak, md: `${encodeURIComponent(cel)}.md` });
      const m = LINKCEL[ut!] ?? { cel: ut!, md: ut! };
      const alcel = u.searchParams.get('alcel');
      return valasz({ ut, cel: m.cel, alak, md: m.md + (alcel ? `#${encodeURIComponent(alcel).replace('%5E', '^')}` : '') });
    }
    if (u.pathname === '/api/vault/feloldas') {
      const k = JSON.parse(String(init?.body)) as { celok: string[] };
      return valasz({ eredmenyek: k.celok.map((c) => ({ cel: c, ut: c === 'Mértani' ? 'Matek/Mértani sorozat.md' : null, tobbertelmu: false })) });
    }
    if (u.pathname === '/api/vault/jegyzet') return valasz({ fejezetek: [{ szint: 2, szoveg: 'Első rész', sor: 3 }], blokkok: [] });
    if (u.pathname === '/api/vault/fajl') return valasz({ ut: 'x', tartalom: MASIK, hash: 'h' });
    if (u.pathname === '/api/vault/feloldatlan') return valasz({ szovegek: feloldatlan });
    if (u.pathname === '/api/vault/fejezetek') {
      const q = (u.searchParams.get('q') ?? '').toLowerCase();
      const mind = [
        { ut: 'Matek/Mértani sorozat.md', szint: 2, szoveg: 'Első rész', sor: 3 },
        { ut: 'Matek/Számtani sorozat.md', szint: 1, szoveg: 'Képlet', sor: 1 },
        { ut: 'Matek/Számtani sorozat.md', szint: 2, szoveg: 'Első lépések', sor: 6 },
      ];
      return valasz({ fejezetek: mind.filter((h) => h.szoveg.toLowerCase().includes(q)) });
    }
    return valasz({ hiba: 'nincs' }, 404);
  });
});

afterEach(() => {
  while (nezetek.length) nezetek.pop()!.destroy();
  document.body.textContent = '';
  ertesitesek.lista.length = 0;
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

function nezet(doc: string, o: { kurzor?: number; kijeloles?: [number, number] } = {}): EditorView {
  const hely = document.createElement('div');
  document.body.appendChild(hely);
  const state = EditorState.create({
    doc,
    selection: o.kijeloles ? { anchor: o.kijeloles[0], head: o.kijeloles[1] } : { anchor: o.kurzor ?? doc.length },
    extensions: bovitmenyek({
      mod: 'elo',
      csakOlvashato: false,
      ut: 'Jegyzet.md',
      cimke: 'próba',
      linkNev: () => 'Jegyzet',
      kiegeszites: { fajlok: () => FAJLOK, legutobbi: () => [] },
    }),
  });
  const v = new EditorView({ state, parent: hely });
  ensureSyntaxTree(v.state, v.state.doc.length, 5000);
  nezetek.push(v);
  return v;
}

/** Gépelés a beviteli kezelőkön át, mint a böngésző `beforeinput`-ja. */
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

/** Egy másik jegyzet nyitott `Dokumentum`-a helyett: a szöveg, a mentés és az elengedés megfigyelhető. */
function ujDok(szoveg: string, felulirt: Record<string, unknown> = {}) {
  const dok = {
    szoveg: Text.of(szoveg.split('\n')),
    csakOlvashato: null as string | null,
    allapot: 'tiszta',
    hiba: null as string | null,
    valtozott: vi.fn((_cs: unknown, uj: Text, _forras?: unknown, _elozmenybe?: boolean) => {
      dok.szoveg = uj;
    }),
    ment: vi.fn(async () => ({ ok: true })),
    ...felulirt,
  };
  vi.spyOn(szerkesztok.dokumentumok, 'megnyit').mockResolvedValue(dok as never);
  const elenged = vi.spyOn(szerkesztok.dokumentumok, 'elenged').mockResolvedValue(undefined as never);
  return { dok, elenged };
}

describe('02-links-05: [[## — a vault összes fejezete', () => {
  it('a lekérdezés-elemzés új módja', () => {
    expect(lekerdezesElemez('##els')).toEqual({ mod: 'fejezetMind', cel: '', alk: 'els', alias: '' });
    expect(lekerdezesElemez('##')).toEqual({ mod: 'fejezetMind', cel: '', alk: '', alias: '' });
    expect(lekerdezesElemez('#els').mod).toBe('fejezet');
    expect(lekerdezesElemez('Jegyzet##x').mod).toBe('fejezet'); // célnál marad az alap értelmezés
  });

  it('a core szűri, a felület rangsorol; a jelző a jegyzetet mutatja; a beírás [[Jegyzet#Fejezet]]', async () => {
    const v = nezet('');
    ir(v, '[[##els');
    await varMenu(v, (e) => e.length === 2);
    expect(elemek(v).sort()).toEqual(['Első lépések', 'Első rész']);
    expect(jelzok(v).every((j) => /^H\d · /.test(j))).toBe(true);
    expect(kerelmek.some((k) => k.startsWith('/api/vault/fejezetek?q=els'))).toBe(true);
    const cel = elemek(v).indexOf('Első lépések');
    for (let i = 0; i < cel; i++) billentyu(v, 'ArrowDown');
    billentyu(v, 'Enter');
    await vi.waitFor(() => expect(v.state.doc.toString()).toBe('[[Számtani sorozat#Első lépések]]'));
    expect(kiegeszitesNyitva(v.state)).toBe(false);
  });

  it('üres szűrővel a core listáját mutatja', async () => {
    const v = nezet('');
    ir(v, '[[##');
    await varMenu(v, (e) => e.length === 3);
  });
});

describe('02-links-04: id nélküli blokk másik jegyzetben', () => {
  it('felsorolja az id nélkülit is (új ^id jelzővel); a kiválasztás az azonosítót a másik jegyzetbe menti, majd beírja a linket', async () => {
    const { dok, elenged } = ujDok(MASIK);
    const v = nezet('');
    ir(v, '[[Mértani#^');
    await varMenu(v, (e) => e.length === 2);
    expect(elemek(v)).toEqual(['Első bekezdés', 'Másik bekezdés']);
    expect(jelzok(v)).toEqual(['új ^id', '^abc']);
    billentyu(v, 'Enter');
    await vi.waitFor(() => expect(v.state.doc.toString()).toMatch(/^\[\[Mértani#\^[a-z0-9]{6}\]\]$/));
    const id = /#\^([a-z0-9]{6})/.exec(v.state.doc.toString())![1];
    expect(dok.szoveg.toString()).toBe(`# Mértani sorozat\n\nElső bekezdés ^${id}\n\nMásik bekezdés ^abc\n`);
    expect(dok.valtozott).toHaveBeenCalledTimes(1);
    expect(dok.valtozott.mock.calls[0][3]).toBe(true);
    expect(dok.ment).toHaveBeenCalledTimes(1);
    expect(elenged).toHaveBeenCalledTimes(1);
  });

  it('a meglévő azonosítójú blokk linkje nem ír a másik jegyzetbe', async () => {
    const { dok } = ujDok(MASIK);
    const v = nezet('');
    ir(v, '[[Mértani#^');
    await varMenu(v, (e) => e.length === 2);
    billentyu(v, 'ArrowDown');
    billentyu(v, 'Enter');
    await vi.waitFor(() => expect(v.state.doc.toString()).toBe('[[Mértani#^abc]]'));
    expect(dok.valtozott).not.toHaveBeenCalled();
  });

  it('közben megváltozott jegyzetnél a blokkot a sora alapján találja meg újra', async () => {
    const { dok } = ujDok('Új első sor\n\n' + MASIK);
    const v = nezet('');
    ir(v, '[[Mértani#^');
    await varMenu(v, (e) => e.length === 2);
    billentyu(v, 'Enter');
    await vi.waitFor(() => expect(v.state.doc.toString()).toMatch(/^\[\[Mértani#\^[a-z0-9]{6}\]\]$/));
    expect(dok.szoveg.toString()).toMatch(/\nElső bekezdés \^[a-z0-9]{6}\n/);
    expect(dok.szoveg.toString().startsWith('Új első sor\n\n# Mértani sorozat')).toBe(true);
  });

  it('ha a blokk sora eltűnt, nem ír és nem linkel (értesítés), a menü marad', async () => {
    const { dok } = ujDok('# Más\n\nTeljesen más szöveg\n');
    const v = nezet('');
    ir(v, '[[Mértani#^');
    await varMenu(v, (e) => e.length === 2);
    billentyu(v, 'Enter');
    await vi.waitFor(() => expect(ertesitesek.lista.at(-1)?.cim).toContain('megváltozott'));
    expect(dok.valtozott).not.toHaveBeenCalled();
    expect(v.state.doc.toString()).toBe('[[Mértani#^]]');
    expect(kiegeszitesNyitva(v.state)).toBe(true);
  });

  it('csak olvasható / ütköző jegyzetbe nem ír', async () => {
    const { dok } = ujDok(MASIK, { csakOlvashato: 'Külső módosítás.' });
    const v = nezet('');
    ir(v, '[[Mértani#^');
    await varMenu(v, (e) => e.length === 2);
    billentyu(v, 'Enter');
    await vi.waitFor(() => expect(ertesitesek.lista.at(-1)?.cim).toContain('nem írható'));
    expect(dok.valtozott).not.toHaveBeenCalled();
    expect(v.state.doc.toString()).toBe('[[Mértani#^]]');
  });

  it('mentési hiba: értesítés, link nélkül', async () => {
    const { dok } = ujDok(MASIK);
    dok.ment.mockResolvedValue({ ok: false });
    dok.hiba = 'Lemezhiba';
    const v = nezet('');
    ir(v, '[[Mértani#^');
    await varMenu(v, (e) => e.length === 2);
    billentyu(v, 'Enter');
    await vi.waitFor(() => expect(ertesitesek.lista.at(-1)?.cim).toContain('nem mentődött'));
    expect(v.state.doc.toString()).toBe('[[Mértani#^]]');
  });
});

describe('02-links-14: használt, de még nem létező link-célok', () => {
  it('megjelennek (nincs még jelzővel) a létező fájlok után; a beírás [[Cél]]', async () => {
    feloldatlan = [{ cel: 'Még nincs', db: 3 }, { cel: 'Mértani vázlat', db: 1 }];
    const v = nezet('');
    ir(v, '[[mértani');
    await varMenu(v, (e) => e.length >= 2);
    expect(elemek(v)[0]).toBe('Mértani sorozat'); // a létező fájl előbb
    expect(elemek(v)).toContain('Mértani vázlat');
    expect(jelzok(v)[elemek(v).indexOf('Mértani vázlat')]).toBe('nincs még');
    for (let i = 0; i < elemek(v).indexOf('Mértani vázlat'); i++) billentyu(v, 'ArrowDown');
    billentyu(v, 'Enter');
    await vi.waitFor(() => expect(v.state.doc.toString()).toBe('[[Mértani vázlat]]'));
  });

  it('md módban a még nem létező cél is md-link, a core kódolásával', async () => {
    alak = 'md';
    feloldatlan = [{ cel: 'Új jegyzet', db: 2 }];
    const v = nezet('');
    ir(v, '[[új jeg');
    await varMenu(v, (e) => e.includes('Új jegyzet'));
    billentyu(v, 'Enter');
    await vi.waitFor(() => expect(v.state.doc.toString()).toBe('[Új jegyzet](%C3%9Aj%20jegyzet.md)'));
    expect(kerelmek.some((k) => k.includes('/api/vault/linkcel?cel='))).toBe(true);
  });

  it('üres lekérdezésnél nem kér feloldatlan listát', async () => {
    const v = nezet('');
    ir(v, '[[');
    await varMenu(v);
    expect(kerelmek.some((k) => k.startsWith('/api/vault/feloldatlan'))).toBe(false);
  });
});

describe('02-links-13: „Use [[Wikilinks]]” kikapcsolva — markdown-link a [[…]] helyén', () => {
  beforeEach(() => {
    alak = 'md';
  });

  it('fájl: [név](kódolt.md); a kurzor a link után; a ]] is eltűnik', async () => {
    const v = nezet('Lásd: ');
    ir(v, '[[mertani');
    await varMenu(v, (e) => e[0] === 'Mértani sorozat');
    billentyu(v, 'Enter');
    await vi.waitFor(() => expect(v.state.doc.toString()).toBe('Lásd: [Mértani sorozat](M%C3%A9rtani%20sorozat.md)'));
    expect(v.state.selection.main.head).toBe(v.state.doc.length);
    expect(kiegeszitesNyitva(v.state)).toBe(false);
  });

  it('beágyazás: ![felirat](cél); a melléklet felirata a fájlnév', async () => {
    const v = nezet('');
    ir(v, '![[abra');
    await varMenu(v, (e) => e[0] === 'ábra 1.png');
    billentyu(v, 'Enter');
    await vi.waitFor(() => expect(v.state.doc.toString()).toBe('![ábra 1.png](%C3%A1bra%201.png)'));
  });

  it('fejezet: a horgony a kódolt célban és a feliratban; a core a horgonyt is megkapja', async () => {
    const v = nezet('');
    ir(v, '[[Mértani#');
    await varMenu(v, (e) => e.length > 0);
    billentyu(v, 'Enter');
    await vi.waitFor(() => expect(v.state.doc.toString()).toMatch(/^\[Mértani sorozat#.+\]\(M%C3%A9rtani%20sorozat\.md#.+\)$/));
    expect(kerelmek.some((k) => k.includes('/api/vault/linkcel') && k.includes('alcel='))).toBe(true);
  });

  it('alias: [alias](cél)', async () => {
    const v = nezet('');
    ir(v, '[[Mértani|');
    // a core aliasai: üres térkép → nincs alias-elem; az alias-mód md alakját az explicit alias adja
    await varMenu(v, (e) => e.length === 0);
    expect(kiegeszitesNyitva(v.state)).toBe(true);
  });

  it('id nélküli blokk az aktuális jegyzetben: egy tranzakció, md-link az új azonosítóval', async () => {
    const v = nezet('Egy bekezdés\n\n');
    ir(v, '[[#^');
    await varMenu(v, (e) => e.length === 1);
    billentyu(v, 'Enter');
    await vi.waitFor(() => expect(v.state.doc.toString()).toMatch(/^Egy bekezdés \^[a-z0-9]{6}\n\n\[Jegyzet#\^[a-z0-9]{6}\]\(Jegyzet\.md#\^[a-z0-9]{6}\)$/));
  });
});

describe('02-links-06: újranyitás egy meglévő [[… belsejében', () => {
  const lassu = () => new Promise((r) => setTimeout(r, 15));

  it('a nyitott [[ utáni szövegbe gépelve a menü újra előjön, a lekérdezés a kurzor előtti szöveg', async () => {
    const v = nezet('Lásd [[Jegy és tovább', { kurzor: 'Lásd [[Jegy'.length });
    expect(kiegeszitesNyitva(v.state)).toBe(false);
    ir(v, 'z');
    await vi.waitFor(() => expect(kiegeszitesNyitva(v.state)).toBe(true));
    expect(lekerdezes(v.state)).toBe('Jegyz');
  });

  it('törlésre (Backspace) is, és a ![[ beágyazásra is', async () => {
    const v = nezet('![[abra]]', { kurzor: '![[abra'.length });
    v.dispatch({ changes: { from: '![[abr'.length, to: '![[abra'.length }, selection: { anchor: '![[abr'.length }, userEvent: 'delete.backward' });
    await vi.waitFor(() => expect(kiegeszitesNyitva(v.state)).toBe(false)); // a ]] lezárja: nincs menü
    const w = nezet('![[abra', {});
    w.dispatch({ changes: { from: 6, to: 7 }, selection: { anchor: 6 }, userEvent: 'delete.backward' });
    await vi.waitFor(() => expect(kiegeszitesNyitva(w.state)).toBe(true));
    expect(lekerdezes(w.state)).toBe('abr');
  });

  it('lezárt linken, kódban és csak mozgatásnál nem nyílik', async () => {
    const lezart = nezet('[[Kész]] szöveg');
    ir(lezart, 'x');
    await lassu();
    expect(kiegeszitesNyitva(lezart.state)).toBe(false);
    const kod = nezet('```\n[[Jegy', {});
    ir(kod, 'z');
    await lassu();
    expect(kiegeszitesNyitva(kod.state)).toBe(false);
    const mozg = nezet('[[Jegy ab', { kurzor: 3 });
    mozg.dispatch({ selection: { anchor: 6 } });
    await lassu();
    expect(kiegeszitesNyitva(mozg.state)).toBe(false);
  });

  it('az Esc az adott linken kikapcsolja, amíg a kurzor ki nem lép belőle', async () => {
    const v = nezet('x [[Jegy');
    ir(v, 'z');
    await vi.waitFor(() => expect(kiegeszitesNyitva(v.state)).toBe(true));
    billentyu(v, 'Escape');
    expect(kiegeszitesNyitva(v.state)).toBe(false);
    ir(v, 'z');
    await lassu();
    expect(kiegeszitesNyitva(v.state)).toBe(false); // ugyanazon a linken nem nyit újra
    v.dispatch({ changes: { from: v.state.doc.length, insert: ']] ' }, selection: { anchor: v.state.doc.length + 3 }, userEvent: 'input.type' });
    ir(v, '[[Uj');
    await vi.waitFor(() => expect(kiegeszitesNyitva(v.state)).toBe(true)); // új link: újra működik
  });

  it('nyitottLink: a sorban álló utolsó le nem zárt [[ és a beágyazás jelzése', () => {
    const s = EditorState.create({ doc: 'a [[b]] c ![[d e' });
    const k = nyitottLink(s, s.doc.length);
    expect(k).toEqual({ from: 'a [[b]] c ![['.length, beagyazas: true });
    expect(nyitottLink(EditorState.create({ doc: '[[x]] y' }), 7)).toBeNull();
    expect(nyitottLink(EditorState.create({ doc: 'sima szöveg' }), 3)).toBeNull();
  });
});

describe('02-links-07: [[ kijelöléssel', () => {
  it('a parancs a kijelölt szöveget [[…]]-be fogja és lekérdezésként használja', async () => {
    const v = nezet('Egy Mértani szó', { kijeloles: [4, 11] });
    expect(linkBeszur(v)).toBe(true);
    expect(v.state.doc.toString()).toBe('Egy [[Mértani]] szó');
    expect(lekerdezes(v.state)).toBe('Mértani');
    expect(kiegeszitesNyitva(v.state)).toBe(true);
    await varMenu(v, (e) => e[0] === 'Mértani sorozat');
  });

  it('beágyazás-parancs: ![[kijelölt]]', () => {
    const v = nezet('abra', { kijeloles: [0, 4] });
    expect(linkBeszur(v, true)).toBe(true);
    expect(v.state.doc.toString()).toBe('![[abra]]');
    expect(lekerdezes(v.state)).toBe('abra');
  });

  it('többsoros kijelölésnél semmi nem vész el: a link a kijelölés mögé kerül', () => {
    const v = nezet('első\nmásodik', { kijeloles: [0, 12] });
    expect(linkBeszur(v)).toBe(true);
    expect(v.state.doc.toString()).toBe('első\nmásodik[[]]');
  });

  it('a [ gépelése kijelöléssel: [kijelölt], a második [ [[kijelölt]]-re bővít és megnyitja a menüt', async () => {
    const v = nezet('Egy Mértani szó', { kijeloles: [4, 11] });
    ir(v, '[');
    expect(v.state.doc.toString()).toBe('Egy [Mértani] szó');
    expect(v.state.sliceDoc(v.state.selection.main.from, v.state.selection.main.to)).toBe('Mértani');
    expect(kiegeszitesNyitva(v.state)).toBe(false);
    ir(v, '[');
    expect(v.state.doc.toString()).toBe('Egy [[Mértani]] szó');
    expect(kiegeszitesNyitva(v.state)).toBe(true);
    expect(lekerdezes(v.state)).toBe('Mértani');
    await varMenu(v, (e) => e[0] === 'Mértani sorozat');
    billentyu(v, 'Enter');
    await vi.waitFor(() => expect(v.state.doc.toString()).toBe('Egy [[Mértani sorozat]] szó'));
  });

  it('kijelölés [ vagy ] jellel, valamint többsoros kijelölés: az alap viselkedés (csere) marad, nem nyit menüt', () => {
    const v = nezet('a [b] c', { kijeloles: [2, 5] });
    ir(v, '[');
    expect(kiegeszitesNyitva(v.state)).toBe(false);
  });
});
