// „Új jegyzet sablonból” (C32b, Javító 7): a séma-sértő sablon-frontmatter a core-tól 409 + lista, a felület mutatja, és csak a
// „Mégis létrehozom” után küldi újra `megerosit: true`-val; a hiba szintű sértés megerősítéssel sem írható; a tiszta és a
// frontmatter nélküli sablon változatlanul, megerősítés nélkül megy. A hívó (`ujJegyzetSablonbolHiv`) és a fájlfa (Fa.svelte).

import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/svelte';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { CoreKapcsolat } from '../src/lib/core/ws.svelte';
import { Felulet } from '../src/lib/elrendezes/felulet.svelte';
import { KORNYEZET_KULCS } from '../src/lib/kornyezet';
import { VaultFajlok } from '../src/lib/vault/fajlok.svelte';
import Fa from '../src/hej/Fa.svelte';
import { ujJegyzetSablonbolHiv } from '../src/ma/sablonUj';

const SERTES = { kod: 'ismeretlen_kulcs', szint: 'sertes', kulcs: 'icon', ertek: null, uzenet: 'A(z) „icon” kulcs nincs a vault sémájában.' };
const HIBA = { kod: 'yaml_hiba', szint: 'hiba', kulcs: null, ertek: null, uzenet: 'A frontmatter formai hibás: x' };

let kerelmek: { ut: string; torzs?: Record<string, unknown> }[];
let valasz: (torzs: Record<string, unknown>) => Response;

const json = (adat: unknown, kod = 200) => new Response(JSON.stringify(adat), { status: kod, headers: { 'Content-Type': 'application/json' } });
const sertesValasz = (torzs: Record<string, unknown>) =>
  torzs.megerosit === true
    ? json({ ut: 'Új téma.md', kurzor: null, figyelmeztetes: null })
    : json({ hiba: 'a sablon frontmatterje sérti a vault sémáját; megerősítéssel hozható létre', sema_sertes: true, megerositheto: true, problemak: [SERTES] }, 409);

beforeEach(() => {
  kerelmek = [];
  valasz = () => json({ ut: 'Új téma.md', kurzor: 4 });
  vi.stubGlobal('fetch', async (url: string, o?: { body?: string }) => {
    const torzs = o?.body ? JSON.parse(o.body) : undefined;
    kerelmek.push({ ut: url, torzs });
    if (url === '/api/sablon/uj') return valasz(torzs);
    return json({});
  });
});

afterEach(() => {
  cleanup();
  document.body.textContent = '';
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe('ujJegyzetSablonbolHiv', () => {
  it('tiszta sablon: létrejön, megerősítés nélkül; a törzs nem hordoz megerosit kulcsot', async () => {
    const e = await ujJegyzetSablonbolHiv('Fizika', 'Új téma', '_Template/A.md');
    expect(e).toEqual({ allapot: 'kesz', valasz: { ut: 'Új téma.md', kurzor: 4 } });
    expect(kerelmek[0].torzs).toEqual({ mappa: 'Fizika', nev: 'Új téma', sablon: '_Template/A.md' });
  });

  it('séma-sértés: megerősítésre vár, a lista a core-é; a megerősített hívás megerosit: true-t küld', async () => {
    valasz = sertesValasz;
    const e = await ujJegyzetSablonbolHiv('', 'Új téma', '_Template/A.md');
    expect(e).toMatchObject({ allapot: 'megerosit', problemak: [SERTES] });
    const e2 = await ujJegyzetSablonbolHiv('', 'Új téma', '_Template/A.md', true);
    expect(e2.allapot).toBe('kesz');
    expect(kerelmek.map((k) => k.torzs?.megerosit)).toEqual([undefined, true]);
  });

  it('hiba szintű sértés: nem megerősíthető, a sértések látszanak', async () => {
    valasz = () => json({ hiba: 'a sablon frontmatterje hibás', sema_sertes: true, megerositheto: false, problemak: [HIBA] }, 400);
    const e = await ujJegyzetSablonbolHiv('', 'X', '_Template/A.md', true);
    expect(e).toMatchObject({ allapot: 'hiba', problemak: [HIBA] });
  });

  it('más hiba (névütközés, nem séma 409) sima hiba, lista nélkül', async () => {
    valasz = () => json({ hiba: 'már van ilyen nevű fájl: X.md' }, 400);
    expect(await ujJegyzetSablonbolHiv('', 'X', '_Template/A.md')).toEqual({ allapot: 'hiba', uzenet: 'már van ilyen nevű fájl: X.md', problemak: [] });
    valasz = () => json({ hiba: 'foglalt' }, 409);
    expect(await ujJegyzetSablonbolHiv('', 'X', '_Template/A.md')).toMatchObject({ allapot: 'hiba', problemak: [] });
  });

  it('hálózati hiba is hiba, nem kivétel', async () => {
    vi.stubGlobal('fetch', async () => {
      throw new Error('nincs hálózat');
    });
    expect(await ujJegyzetSablonbolHiv('', 'X', '_Template/A.md')).toMatchObject({ allapot: 'hiba', uzenet: 'nincs hálózat' });
  });
});

describe('a fájlfa: új jegyzet sablonból', () => {
  let felulet: Felulet;

  function megnyit() {
    felulet = new Felulet({});
    const fajlok = new VaultFajlok();
    fajlok.mappak = [];
    const context = new Map<unknown, unknown>([[KORNYEZET_KULCS, { felulet, fajlok, kapcsolat: new CoreKapcsolat('ws://x') }]]);
    render(Fa, { context });
    felulet.faUjSablon = { mappa: '', sablon: '_Template/A.md' };
  }

  async function nevetBeir(nev: string) {
    const mezo = (await screen.findByLabelText('Az új jegyzet neve')) as HTMLInputElement;
    await fireEvent.input(mezo, { target: { value: nev } });
    await fireEvent.keyDown(mezo, { key: 'Enter' });
  }

  it('séma-sértésnél a lista és a „Mégis létrehozom” látszik; a jegyzet addig nem nyílik; a gomb után megerosit: true megy és megnyílik', async () => {
    valasz = sertesValasz;
    megnyit();
    await nevetBeir('Új téma');
    expect(await screen.findByText(SERTES.uzenet)).toBeTruthy();
    expect(felulet.munkaterulet.aktivFul?.ut ?? null).toBeNull();
    expect(kerelmek.filter((k) => k.ut === '/api/sablon/uj')).toHaveLength(1);
    await fireEvent.click(screen.getByRole('button', { name: 'Mégis létrehozom' }));
    await waitFor(() => expect(felulet.munkaterulet.aktivFul?.ut).toBe('Új téma.md'));
    const hivasok = kerelmek.filter((k) => k.ut === '/api/sablon/uj');
    expect(hivasok.map((k) => k.torzs?.megerosit)).toEqual([undefined, true]);
  });

  it('hiba szintű sértésnél nincs „Mégis létrehozom”', async () => {
    valasz = () => json({ hiba: 'a sablon frontmatterje hibás', sema_sertes: true, megerositheto: false, problemak: [HIBA] }, 400);
    megnyit();
    await nevetBeir('Hibás');
    expect(await screen.findByText(HIBA.uzenet)).toBeTruthy();
    expect(screen.queryByRole('button', { name: 'Mégis létrehozom' })).toBeNull();
    expect(felulet.munkaterulet.aktivFul?.ut ?? null).toBeNull();
  });

  it('a név módosítása eldobja a megerősítést (a sértéslista a korábbi útra szólt)', async () => {
    valasz = sertesValasz;
    megnyit();
    await nevetBeir('Új téma');
    await screen.findByRole('button', { name: 'Mégis létrehozom' });
    const mezo = screen.getByLabelText('Az új jegyzet neve') as HTMLInputElement;
    await fireEvent.input(mezo, { target: { value: 'Más név' } });
    expect(screen.queryByRole('button', { name: 'Mégis létrehozom' })).toBeNull();
  });

  it('tiszta sablon: egy hívás, megerősítés nélkül, megnyílik', async () => {
    megnyit();
    await nevetBeir('Új téma');
    await waitFor(() => expect(felulet.munkaterulet.aktivFul?.ut).toBe('Új téma.md'));
    expect(kerelmek.filter((k) => k.ut === '/api/sablon/uj').map((k) => k.torzs?.megerosit)).toEqual([undefined]);
  });
});
