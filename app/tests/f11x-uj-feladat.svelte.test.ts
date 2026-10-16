// F11 (2. tétel): az „Új feladat” felület a kód-munkafelület minden nyelvén: nyelvválasztó a profil-táblából, a kérés a
// kiválasztott nyelvet küldi, a siker után a jegyzet nyílik és a (nem C++) forrás osztásban előkerül.

import { cleanup, fireEvent, render, waitFor } from '@testing-library/svelte';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import UjFeladat from '../src/kod/UjFeladat.svelte';
import { CoreKapcsolat } from '../src/lib/core/ws.svelte';
import { nyelv } from '../src/lib/i18n';
import { Felulet } from '../src/lib/elrendezes/felulet.svelte';
import { KORNYEZET_KULCS } from '../src/lib/kornyezet';
import { VaultFajlok } from '../src/lib/vault/fajlok.svelte';
import { KOD_NYELVEK } from '../src/lib/vault/kodFajl';

let keresek: { ut: string; torzs: Record<string, unknown> }[];
const valasz = (kod: number, adat: unknown) => new Response(JSON.stringify(adat), { status: kod, headers: { 'Content-Type': 'application/json' } });

beforeEach(() => {
  nyelv.beallit('en');
  keresek = [];
  vi.stubGlobal('fetch', async (url: string, init?: RequestInit) => {
    const u = new URL(url, 'http://127.0.0.1/');
    const torzs = init?.body ? (JSON.parse(String(init.body)) as Record<string, unknown>) : {};
    keresek.push({ ut: u.pathname, torzs });
    if (u.pathname === '/api/cpp/feladat') {
      const kit = torzs.nyelv === 'python' ? '.py' : '.cpp';
      return valasz(201, { jegyzet: `${torzs.nev}.md`, cpp: `${torzs.nev}${kit}`, forras: `${torzs.nev}${kit}`, nyelv: torzs.nyelv, figyelmeztetes: null });
    }
    return valasz(404, { hiba: u.pathname });
  });
});

afterEach(() => {
  nyelv.beallit('hu');
  cleanup();
  vi.unstubAllGlobals();
});

function nyit() {
  const felulet = new Felulet({});
  felulet.atfedes = 'cpp-feladat';
  const megnyit = vi.spyOn(felulet.munkaterulet, 'megnyit').mockImplementation(() => undefined as never);
  const kornyezet = { felulet, fajlok: new VaultFajlok(), kapcsolat: new CoreKapcsolat('ws://127.0.0.1:1/ws') };
  const c = render(UjFeladat, { context: new Map([[KORNYEZET_KULCS, kornyezet]]) });
  return { c, felulet, megnyit };
}

describe('Új feladat: nyelvválasztó', () => {
  it('a nyelvlista a kód-profilok táblája, az alap a C++, a cím nyelvfüggetlen angol', () => {
    const { c } = nyit();
    const sel = c.container.querySelector<HTMLSelectElement>('[data-teszt="uj-feladat-nyelv"]')!;
    expect([...sel.options].map((o) => o.value)).toEqual(KOD_NYELVEK.map((n) => n.azonosito));
    expect([...sel.options].map((o) => o.textContent)).toEqual(KOD_NYELVEK.map((n) => n.nev));
    expect(sel.value).toBe('cpp');
    expect(c.container.querySelector('h2')!.textContent).toBe('New task');
    expect(c.container.textContent).not.toMatch(/C\+\+ task/);
  });

  it('Python kiválasztva: a kérés a nyelvet küldi, a jegyzet nyílik, a Python forrás osztásban előkerül', async () => {
    const { c, felulet, megnyit } = nyit();
    const sel = c.container.querySelector<HTMLSelectElement>('[data-teszt="uj-feladat-nyelv"]')!;
    await fireEvent.change(sel, { target: { value: 'python' } });
    const nev = c.container.querySelector<HTMLInputElement>('input')!;
    await fireEvent.input(nev, { target: { value: 'Szamok' } });
    await fireEvent.keyDown(nev, { key: 'Enter' });
    await waitFor(() => expect(megnyit).toHaveBeenCalledTimes(2));
    const k = keresek.find((x) => x.ut === '/api/cpp/feladat')!;
    expect(k.torzs).toEqual({ mappa: '', nev: 'Szamok', nyelv: 'python' });
    expect(megnyit.mock.calls[0][0]).toBe('Szamok.md');
    expect(megnyit.mock.calls[1][0]).toBe('Szamok.py');
    expect(felulet.atfedes).toBeNull();
  });

  it('alapból C++ -t kér (a C36a kérés-alak nyelvmezővel)', async () => {
    const { c, megnyit } = nyit();
    const nev = c.container.querySelector<HTMLInputElement>('input')!;
    await fireEvent.input(nev, { target: { value: 'Osszeg' } });
    await fireEvent.keyDown(nev, { key: 'Enter' });
    await waitFor(() => expect(megnyit).toHaveBeenCalled());
    expect(keresek.find((x) => x.ut === '/api/cpp/feladat')!.torzs).toEqual({ mappa: '', nev: 'Osszeg', nyelv: 'cpp' });
  });
});
