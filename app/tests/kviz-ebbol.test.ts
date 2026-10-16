// „Kvíz ebből” (C22b): előbb ment, utána indítja a `kviz_general` feladatot; kísérőjegyzetből nem indul; a hiba értesítés.

import { beforeEach, describe, expect, it, vi } from 'vitest';
import { Regiszter } from '../src/lib/parancsok/regiszter';
import { Felulet } from '../src/lib/elrendezes/felulet.svelte';
import { ertesitesek } from '../src/lib/ertesites/ertesites.svelte';
import { szerkesztok, type SzerkesztoPeldany } from '../src/szerkeszto/szerkesztok.svelte';
import { kvizEbbol, kvizTelepit } from '../src/kviz';
import { KARTYA_MAPPA } from '../src/kartya/allando';
import { KVIZ_MAPPA } from '../src/kviz/allando';
import { HELYORZOK } from '../src/vezerlo/helyorzok';

function peldany(ut: string, sorrend: string[]): SzerkesztoPeldany {
  return { ut, mentes: async () => { sorrend.push('mentes'); } } as unknown as SzerkesztoPeldany;
}

function alApi(sorrend: string[], hiba = false): (ut: string) => Promise<unknown> {
  return vi.fn(async (ut: string) => {
    sorrend.push(`general:${ut}`);
    if (hiba) throw new Error('nincs kalibrált modell');
    return {};
  });
}

describe('Kvíz ebből', () => {
  beforeEach(() => {
    szerkesztok.aktiv = null;
  });

  it('előbb ment, utána indítja a feladatot, és kimondja, hogy tétlenségben is készülhet', async () => {
    const sorrend: string[] = [];
    szerkesztok.aktiv = peldany('M10 - Sorozatok/Mértani sorozat.md', sorrend);
    await kvizEbbol(alApi(sorrend));
    expect(sorrend).toEqual(['mentes', 'general:M10 - Sorozatok/Mértani sorozat.md']);
    expect(ertesitesek.elozmeny[0].cim).toBe('Kvíz készül');
    expect(ertesitesek.elozmeny[0].szoveg).toContain('tétlenségben');
  });

  it('kvíz- és kártyajegyzetből nem indul', async () => {
    for (const ut of [`${KVIZ_MAPPA}/X — Kvíz 2026-10-08 1200.md`, `${KARTYA_MAPPA}/X — kártyák.md`]) {
      const sorrend: string[] = [];
      szerkesztok.aktiv = peldany(ut, sorrend);
      await kvizEbbol(alApi(sorrend));
      expect(sorrend).toEqual([]);
      expect(ertesitesek.elozmeny[0].cim).toBe('Ez egy kísérőjegyzet');
    }
  });

  it('a hiba értesítés, nem kivétel', async () => {
    const sorrend: string[] = [];
    szerkesztok.aktiv = peldany('A.md', sorrend);
    await kvizEbbol(alApi(sorrend, true));
    expect(ertesitesek.elozmeny[0].cim).toBe('A kvíz készítése nem indult el');
    expect(ertesitesek.elozmeny[0].szoveg).toContain('kalibrált');
  });

  it('a parancs a C17 helyőrzőjének azonosítóján él, és már nem helyőrző', () => {
    const reg = new Regiszter();
    const felulet = new Felulet();
    const le = kvizTelepit(reg, felulet);
    expect(reg.kap('kviz.ebbol')?.nev).toBe('Kvíz ebből');
    expect(HELYORZOK.map((h) => h.id)).not.toContain('kviz.ebbol');
    le();
    expect(reg.kap('kviz.ebbol')).toBeUndefined();
  });
});
