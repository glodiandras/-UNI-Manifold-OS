// A jobb panel (C10), jsdom-ban, ál-core-ral: visszahivatkozások forrásonként a link sorával, linkeletlen említések
// (egy kattintás = link a másik jegyzetben, a `Dokumentum` úton, elavult pozíción nem ír), kimenő linkek (külön a
// feloldatlanok), az élő vázlat, a lekérés és a WS-re újratöltés.

import { cleanup, fireEvent, render, waitFor } from '@testing-library/svelte';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { CoreKapcsolat } from '../src/lib/core/ws.svelte';
import { Felulet } from '../src/lib/elrendezes/felulet.svelte';
import { ertesitesek } from '../src/lib/ertesites/ertesites.svelte';
import { KORNYEZET_KULCS } from '../src/lib/kornyezet';
import { VaultFajlok } from '../src/lib/vault/fajlok.svelte';
import { Kapcsolatok, kornyezetReszek } from '../src/lib/vault/kapcsolatok.svelte';
import JobbPanel from '../src/hej/JobbPanel.svelte';
import { emlitesLink, emlitesLinkel } from '../src/szerkeszto/linkek/emlites';
import { szerkesztok } from '../src/szerkeszto/szerkesztok.svelte';
import { navigacioBeallit } from '../src/szerkeszto/linkek/navigacio';

const KORNYEZETI_SOR = 'A mértani sorozat hányadosa állandó, a Mértani sorozat fogalma fontos.';
let lemez: Map<string, string>;
let kerelmek: string[];
let irasok: { ut: string; tartalom: string; elso: boolean; pillanat: boolean }[];
let vissza: Record<string, unknown>;
let emlit: Record<string, unknown>;
let jegyzet: Record<string, unknown>;

const hash = (s: string) => `h${s.length}:${[...s].reduce((h, c) => (h * 31 + c.charCodeAt(0)) | 0, 7)}`;
function valasz(adat: unknown, kod = 200) {
  return new Response(JSON.stringify(adat), { status: kod, headers: { 'Content-Type': 'application/json' } });
}

beforeEach(() => {
  kerelmek = [];
  irasok = [];
  lemez = new Map([['Matek/Mértani sorozat.md', '# Mértani sorozat\n'], ['Történelem/Ókor.md', `# Ókor\n\n${KORNYEZETI_SOR}\nvége\n`]]);
  vissza = {
    forrasok: [
      { ut: 'Matek/Számtani.md', linkek: [{ fajta: 'wiki', sor: 3, oszlop: 5, hossz: 19, alcel: null, alias: null, beagyazas: false, tulajdonsag: null, csomopont: null, kornyezet: 'Lásd [[Mértani sorozat]] is.' }] },
      { ut: 'X03 - Könyvek/Könyv.md', linkek: [{ fajta: 'wiki', sor: 2, oszlop: 9, hossz: 21, alcel: 'page=3', alias: null, beagyazas: false, tulajdonsag: 'Source', csomopont: null, kornyezet: 'Source: "[[m.pdf#page=3]]"' }, { fajta: 'wiki', sor: 9, oszlop: 0, hossz: 5, alcel: null, alias: null, beagyazas: true, tulajdonsag: null, csomopont: null, kornyezet: '![[x]]' }] },
      { ut: 'Vászon.canvas', linkek: [{ fajta: 'canvas_fajl', sor: null, oszlop: null, hossz: null, alcel: null, alias: null, beagyazas: false, tulajdonsag: null, csomopont: 'n1', kornyezet: null }] },
    ],
  };
  emlit = { forrasok: [{ ut: 'Történelem/Ókor.md', talalatok: [{ sor: 3, oszlop: 2, hossz: 15, szoveg: KORNYEZETI_SOR }, { sor: 3, oszlop: 39, hossz: 15, szoveg: KORNYEZETI_SOR }] }] };
  jegyzet = {
    linkek: [
      { fajta: 'wiki', cel_nyers: 'Számtani', cel: 'Matek/Számtani.md', alcel: 'Képlet', alias: null, beagyazas: false, tulajdonsag: null, sor: 2 },
      { fajta: 'wiki', cel_nyers: 'Számtani', cel: 'Matek/Számtani.md', alcel: 'Képlet', alias: 'másképp', beagyazas: false, tulajdonsag: null, sor: 8 },
      { fajta: 'wiki', cel_nyers: 'Még nincs', cel: null, alcel: null, alias: null, beagyazas: false, tulajdonsag: null, sor: 4 },
      { fajta: 'wiki', cel_nyers: 'kep.png', cel: 'kep.png', alcel: null, alias: null, beagyazas: true, tulajdonsag: null, sor: 5 },
    ],
  };
  vi.stubGlobal('fetch', async (url: string, init?: RequestInit) => {
    const u = new URL(url, 'http://127.0.0.1/');
    kerelmek.push(u.pathname);
    if (u.pathname === '/api/vault/visszahivatkozasok') return valasz(vissza);
    if (u.pathname === '/api/vault/emlitesek') return valasz(emlit);
    if (u.pathname === '/api/vault/jegyzet') return valasz(jegyzet);
    if (u.pathname === '/api/vault/linkcel') return valasz({ ut: 'x', cel: 'Mértani sorozat' });
    if (u.pathname === '/api/vault/uj') return valasz({ ok: true, ut: 'Matek/Még nincs.md' }, 201);
    if (u.pathname === '/api/vault/fajl' && (!init?.method || init.method === 'GET')) {
      const ut = u.searchParams.get('ut')!;
      const t = lemez.get(ut);
      return t === undefined ? valasz({ hiba: 'nincs' }, 404) : valasz({ ut, tartalom: t, hash: hash(t), jel: '', mtime: 0, kodolas_hiba: false });
    }
    if (u.pathname === '/api/vault/fajl' && init?.method === 'PUT') {
      const k = JSON.parse(String(init.body));
      irasok.push(k);
      lemez.set(k.ut, k.tartalom);
      return valasz({ ok: true, ut: k.ut, hash: hash(k.tartalom), jel: '', uzenet: 'mentve', pillanat: null, elotte: null, git: true });
    }
    return valasz({ hiba: 'nincs' }, 404);
  });
});

afterEach(() => {
  cleanup();
  navigacioBeallit(null);
  ertesitesek.lista.length = 0;
  vi.unstubAllGlobals();
});

function panel(ut: string | null = 'Matek/Mértani sorozat.md') {
  const felulet = new Felulet({ csend: { be: false } }); // a mindent mutató felület (C38: csendben a panel alapból zárt)
  if (ut) felulet.munkaterulet.megnyit(ut);
  const kapcsolat = new CoreKapcsolat('ws://127.0.0.1:1/ws');
  const context = new Map<unknown, unknown>([[KORNYEZET_KULCS, { felulet, fajlok: new VaultFajlok(), kapcsolat }]]);
  const r = render(JobbPanel, { context });
  return { ...r, felulet, kapcsolat };
}

describe('a Kapcsolatok tároló', () => {
  it('lekéri a három végpontot; md-n kívül nincs említés', async () => {
    const k = new Kapcsolatok();
    await k.frissit('Matek/Mértani sorozat.md');
    expect(kerelmek.sort()).toEqual(['/api/vault/emlitesek', '/api/vault/jegyzet', '/api/vault/visszahivatkozasok']);
    expect(k.visszahivatkozasok).toHaveLength(3);
    expect(k.emlitesek).toHaveLength(1);
    kerelmek.length = 0;
    await k.frissit('Könyvek/m.pdf');
    expect(kerelmek).toEqual(['/api/vault/visszahivatkozasok']);
    await k.frissit(null);
    expect(k.visszahivatkozasok).toHaveLength(0);
  });

  it('a hiányzó vagy épülő index nem hiba; a gyors váltásnál a régi válasz eldobódik', async () => {
    vi.stubGlobal('fetch', async () => valasz({ hiba: 'az index épül' }, 503));
    const k = new Kapcsolatok();
    await k.frissit('A.md');
    expect(k.hiba).toBeNull();
    expect(k.betolt).toBe(false);
  });

  it('a link kiemelése a környezeti sorban (kódpont-oszlopokkal)', () => {
    expect(kornyezetReszek('Lásd [[Mértani]] is.', 5, 11)).toEqual({ elotte: 'Lásd ', link: '[[Mértani]]', utana: ' is.' });
    expect(kornyezetReszek('😀 [[X]]', 2, 5)).toEqual({ elotte: '😀 ', link: '[[X]]', utana: '' });
    expect(kornyezetReszek('rövid', null, null)).toEqual({ elotte: 'rövid', link: '', utana: '' });
  });
});

describe('a jobb panel', () => {
  it('visszahivatkozások forrásonként, kiemelt linkkel, canvas- és tulajdonság-jelzéssel', async () => {
    const { container } = panel();
    const szakasz = () => container.querySelector('section')!; // az első: a visszahivatkozások
    await waitFor(() => expect(szakasz().querySelectorAll('.forras').length).toBe(3));
    const forrasok = [...szakasz().querySelectorAll('.forras > .fej .nev')].map((e) => e.textContent);
    expect(forrasok).toEqual(['Számtani', 'Könyv', 'Vászon.canvas']);
    expect(szakasz().querySelector('mark')!.textContent).toBe('[[Mértani sorozat]]');
    const jelek = [...szakasz().querySelectorAll('.jel')].map((e) => e.textContent);
    expect(jelek).toEqual(expect.arrayContaining(['Source', 'canvas']));
    expect(szakasz().textContent).toContain('4 link, 3 jegyzetből');
  });

  it('kattintás a linkre: a forrás megnyílik az adott soron', async () => {
    const { container, felulet } = panel();
    await waitFor(() => expect(container.querySelectorAll('.link').length).toBeGreaterThan(0));
    await fireEvent.click(container.querySelector('section .link')!);
    expect(felulet.munkaterulet.aktivFul!.ut).toBe('Matek/Számtani.md');
    expect(szerkesztok.fuggoUgrasKap('Matek/Számtani.md')).toEqual({ sor: 3, oszlop: undefined });
  });

  it('kimenő linkek: egyedi célok, külön a feloldatlan; a feloldatlanra kattintva új jegyzet', async () => {
    const { container, felulet } = panel();
    navigacioBeallit({ megnyit: (ut) => felulet.munkaterulet.megnyit(ut, 'ujful'), mappak: () => ['Matek'] });
    await waitFor(() => expect(container.querySelectorAll('.hianyzo').length).toBe(1));
    const kimeno = container.querySelectorAll('section')[2];
    const nevek = [...kimeno.querySelectorAll('.sor:not(.hianyzo) .nev')].map((e) => e.textContent);
    expect(nevek).toEqual(['Számtani › Képlet', 'kep.png']); // az azonos cél (más aliasszal) egyszer szerepel
    expect(kimeno.querySelector('.sor.hianyzo .nev')!.textContent).toBe('Még nincs');
    expect(kimeno.textContent).toContain('beágyazás');
    await fireEvent.click(kimeno.querySelector('.sor.hianyzo')!);
    await waitFor(() => expect(felulet.munkaterulet.aktivFul!.ut).toBe('Matek/Még nincs.md'));
  });

  it('a vázlat az aktív szerkesztő élő fejezeteit mutatja', async () => {
    const { container } = panel();
    szerkesztok.beallit({
      ut: 'Matek/Mértani sorozat.md',
      nezet: () => null,
      mod: () => 'elo',
      olvasoValt() {},
      forrasValt() {},
      mentes: async () => {},
      pillanatkep: async () => {},
      fokuszban: () => false,
      ugras: vi.fn(),
      vazlat: () => [{ szint: 1, szoveg: 'Cím', sor: 1 }, { szint: 2, szoveg: 'Rész', sor: 4 }],
      valtozat: () => 0,
    });
    await waitFor(() => expect([...container.querySelectorAll('.sor')].some((e) => e.textContent === 'Rész')).toBe(true));
    const rész = [...container.querySelectorAll<HTMLButtonElement>('.sor')].find((e) => e.textContent === 'Rész')!;
    await fireEvent.click(rész);
    expect(szerkesztok.aktiv!.ugras).toHaveBeenCalledWith(4);
    szerkesztok.beallit(null);
  });

  it('nincs megnyitott fájl: üres állapot, nincs lekérés', () => {
    const { container } = panel(null);
    expect(container.textContent).toContain('Nincs megnyitott fájl');
    expect(kerelmek).toEqual([]);
  });
});

describe('linkeletlen említés → link', () => {
  it('a link szövege: pontos névnél [[Cél]], különben [[Cél|szöveg]]', () => {
    expect(emlitesLink('Mértani sorozat', 'Mértani sorozat', 'Mértani sorozat')).toBe('[[Mértani sorozat]]');
    expect(emlitesLink('Mértani sorozat', 'Mértani sorozat', 'mértani sorozat')).toBe('[[Mértani sorozat|mértani sorozat]]');
  });

  it('egy kattintás: a másik jegyzet szövege pontosan az említés helyén változik, mentődik', async () => {
    const t = (emlit.forrasok as { talalatok: unknown[] }[])[0].talalatok[0] as never;
    const ok = await emlitesLinkel('Matek/Mértani sorozat.md', 'Történelem/Ókor.md', t);
    expect(ok).toBe(true);
    expect(lemez.get('Történelem/Ókor.md')).toBe('# Ókor\n\nA [[Mértani sorozat|mértani sorozat]] hányadosa állandó, a Mértani sorozat fogalma fontos.\nvége\n');
    expect(irasok).toHaveLength(2); // a mentés `elso`-val, a lezárás pillanatképpel
    expect(irasok[0]).toMatchObject({ elso: true, pillanat: false });
  });

  it('nyitott szerkesztőnél a link beszúrása az előzménybe kerül: a ⌘Z visszahozza (T028 rokona, C29.7b)', async () => {
    const dok = await szerkesztok.dokumentumok.megnyit('Történelem/Ókor.md');
    const kapott: boolean[] = [];
    const le = dok.csatol({ alkalmaz: (_c, elozmenybe) => void kapott.push(!!elozmenybe) });
    const t = (emlit.forrasok as { talalatok: unknown[] }[])[0].talalatok[0] as never;
    expect(await emlitesLinkel('Matek/Mértani sorozat.md', 'Történelem/Ókor.md', t)).toBe(true);
    expect(kapott).toEqual([true]);
    le();
    szerkesztok.dokumentumok.eldob('Történelem/Ókor.md');
  });

  it('a második említés (pontos név) [[Cél]] alakot kap', async () => {
    const t = (emlit.forrasok as { talalatok: unknown[] }[])[0].talalatok[1] as never;
    expect(await emlitesLinkel('Matek/Mértani sorozat.md', 'Történelem/Ókor.md', t)).toBe(true);
    expect(lemez.get('Történelem/Ókor.md')).toBe('# Ókor\n\nA mértani sorozat hányadosa állandó, a [[Mértani sorozat]] fogalma fontos.\nvége\n');
  });

  it('elavult pozíción (a sor megváltozott) nem ír, értesít', async () => {
    lemez.set('Történelem/Ókor.md', '# Ókor\n\nMás szöveg lett.\n');
    const t = (emlit.forrasok as { talalatok: unknown[] }[])[0].talalatok[0] as never;
    expect(await emlitesLinkel('Matek/Mértani sorozat.md', 'Történelem/Ókor.md', t)).toBe(false);
    expect(irasok).toHaveLength(0);
    expect(ertesitesek.lista.at(-1)!.cim).toContain('megváltozott');
    const t2 = { sor: 99, oszlop: 0, hossz: 3, szoveg: 'x' } as never;
    expect(await emlitesLinkel('Matek/Mértani sorozat.md', 'Történelem/Ókor.md', t2)).toBe(false);
  });

  it('a hiányzó jegyzet nyitási hibája értesítés, nem kivétel', async () => {
    const t = { sor: 1, oszlop: 0, hossz: 3, szoveg: 'x' } as never;
    expect(await emlitesLinkel('Matek/Mértani sorozat.md', 'Nincs.md', t)).toBe(false);
    expect(ertesitesek.lista.at(-1)!.cim).toContain('nem nyitható');
  });
});
