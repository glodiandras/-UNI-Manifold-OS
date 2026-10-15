// A dolgozat-oldal telepítése (C28a): a nézet-regisztráció, a ⌘P-parancs, a fülcím és az ikon, és a Ma oldal gombja.

import { cleanup, fireEvent, render, screen } from '@testing-library/svelte';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { dolgozatTelepit } from '../src/dolgozat';
import Fulsor from '../src/hej/Fulsor.svelte';
import { CoreKapcsolat } from '../src/lib/core/ws.svelte';
import { Felulet } from '../src/lib/elrendezes/felulet.svelte';
import { nezetek } from '../src/lib/elrendezes/nezetek.svelte';
import { KORNYEZET_KULCS } from '../src/lib/kornyezet';
import { Regiszter } from '../src/lib/parancsok/regiszter';
import { VaultFajlok } from '../src/lib/vault/fajlok.svelte';
import Ma from '../src/ma/Ma.svelte';
import { maAdat } from '../src/ma/modell.svelte';
import { json } from './dolgozat-fixture';

afterEach(() => {
  cleanup();
  document.body.textContent = '';
  vi.unstubAllGlobals();
});

describe('telepítő', () => {
  it('a nézet a dolgozat-fülre illeszkedik, a parancs megnyitja a fület, a leiratkozás mindent visszavon', () => {
    const felulet = new Felulet({});
    const reg = new Regiszter();
    const le = dolgozatTelepit(reg, felulet, new CoreKapcsolat('ws://x'));
    const f = { id: 'f', ut: null, nezet: { tipus: 'dolgozat' } };
    expect(nezetek.valaszt(f, undefined)?.id).toBe('dolgozat.nezet');
    expect(nezetek.valaszt({ id: 'g', ut: null, nezet: { tipus: 'ma' } }, undefined)?.id).not.toBe('dolgozat.nezet');
    const parancs = reg.kap('dolgozat.megnyit');
    expect(parancs?.nev).toBe('Dolgozat-felkészültség');
    expect(parancs?.kategoria).toBe('Tanulás');
    reg.futtat('dolgozat.megnyit', 'paletta');
    expect(felulet.munkaterulet.aktivFul?.nezet?.tipus).toBe('dolgozat');
    le();
    expect(reg.kap('dolgozat.megnyit')).toBeUndefined();
    expect(nezetek.valaszt(f, undefined)?.id).not.toBe('dolgozat.nezet');
  });
});

describe('fülsor', () => {
  it('a dolgozat-fül saját címet kap', () => {
    const felulet = new Felulet({});
    const m = felulet.munkaterulet;
    m.megnyitNezet('dolgozat');
    m.ujFul();
    const context = new Map<unknown, unknown>([[KORNYEZET_KULCS, { felulet, fajlok: new VaultFajlok(), kapcsolat: new CoreKapcsolat('ws://x') }]]);
    render(Fulsor, { context, props: { panel: m.aktivPanel, aktivPanel: true, nezetId: 'nezet' } });
    expect(screen.getAllByRole('tab').map((t) => t.textContent?.trim())).toEqual(['Dolgozat', 'Új fül']);
  });
});

describe('a Ma oldal gombja', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', async () => json({}));
  });

  it('a következő dolgozat kártyáján a „Felkészültség” gomb a dolgozat-oldalt nyitja az azonosítóval', async () => {
    const felulet = new Felulet({});
    const context = new Map<unknown, unknown>([[KORNYEZET_KULCS, { felulet, fajlok: new VaultFajlok(), kapcsolat: new CoreKapcsolat('ws://x') }]]);
    const adat = {
      datum: '2026-10-03', felirat: '2026. október 3., szombat', ma: true, napi: { ut: 'X.md', letezik: false, kivonat: '' },
      dolgozatok: { lista: [{ azon: 'd1|x', cim: 'Matek témazáró', nap: '2026-10-07', egesznap: false, ora: '10:00', hely: '', szin: '', napok: 4, jegyzet: null, kotes: null }], utolso_szinkron: null, regi: false },
      naptar: { esemenyek: [], utolso_szinkron: null, regi: false }, feladatok: { ma: [], lejart: [], osszes_ma: 0, osszes_lejart: 0 },
      kartyak: { allapot: 'nincs', esedekes: 0 },
    };
    maAdat.adat = adat as never;
    vi.stubGlobal('fetch', async (url: string) => json(String(url).includes('/api/tracker/') ? { napok: [], tantargyak: [], osszes: { aktiv_mp: 0 } } : String(url).includes('/api/felkeszultseg/keret') ? { napi_perc: 45 } : adat)); // a nézet csatoláskor tölt (T167)
    render(Ma, { context, props: { ful: { id: 'f1', ut: null, nezet: { tipus: 'ma' } }, info: undefined, aktiv: false } });
    await fireEvent.click(screen.getByRole('button', { name: 'Felkészültség' }));
    expect(felulet.munkaterulet.aktivFul?.nezet).toMatchObject({ tipus: 'dolgozat', azon: 'd1|x' });
  });
});
