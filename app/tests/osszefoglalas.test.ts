// Az összefoglaló felülete (C26b), ál-core-ral jsdom-ban: a kísérőjegyzet beágyazása az állításokkal és a forrás-linkekkel, a
// sodródás-jelzés, az újragenerálás indítása, a parancsok (mappa-terv, kontextus-csomag), a külső AI válaszának beillesztése és
// az állandók tükre a core-hoz.

import { readFileSync } from 'node:fs';
import { cleanup, fireEvent, waitFor } from '@testing-library/svelte';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { ertesitesek } from '../src/lib/ertesites/ertesites.svelte';
import { linkek } from '../src/lib/vault/linkek.svelte';
import { mediaUt, OSSZEFOGLALO_MAPPA, osszefoglaloUt } from '../src/osszefoglalas/allando';
import { osszefoglalasTelepit } from '../src/osszefoglalas';
import { kulsoAi } from '../src/osszefoglalas/kulsoAllapot.svelte';
import { osszefoglalasMappabol, tartalmiJegyzet } from '../src/osszefoglalas/parancsok';
import { Felulet } from '../src/lib/elrendezes/felulet.svelte';
import { Regiszter } from '../src/lib/parancsok/regiszter';
import { jegyzetOsztalyRenderelok } from '../src/szerkeszto/beagyazas/regiszter';
import { obsidianElemzo } from '../src/szerkeszto/markdown/elemzo';
import { dokumentumRenderel } from '../src/szerkeszto/olvaso/html';
import { LustaRajzolo } from '../src/szerkeszto/olvaso/lusta';

const OSSZ_UT = `${OSSZEFOGLALO_MAPPA}/Jegyzet — összefoglaló.md`;
const json = (adat: unknown, kod = 200) => new Response(JSON.stringify(adat), { status: kod, headers: { 'Content-Type': 'application/json' } });

let kerelmek: { ut: string; metodus: string; torzs?: any }[];
let sodrodott: boolean;
let le: () => void;
let reg: Regiszter;
let felulet: Felulet;

const allitas = (i: number, s = false) => ({
  id: `a${i}`, szoveg: `Állítás ${i}.`, idezet: `A jegyzet ${i}. mondata.`, cel: 'M/Jegyzet', alcel: `^m-000${i}`, felirat: 'forrás',
  sodrodott: s, horgony_hianyzik: false, forras_hianyzik: false,
});

function elemzes() {
  return {
    ok: true, ut: OSSZ_UT, szint: 'jegyzet', cim: 'Jegyzet', azon: 'OSSZ-20261008-120000-abc123', modell: 'qwen35_4b', keszult: '2026-10-08 1200',
    forrasok: ['M/Jegyzet'], forras_ut: 'M/Jegyzet.md', allitasok: [allitas(1), allitas(2, sodrodott)], hibak: [],
    sodrodott: sodrodott ? ['a2'] : [], horgony_hianyzik: [], forras_hianyzik: [],
  };
}

beforeEach(() => {
  kerelmek = [];
  sodrodott = false;
  linkek.mediaToken = 'tok';
  ertesitesek.lista = [];
  ertesitesek.elozmeny = [];
  vi.stubGlobal('fetch', async (url: string, o?: { body?: string; method?: string }) => {
    const u = new URL(url, 'http://127.0.0.1/');
    const torzs = o?.body ? JSON.parse(o.body) : undefined;
    kerelmek.push({ ut: u.pathname + u.search, metodus: o?.method ?? 'GET', torzs });
    if (u.pathname === '/api/vault/beagyazas') return json({ tipus: 'jegyzet', ut: OSSZ_UT, szoveg: '# Jegyzet — Összefoglaló\n' });
    if (u.pathname === '/api/osszefoglalas/jegyzet') return json(elemzes());
    if (u.pathname === '/api/osszefoglalas/mappa-terv')
      return json({ ok: true, jegyzetek: ['M/a.md', 'M/b.md', 'M/c.md'], van: ['M/a.md'], hianyzik: ['M/b.md', 'M/c.md'], keszul: ['M/b.md', 'M/c.md'], tetelek: 3 });
    if (u.pathname === '/api/osszefoglalas/kontextus')
      return json({ ok: true, szoveg: 'CSOMAG', azonositok: { J1: torzs.utak[0] }, benne: ['J1'], csonkolt: [], kihagyott: [], karakter: 6 });
    if (u.pathname === '/api/feladatok') return json({ id: 'F-1' });
    return json({ tipus: 'nincs' });
  });
  reg = new Regiszter();
  felulet = new Felulet();
  le = osszefoglalasTelepit(reg, felulet);
});

afterEach(() => {
  le();
  cleanup();
  document.body.textContent = '';
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

function rajzol(szoveg: string, ut = 'M/Fő.md'): HTMLElement {
  const kont = document.createElement('div');
  document.body.appendChild(kont);
  kont.appendChild(dokumentumRenderel(obsidianElemzo.parse(szoveg), { olvas: (a, b) => szoveg.slice(a, b), ut, lusta: LustaRajzolo.azonnali() }));
  return kont;
}

describe('az állandók', () => {
  it('az összefoglaló-mappa a core [osszefoglalas] mappa tükre', () => {
    const toml = new TextDecoder().decode(readFileSync(decodeURIComponent(new URL('../../config/os.toml', import.meta.url).pathname).replace(/^\/@fs/, '')));
    expect(toml).toContain(`mappa = "${OSSZEFOGLALO_MAPPA}"`);
  });

  it('felismerés', () => {
    expect(osszefoglaloUt(OSSZ_UT)).toBe(true);
    expect(osszefoglaloUt(OSSZ_UT.normalize('NFD'))).toBe(true);
    expect(osszefoglaloUt('M/Jegyzet.md')).toBe(false);
    expect(osszefoglaloUt(`${OSSZEFOGLALO_MAPPA}/kep.png`)).toBe(false);
    expect(mediaUt('V/Előadás.MP4')).toBe(true);
    expect(mediaUt('M/Jegyzet.md')).toBe(false);
    expect(tartalmiJegyzet('M/Jegyzet.md')).toBe(true);
    expect(tartalmiJegyzet(OSSZ_UT)).toBe(false);
    expect(tartalmiJegyzet('.obsidian/x.md')).toBe(false);
  });
});

describe('a beágyazás', () => {
  it('az összefoglaló-jegyzet állításokat és forrás-linkeket mutat, nem a nyers szöveget', async () => {
    const k = rajzol('![[Jegyzet — összefoglaló]]');
    await waitFor(() => expect(k.querySelector('.beagyazas-osszefoglalo .ossz-lista li')).not.toBeNull());
    expect(k.querySelectorAll('.ossz-lista li')).toHaveLength(2);
    expect(k.querySelector('.ossz-cim')!.textContent).toBe('Összefoglaló · Jegyzet');
    expect(k.querySelector('.ossz-al')!.textContent).toContain('2 állítás · jegyzet · qwen35_4b');
    expect(k.querySelector('.ossz-megj')).toBeNull();
    expect(kerelmek.some((r) => r.ut === `/api/osszefoglalas/jegyzet?ut=${encodeURIComponent(OSSZ_UT)}`)).toBe(true);
  });

  it('a jegyzet mondata az idézet-gombra nyílik', async () => {
    const k = rajzol('![[Jegyzet — összefoglaló]]');
    await waitFor(() => expect(k.querySelector('.ossz-idezet-gomb')).not.toBeNull());
    expect(k.querySelector('.ossz-idezet')).toBeNull();
    await fireEvent.click(k.querySelector('.ossz-idezet-gomb')!);
    expect(k.querySelector('.ossz-idezet')!.textContent).toBe('A jegyzet 1. mondata.');
  });

  it('a sodródott állítás elavultnak jelölt, az újragenerálás a feladatot indítja', async () => {
    sodrodott = true;
    const k = rajzol('![[Jegyzet — összefoglaló]]');
    await waitFor(() => expect(k.querySelector('.ossz-megj')).not.toBeNull());
    expect(k.querySelector('.ossz-megj')!.textContent).toContain('1 állítás elavult lehet');
    expect(k.querySelectorAll('.ossz-lista li.elavult')).toHaveLength(1);
    await fireEvent.click([...k.querySelectorAll('button')].find((b) => b.textContent === 'Újragenerálás')!);
    await waitFor(() => expect(kerelmek.some((r) => r.ut === '/api/feladatok')).toBe(true));
    expect(kerelmek.find((r) => r.ut === '/api/feladatok')!.torzs).toEqual({ tipus: 'osszefoglalas', parameterek: { szint: 'jegyzet', ut: 'M/Jegyzet.md' } });
  });

  it('a regiszter kettős regisztrációt nem enged; a leiratkozás kivezeti a renderelőt', () => {
    expect(() => osszefoglalasTelepit(reg, felulet)).toThrow();
    le();
    expect(jegyzetOsztalyRenderelok.keres({ tipus: 'jegyzet', ut: OSSZ_UT }, { cel: 'x' } as never)).toBeUndefined();
    le = osszefoglalasTelepit(reg, felulet);
  });
});

describe('a parancsok', () => {
  it('az „Összefoglalás” valódi parancs (nem helyőrző), jegyzetnél indít', async () => {
    expect(reg.kap('osszefoglalas.keszit')).toBeDefined();
    felulet.munkaterulet.megnyit('M/Jegyzet.md', 'aktiv');
    expect(reg.elerheto(reg.kap('osszefoglalas.keszit')!)).toBe(true);
    reg.futtat('osszefoglalas.keszit');
    await waitFor(() => expect(kerelmek.some((r) => r.ut === '/api/feladatok')).toBe(true));
    expect(kerelmek.find((r) => r.ut === '/api/feladatok')!.torzs.parameterek).toEqual({ szint: 'jegyzet', ut: 'M/Jegyzet.md' });
  });

  it('a videóból átirat-szintű feladat indul', async () => {
    felulet.munkaterulet.megnyit('ATTCHMNTS - Videos/Előadás.mp4', 'aktiv');
    reg.futtat('osszefoglalas.keszit');
    await waitFor(() => expect(kerelmek.some((r) => r.ut === '/api/feladatok')).toBe(true));
    expect(kerelmek.find((r) => r.ut === '/api/feladatok')!.torzs.parameterek.szint).toBe('video');
  });

  it('a mappa-összefoglaló előbb megmutatja a tervet: hány tétel készül', async () => {
    await osszefoglalasMappabol('M/');
    expect(kerelmek.map((r) => r.ut)).toEqual(['/api/osszefoglalas/mappa-terv?ut=M', '/api/feladatok']);
    expect(kerelmek[1].torzs).toEqual({ tipus: 'osszefoglalas', parameterek: { szint: 'mappa', ut: 'M', kiegeszit: true } });
    const e = ertesitesek.elozmeny[0];
    expect(e.cim).toBe('Mappa-összefoglaló készül');
    expect(e.szoveg).toContain('1 jegyzethez már van összefoglaló, 2 még előbb elkészül');
    expect(e.szoveg).toContain('összesen 3 gépi írás');
  });

  it('kevés jegyzetnél a mappa-összefoglaló nem indul', async () => {
    vi.stubGlobal('fetch', async (url: string) => {
      kerelmek.push({ ut: url, metodus: 'GET' });
      return json({ ok: true, jegyzetek: ['M/a.md'], van: [], hianyzik: ['M/a.md'], keszul: ['M/a.md'], tetelek: 2 });
    });
    await osszefoglalasMappabol('M');
    expect(kerelmek.some((r) => r.ut === '/api/feladatok')).toBe(false);
    expect(ertesitesek.elozmeny[0].cim).toBe('Kevés jegyzet a mappa-összefoglalóhoz');
  });

  it('a kontextus-csomag a vágólapra kerül, útvonal nélkül; a csomag jegyzetei megmaradnak a válaszhoz', async () => {
    const ir = vi.fn(async () => {});
    vi.stubGlobal('navigator', { clipboard: { writeText: ir } });
    felulet.munkaterulet.megnyit('M/Jegyzet.md', 'aktiv');
    reg.futtat('osszefoglalas.kontextus');
    await waitFor(() => expect(ir).toHaveBeenCalledWith('CSOMAG'));
    expect(kulsoAi.utak).toEqual(['M/Jegyzet.md']);
    expect(kulsoAi.csomagKesz).toBe(true);
    await waitFor(() => expect(ertesitesek.elozmeny[0]?.cim).toBe('A kontextus-csomag a vágólapon van'));
    expect(ertesitesek.elozmeny[0].szoveg).toContain('útvonal nincs benne');
  });

  it('a „Külső AI válasza…” az átfedést nyitja', () => {
    kulsoAi.beallit(['M/Jegyzet.md'], true);
    felulet.munkaterulet.megnyit('M/Jegyzet.md', 'aktiv');
    reg.futtat('osszefoglalas.kulso-ai');
    expect(felulet.atfedes).toBe('kulso-ai');
  });
});
