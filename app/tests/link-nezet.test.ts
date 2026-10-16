// A link a szerkesztőben és a navigáció (C10), jsdom-ban: a Live Preview a kirajzolt linket mutatja (alias vagy
// cél › horgony, a `[[ ]]` rejtve, az aktív sorban a forrás), az egyedül álló `![[…]]` blokk-widget, a sor közepén
// álló inline; `linkAt`/`kurzorLinkMegnyit`; és a `linkMegnyit` ágai: feloldott fájl, fejezetre ugrás, média-horgony,
// hiányzó cél (új jegyzet), hibás válasz. A kattintás pozíció-geometriáját a böngészős kör méri.

import { ensureSyntaxTree } from '@codemirror/language';
import { EditorState } from '@codemirror/state';
import { EditorView } from '@codemirror/view';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { ertesitesek } from '../src/lib/ertesites/ertesites.svelte';
import { linkek } from '../src/lib/vault/linkek.svelte';
import { bovitmenyek } from '../src/szerkeszto/beallitas';
import { linkAt, kurzorLinkMegnyit } from '../src/szerkeszto/linkek/szerkeszto';
import { jegyzetLetrehoz, linkMegnyit, navigacioBeallit, nyitasMod } from '../src/szerkeszto/linkek/navigacio';
import { szerkesztok } from '../src/szerkeszto/szerkesztok.svelte';

type Valasz = Record<string, unknown>;
let tabla: Record<string, Valasz>;
let kerelmek: { url: string; body?: unknown }[];
const nezetek: EditorView[] = [];
const megnyitasok: { ut: string; mod: string; horgony?: string | null }[] = [];

function valasz(adat: unknown, kod = 200) {
  return new Response(JSON.stringify(adat), { status: kod, headers: { 'Content-Type': 'application/json' } });
}

beforeEach(() => {
  tabla = {};
  kerelmek = [];
  megnyitasok.length = 0;
  linkek.mediaToken = 'tok';
  navigacioBeallit({ megnyit: (ut, mod, horgony) => megnyitasok.push({ ut, mod, horgony }), mappak: () => ['Matek', 'Matek/Sorozatok'] });
  vi.stubGlobal('fetch', async (url: string, init?: RequestInit) => {
    const u = new URL(url, 'http://127.0.0.1/');
    kerelmek.push({ url: u.pathname + u.search, body: init?.body ? JSON.parse(String(init.body)) : undefined });
    if (u.pathname === '/api/vault/beagyazas') {
      const k = `${u.searchParams.get('forras')}|${u.searchParams.get('cel')}|${u.searchParams.get('alcel') ?? ''}`;
      return valasz(tabla[k] ?? { tipus: 'nincs', cel: u.searchParams.get('cel') });
    }
    if (u.pathname === '/api/vault/uj') {
      // a core helyett: az útvonalas cél a gyökérhez képest, az út nélküli a gyökérbe (C31, T158)
      const cel: string = JSON.parse(String(init?.body)).link.cel;
      return valasz({ ok: true, ut: `${cel.replace(/\.md$/i, '')}.md` }, 201);
    }
    return valasz({ hiba: 'nincs' }, 404);
  });
});

afterEach(() => {
  while (nezetek.length) nezetek.pop()!.destroy();
  document.body.textContent = '';
  navigacioBeallit(null);
  ertesitesek.lista.length = 0;
  vi.unstubAllGlobals();
});

function nezet(doc: string, kurzor = doc.length): EditorView {
  const hely = document.createElement('div');
  document.body.appendChild(hely);
  const state = EditorState.create({
    doc,
    selection: { anchor: kurzor },
    extensions: bovitmenyek({ mod: 'elo', csakOlvashato: false, ut: 'Matek/Fő.md', cimke: 'próba' }),
  });
  const v = new EditorView({ state, parent: hely });
  ensureSyntaxTree(v.state, v.state.doc.length, 5000);
  nezetek.push(v);
  return v;
}

describe('a kirajzolt link a Live Preview-ban', () => {
  it('az alias, vagy a cél › horgony látszik, a [[ ]] rejtve; az aktív sorban a forrás', () => {
    const doc = 'Lásd [[Mértani#Képlet|a képlet]] és [[Cél#Rész]] és [[Egyszerű]].\n\nmásik sor';
    const v = nezet(doc, doc.length);
    const szoveg = v.dom.querySelector('.cm-line')!.textContent!;
    expect(szoveg).toContain('a képlet');
    expect(szoveg).toContain('Cél › Rész');
    expect(szoveg).toContain('Egyszerű');
    expect(szoveg).not.toContain('[[');
    expect(szoveg).not.toContain('Mértani');
    v.dispatch({ selection: { anchor: 3 } });
    expect(v.dom.querySelector('.cm-line')!.textContent).toContain('[[Mértani#Képlet|a képlet]]');
  });
});

describe('a beágyazás widget a Live Preview-ban', () => {
  it('egyedül álló sor: blokk-widget a tartalommal; az aktív sorban forrás és alatta előnézet', async () => {
    tabla['Matek/Fő.md|Cél|'] = { tipus: 'jegyzet', ut: 'Cél.md', szoveg: '# Cél címe\n\nSzöveg.\n' };
    const doc = 'Előtte\n\n![[Cél]]\n\nUtána';
    const v = nezet(doc, doc.length);
    await vi.waitFor(() => expect(v.dom.querySelector('.cm-beagyazas .beagyazas-jegyzet h1')?.textContent).toBe('Cél címe'));
    expect(v.dom.querySelector('.cm-beagyazas-sorban')).toBeNull();
    expect(v.dom.textContent).not.toContain('![[Cél]]');
    v.dispatch({ selection: { anchor: doc.indexOf('![[') + 2 } });
    await vi.waitFor(() => expect(v.dom.querySelector('.cm-beagyazas .beagyazas-jegyzet h1')?.textContent).toBe('Cél címe'));
    expect(v.dom.textContent).toContain('![[Cél]]');
  });

  it('sor közepén: inline widget; a kép marad, a jegyzet link-chip', async () => {
    tabla['Matek/Fő.md|kep.png|'] = { tipus: 'kep', ut: 'kep.png' };
    tabla['Matek/Fő.md|Cél|'] = { tipus: 'jegyzet', ut: 'Cél.md', szoveg: 'x' };
    const doc = 'szöveg ![[kep.png]] közben ![[Cél]] vége\n\nmásik';
    const v = nezet(doc, doc.length);
    await vi.waitFor(() => expect(v.dom.querySelectorAll('.cm-beagyazas-sorban')).toHaveLength(2));
    await vi.waitFor(() => expect(v.dom.querySelector('.cm-beagyazas-sorban img.beagyazas-kep')).not.toBeNull());
    await vi.waitFor(() => expect(v.dom.querySelector('.cm-beagyazas-sorban .beagyazas-chip')).not.toBeNull());
  });

  it('a fájlszerkezet változása (új fájl) újra feloldja a függő beágyazást', async () => {
    const doc = '![[Később]]\n\nvég';
    const v = nezet(doc, doc.length);
    await vi.waitFor(() => expect(v.dom.querySelector('.beagyazas-hianyzo')).not.toBeNull());
    tabla['Matek/Fő.md|Később|'] = { tipus: 'jegyzet', ut: 'Később.md', szoveg: 'megjött' };
    linkek.ervenytelenit();
    v.dispatch({ effects: (await import('../src/szerkeszto/beagyazas/widget')).linkVerzioValt.of(linkek.verzio) });
    await vi.waitFor(() => expect(v.dom.querySelector('.beagyazas-jegyzet')?.textContent).toContain('megjött'));
  });
});

describe('linkAt és a kurzornál álló link', () => {
  it('a kurzornál (és a határokon) álló link adatai', () => {
    const doc = 'a [[Cél#Rész|szöveg]] b ![[kep.png]]';
    const v = nezet(doc, 6);
    expect(linkAt(v.state, 6)).toMatchObject({ cel: 'Cél', alcel: 'Rész', alias: 'szöveg', beagyazas: false });
    expect(linkAt(v.state, 2)).not.toBeNull();
    expect(linkAt(v.state, 21)).not.toBeNull();
    expect(linkAt(v.state, 0)).toBeNull();
    expect(linkAt(v.state, doc.length - 3)).toMatchObject({ cel: 'kep.png', beagyazas: true });
  });

  it('kurzorLinkMegnyit: a forrás a jegyzet útja, a mód átadva', async () => {
    tabla['Matek/Fő.md|Cél|'] = { tipus: 'jegyzet', ut: 'Matek/Cél.md', szoveg: '', kezd: 1 };
    const v = nezet('a [[Cél]] b', 5);
    expect(kurzorLinkMegnyit(v, 'ujful')).toBe(true);
    await vi.waitFor(() => expect(megnyitasok).toEqual([{ ut: 'Matek/Cél.md', mod: 'ujful', horgony: null }]));
    const w = nezet('nincs link', 3);
    expect(kurzorLinkMegnyit(w)).toBe(false);
  });
});

describe('linkMegnyit', () => {
  it('a módosítók: ⌘ új fül, ⌘⌥ osztás', () => {
    expect(nyitasMod({ metaKey: false, ctrlKey: false, altKey: false })).toBe('aktiv');
    expect(nyitasMod({ metaKey: true, ctrlKey: false, altKey: false })).toBe('ujful');
    expect(nyitasMod({ metaKey: true, ctrlKey: false, altKey: true })).toBe('osztas');
  });

  it('fejezetre ugrás: megnyit, és a sort a szerkesztőnek adja', async () => {
    tabla['Fő.md|Cél|Rész'] = { tipus: 'jegyzet', ut: 'Cél.md', alcel: 'Rész', szoveg: '## Rész', kezd: 7, veg: 9 };
    await linkMegnyit({ forras: 'Fő.md', cel: 'Cél', alcel: 'Rész' });
    expect(megnyitasok).toEqual([{ ut: 'Cél.md', mod: 'aktiv', horgony: null }]);
    expect(szerkesztok.fuggoUgrasKap('Cél.md')).toEqual({ sor: 7, oszlop: undefined });
  });

  it('a jegyzet saját fejezetére (üres cél) csak ugrik, nem nyit', async () => {
    tabla['Fő.md|Fő.md|Rész'] = { tipus: 'jegyzet', ut: 'Fő.md', alcel: 'Rész', szoveg: '## Rész', kezd: 12, veg: 14 };
    await linkMegnyit({ forras: 'Fő.md', cel: '', alcel: 'Rész' });
    expect(megnyitasok).toEqual([]);
    expect(szerkesztok.fuggoUgrasKap('Fő.md')).toEqual({ sor: 12, oszlop: undefined });
  });

  it('hibás fejezet: megnyit, de figyelmeztet', async () => {
    tabla['Fő.md|Cél|Nincs'] = { tipus: 'jegyzet', ut: 'Cél.md', alcel_hiba: true, szoveg: '' };
    await linkMegnyit({ forras: 'Fő.md', cel: 'Cél', alcel: 'Nincs' });
    expect(megnyitasok).toHaveLength(1);
    expect(szerkesztok.fuggoUgrasKap('Cél.md')).toBeNull();
    expect(ertesitesek.lista.at(-1)!.cim).toContain('horgony');
  });

  it('PDF-oldal és videó-időpont: a horgony a nézetnek átadva', async () => {
    tabla['Fő.md|d.pdf|page=5'] = { tipus: 'pdf', ut: 'd.pdf', alcel: 'page=5' };
    tabla['Fő.md|v.mp4|t=12'] = { tipus: 'video', ut: 'v.mp4', alcel: 't=12' };
    await linkMegnyit({ forras: 'Fő.md', cel: 'd.pdf', alcel: 'page=5' });
    await linkMegnyit({ forras: 'Fő.md', cel: 'v.mp4', alcel: 't=12' });
    expect(megnyitasok.map((m) => [m.ut, m.horgony])).toEqual([['d.pdf', 'page=5'], ['v.mp4', 't=12']]);
  });

  it('feloldatlan link: a helyet a core dönti (a nyers cél és a forrás megy), az új jegyzet megnyílik', async () => {
    await linkMegnyit({ forras: 'Matek/Fő.md', cel: 'Új ötlet' });
    expect(kerelmek.find((k) => k.url === '/api/vault/uj')!.body).toEqual({ link: { cel: 'Új ötlet', forras: 'Matek/Fő.md' } });
    expect(megnyitasok).toEqual([{ ut: 'Új ötlet.md', mod: 'aktiv', horgony: undefined }]);
    megnyitasok.length = 0;
    await linkMegnyit({ forras: 'Fő.md', cel: 'matek/Új mappa/Q' }, 'ujful');
    expect(kerelmek.filter((k) => k.url === '/api/vault/uj')[1].body).toEqual({ link: { cel: 'matek/Új mappa/Q', forras: 'Fő.md' } });
    expect(megnyitasok[0].ut).toBe('matek/Új mappa/Q.md');
  });

  it('hiányzó médiához nem készül jegyzet; a hibás név értesítést ad', async () => {
    expect(await jegyzetLetrehoz('Fő.md', 'nincs.png')).toBeNull();
    expect(await jegyzetLetrehoz('Fő.md', 'v1.2')).toBe('v1.2.md'); // a „v1.2” jegyzetnév, nem kiterjesztés
    vi.stubGlobal('fetch', async () => valasz({ hiba: 'érvénytelen név' }, 400));
    expect(await jegyzetLetrehoz('Fő.md', 'Rossz#név')).toBeNull();
    expect(ertesitesek.lista.at(-1)!.szoveg).toContain('érvénytelen név');
  });

  it('a core hibája értesítést ad, nem dob', async () => {
    vi.stubGlobal('fetch', async () => valasz({ hiba: 'az index épül' }, 503));
    await linkMegnyit({ forras: 'Fő.md', cel: 'X' });
    expect(megnyitasok).toEqual([]);
    expect(ertesitesek.lista.at(-1)!.cim).toBe('A link nem oldható fel');
  });
});
