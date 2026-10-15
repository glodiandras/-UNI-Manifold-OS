// A „Ma” oldal C29-es szakaszai: a naptár-jelzés (hiányzó segéd, engedély, hiba), az engedély-kérés gombja a héjban és
// böngészőben, és a tanulásiblokk-javaslatok jóváhagyása / elvetése (a core-kliens hamisításával).

import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/svelte';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { CoreKapcsolat } from '../src/lib/core/ws.svelte';
import { Felulet } from '../src/lib/elrendezes/felulet.svelte';
import { ertesitesek } from '../src/lib/ertesites/ertesites.svelte';
import { KORNYEZET_KULCS } from '../src/lib/kornyezet';
import { naptarHid } from '../src/lib/naptar/hid.svelte';
import { VaultFajlok } from '../src/lib/vault/fajlok.svelte';
import { napKulcs } from '../src/ma/datum';
import { javaslatKezelo } from '../src/ma/javaslat.svelte';
import Ma from '../src/ma/Ma.svelte';
import { maAdat } from '../src/ma/modell.svelte';
import type { Javaslat, MaValasz, NaptarAllapotSzakasz } from '../src/ma/tipusok';

function holnap(): string {
  const d = new Date();
  d.setDate(d.getDate() + 1);
  return napKulcs(d);
}

function javaslat(id: number, mezok: Partial<Javaslat> = {}): Javaslat {
  const nap = holnap();
  return {
    id,
    nap,
    kezd: `${nap}T16:00:00+02:00`,
    veg: `${nap}T17:00:00+02:00`,
    perc: 60,
    cim: `Tanulás: Matematika ${id}`,
    tantargy: 'Matematika',
    tema: 'Deriválás',
    indok: 'A dolgozat előtt két nappal még szabad a sáv.',
    allapot: 'uj',
    ...mezok,
  };
}

function alap(): MaValasz {
  return {
    datum: '2026-10-03',
    felirat: '2026. október 3., szombat',
    ma: true,
    napi: { ut: 'X01/2026-10-03.md', letezik: false, kivonat: '' },
    dolgozatok: { lista: [], utolso_szinkron: null, regi: false },
    naptar: { esemenyek: [], utolso_szinkron: null, regi: false },
    feladatok: { ma: [], lejart: [], osszes_ma: 0, osszes_lejart: 0 },
    naptar_allapot: { seged: true, esemeny_engedely: 'engedelyezve', emlekezteto_engedely: 'engedelyezve', hiba: null, utolso: '2026-10-03T08:00:00+02:00', automatikus: true },
    javaslatok: { lista: [] },
    kartyak: { allapot: 'nincs', esedekes: 0 },
  };
}

const allapot = (m: Partial<NaptarAllapotSzakasz>): NaptarAllapotSzakasz => ({ ...(alap().naptar_allapot as NaptarAllapotSzakasz), ...m });

let valasz: MaValasz;
let kerelmek: { url: string; metodus: string; body?: unknown }[];
let kiegeszito: Record<string, (init?: RequestInit) => Response>;
let context: Map<unknown, unknown>;
let kuldott: unknown[];

const json = (adat: unknown, kod = 200) => new Response(JSON.stringify(adat), { status: kod, headers: { 'Content-Type': 'application/json' } });

async function megjelenit(v: MaValasz = valasz) {
  valasz = v;
  await maAdat.frissit();
  return render(Ma, { context, props: { ful: { id: 'f1', ut: null, nezet: { tipus: 'ma' } }, info: undefined, aktiv: true } });
}

const hejTelepit = () => {
  (window as unknown as { webkit: unknown }).webkit = { messageHandlers: { manifold: { postMessage: (u: unknown) => kuldott.push(u) } } };
};

beforeEach(() => {
  valasz = alap();
  kerelmek = [];
  kuldott = [];
  kiegeszito = {};
  (maAdat as unknown as { engedelyProba: boolean }).engedelyProba = false;
  naptarHid.engedely = null;
  naptarHid.hiba = null;
  naptarHid.kerdesben = false;
  javaslatKezelo.foglalt = [];
  javaslatKezelo.hibak = {};
  ertesitesek.lista = [];
  ertesitesek.elozmeny = [];
  vi.stubGlobal('fetch', async (url: string, init?: RequestInit) => {
    const u = new URL(url, 'http://127.0.0.1/');
    if (u.pathname.startsWith('/api/tracker/')) return json({ napok: [], tantargyak: [], osszes: { aktiv_mp: 0 } });
    if (u.pathname === '/api/felkeszultseg/keret') return json({ napi_perc: 45 });
    const metodus = init?.method ?? 'GET';
    kerelmek.push({ url: u.pathname + u.search, metodus, body: init?.body ? JSON.parse(String(init.body)) : undefined });
    const f = kiegeszito[`${metodus} ${u.pathname}`];
    if (f) return f(init);
    if (u.pathname === '/api/ma') return json(valasz);
    return json({ hiba: 'nincs' }, 404);
  });
  const felulet = new Felulet({});
  context = new Map<unknown, unknown>([[KORNYEZET_KULCS, { felulet, fajlok: new VaultFajlok(), kapcsolat: new CoreKapcsolat('ws://x') }]]);
});

afterEach(() => {
  cleanup();
  document.body.textContent = '';
  delete (window as unknown as { webkit?: unknown }).webkit;
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

const nap = () => screen.getByRole('region', { name: 'A nap' });

describe('a naptár-jelzés a „A nap” szakasz fejében', () => {
  it('rendben lévő szinkronnál nincs jelzés', async () => {
    await megjelenit();
    expect(within(nap()).queryByRole('status')).toBeNull();
  });

  it('hiányzó segéd: az ok kimondva, gomb nélkül', async () => {
    const v = alap();
    v.naptar_allapot = allapot({ seged: false, esemeny_engedely: null, hiba: 'nincs naptár-segéd: a Manifold.app újrafordítása kell' });
    await megjelenit(v);
    expect(within(nap()).getByRole('status').textContent).toContain('újrafordítása');
    expect(within(nap()).queryByRole('button')).toBeNull();
  });

  it('a szinkron hibája engedély mellett is látszik', async () => {
    const v = alap();
    v.naptar_allapot = allapot({ hiba: 'a segéd nem válaszolt' });
    await megjelenit(v);
    expect(within(nap()).getByRole('status').textContent).toContain('a segéd nem válaszolt');
  });

  it('megtagadott engedély: a Rendszerbeállítások teendője, gomb nélkül', async () => {
    const v = alap();
    v.naptar_allapot = allapot({ esemeny_engedely: 'megtagadva' });
    hejTelepit();
    await megjelenit(v);
    expect(within(nap()).getByRole('status').textContent).toContain('Rendszerbeállítások › Adatvédelem és biztonság › Naptárak');
    expect(within(nap()).queryByRole('button')).toBeNull();
  });

  it('nincs döntés böngészőben: a magyarázat gomb helyett', async () => {
    const v = alap();
    v.naptar_allapot = allapot({ esemeny_engedely: 'nincs_dontes' });
    await megjelenit(v);
    expect(within(nap()).getByText('Az engedélyt a Manifold.app kéri; böngészőből nem kérhető.')).toBeTruthy();
    expect(within(nap()).queryByRole('button', { name: 'Naptár-engedély kérése' })).toBeNull();
  });

  it('nincs döntés a héjban: a gomb a natív üzenetet küldi, a válasz újratölt', async () => {
    const v = alap();
    v.naptar_allapot = allapot({ esemeny_engedely: 'nincs_dontes', emlekezteto_engedely: 'nincs_dontes' });
    hejTelepit();
    await megjelenit(v);
    await fireEvent.click(within(nap()).getByRole('button', { name: 'Naptár-engedély kérése' }));
    expect(kuldott).toEqual([{ tipus: 'naptar-engedely', esemeny: true, emlekezteto: true }]);
    expect((within(nap()).getByRole('button') as HTMLButtonElement).disabled).toBe(true); // a rendszer ablakára vár
    naptarHid.fogad({ esemeny: 'engedelyezve', emlekezteto: 'engedelyezve' });
    await waitFor(() => expect((within(nap()).getByRole('button') as HTMLButtonElement).disabled).toBe(false));
  });

  it('ha a core még nem ismeri az engedélyt, egyszer rákérdez (frissit=1), majd újratölt', async () => {
    const v = alap();
    v.naptar_allapot = allapot({ seged: null, esemeny_engedely: null });
    kiegeszito['GET /api/naptar/allapot'] = () => {
      valasz.naptar_allapot = allapot({ esemeny_engedely: 'megtagadva' });
      return json({});
    };
    await megjelenit(v);
    await waitFor(() => expect(within(nap()).getByRole('status').textContent).toContain('meg van tagadva'));
    expect(kerelmek.filter((k) => k.url === '/api/naptar/allapot?frissit=1')).toHaveLength(1);
    await maAdat.frissit();
    expect(kerelmek.filter((k) => k.url === '/api/naptar/allapot?frissit=1')).toHaveLength(1); // nem hurkol
  });

  it('a szakasz saját hibája nem viszi el az oldalt', async () => {
    const v = alap();
    v.naptar_allapot = { hiba: 'nincs szolgáltatás' };
    await megjelenit(v);
    expect(within(nap()).getByRole('status').textContent).toContain('nincs szolgáltatás');
    expect(screen.getByRole('heading', { level: 1 }).textContent).toBe('Manifold');
  });

  it('a javaslat-szakasz hibája nem csendes: halk sor, az oldal él (C32)', async () => {
    const v = alap();
    v.javaslatok = { hiba: 'a javaslat-forrás nem válaszol' };
    await megjelenit(v);
    expect(screen.getByText(/A tanulásiblokk-javaslatok most nem tölthetők be: a javaslat-forrás nem válaszol/)).toBeTruthy();
    expect(screen.queryByRole('alert')).toBeNull();
  });

  it('a régebbi core, amely nem adja a C29-es szakaszokat: nincs jelzés, nincs javaslat', async () => {
    const v = alap();
    delete v.naptar_allapot;
    delete v.javaslatok;
    await megjelenit(v);
    expect(within(nap()).queryByRole('status')).toBeNull();
    expect(screen.queryByText('Tanulási blokk javaslata')).toBeNull();
  });
});

describe('a tanulásiblokk-javaslatok', () => {
  const kartya = (cim: string) => screen.getByRole('group', { name: cim });

  it('kártya: cím, olvasható idő, indok; a dolgozat szakaszban, a kártya alatt', async () => {
    const v = alap();
    v.javaslatok = { lista: [javaslat(7)] };
    await megjelenit(v);
    const dolgozat = screen.getByRole('region', { name: 'Következő dolgozat / határidő' });
    const k = within(dolgozat).getByRole('group', { name: 'Tanulás: Matematika 7' });
    expect(within(k).getByText(/^holnap · .* · 16:00–17:00 · 60 perc$/)).toBeTruthy();
    expect(within(k).getByText('A dolgozat előtt két nappal még szabad a sáv.')).toBeTruthy();
    expect(within(dolgozat).getByRole('heading', { level: 3 }).textContent).toBe('Tanulási blokk javaslata');
    expect(screen.getAllByRole('heading', { level: 2 })).toHaveLength(6); // nem lett új szakasz
  });

  it('a „Beírom a naptárba” egy kattintásra jóváhagy, kérdés nélkül; a lista frissül', async () => {
    const v = alap();
    v.javaslatok = { lista: [javaslat(7), javaslat(8)] };
    kiegeszito['POST /api/naptar/javaslat/7/jovahagy'] = () => {
      valasz.javaslatok = { lista: [javaslat(8)] };
      return json({ ok: true, id: 7, allapot: 'beirva' });
    };
    await megjelenit(v);
    const confirm = vi.spyOn(window, 'confirm');
    await fireEvent.click(within(kartya('Tanulás: Matematika 7')).getByRole('button', { name: 'Beírom a naptárba' }));
    await waitFor(() => expect(screen.queryByRole('group', { name: 'Tanulás: Matematika 7' })).toBeNull());
    expect(confirm).not.toHaveBeenCalled();
    expect(kerelmek.filter((k) => k.metodus === 'POST').map((k) => k.url)).toEqual(['/api/naptar/javaslat/7/jovahagy']);
    expect(screen.getByRole('group', { name: 'Tanulás: Matematika 8' })).toBeTruthy();
    expect(ertesitesek.lista.some((e) => e.cim.includes('bekerült a naptárba'))).toBe(true);
  });

  it('az „Elvetem” az elvet végpontot hívja, és eltűnik a kártya', async () => {
    const v = alap();
    v.javaslatok = { lista: [javaslat(7)] };
    kiegeszito['POST /api/naptar/javaslat/7/elvet'] = () => {
      valasz.javaslatok = { lista: [] };
      return json({ ok: true, id: 7, allapot: 'elvetett' });
    };
    await megjelenit(v);
    await fireEvent.click(within(kartya('Tanulás: Matematika 7')).getByRole('button', { name: 'Elvetem' }));
    await waitFor(() => expect(screen.queryByText('Tanulási blokk javaslata')).toBeNull());
    expect(kerelmek.some((k) => k.url === '/api/naptar/javaslat/7/elvet' && k.metodus === 'POST')).toBe(true);
    expect(kerelmek.some((k) => k.url.endsWith('/jovahagy'))).toBe(false);
  });

  it('a jóváhagyás hibája látszik a kártyán és értesítésben; a kártya megmarad, ha a core nem zárta le', async () => {
    const v = alap();
    v.javaslatok = { lista: [javaslat(7)] };
    kiegeszito['POST /api/naptar/javaslat/7/jovahagy'] = () => json({ hiba: 'a javasolt sáv közben foglalt lett a naptárban' }, 409);
    await megjelenit(v);
    await fireEvent.click(within(kartya('Tanulás: Matematika 7')).getByRole('button', { name: 'Beírom a naptárba' }));
    const hiba = await within(kartya('Tanulás: Matematika 7')).findByRole('alert');
    expect(hiba.textContent).toBe('a javasolt sáv közben foglalt lett a naptárban');
    expect(ertesitesek.lista.some((e) => e.szint === 'hiba' && e.szoveg.includes('foglalt lett'))).toBe(true);
    expect((within(kartya('Tanulás: Matematika 7')).getByRole('button', { name: 'Elvetem' }) as HTMLButtonElement).disabled).toBe(false);
  });

  it('döntés közben a két gomb tiltott (nincs dupla jóváhagyás)', async () => {
    const v = alap();
    v.javaslatok = { lista: [javaslat(7)] };
    let kiold: () => void = () => {};
    const var_ = new Promise<void>((r) => (kiold = r));
    vi.stubGlobal('fetch', async (url: string, init?: RequestInit) => {
      const u = new URL(url, 'http://127.0.0.1/');
    if (u.pathname.startsWith('/api/tracker/')) return json({ napok: [], tantargyak: [], osszes: { aktiv_mp: 0 } });
    if (u.pathname === '/api/felkeszultseg/keret') return json({ napi_perc: 45 });
      kerelmek.push({ url: u.pathname, metodus: init?.method ?? 'GET' });
      if (u.pathname.endsWith('/jovahagy')) {
        await var_;
        return json({ ok: true });
      }
      return json(valasz);
    });
    await megjelenit(v);
    const gomb = within(kartya('Tanulás: Matematika 7')).getByRole('button', { name: 'Beírom a naptárba' }) as HTMLButtonElement;
    await fireEvent.click(gomb);
    await waitFor(() => expect(gomb.disabled).toBe(true));
    await fireEvent.click(gomb);
    kiold();
    await waitFor(() => expect(gomb.disabled).toBe(false));
    expect(kerelmek.filter((k) => k.url.endsWith('/jovahagy'))).toHaveLength(1);
  });

  it('a javaslat-szakasz hibája csendes: nincs kártya', async () => {
    const v = alap();
    v.javaslatok = { hiba: 'a szolgáltatás nem érhető el' };
    await megjelenit(v);
    expect(screen.queryByText('Tanulási blokk javaslata')).toBeNull();
    expect(screen.queryByRole('alert')).toBeNull();
  });
});

describe('a WS-események újratöltik az oldalt', () => {
  it('naptar_valtozas és naptar_javaslat: összevonva egy töltés', async () => {
    vi.useFakeTimers();
    try {
      const k = new CoreKapcsolat('ws://x');
      const le = maAdat.figyel(k);
      const megjelent = maAdat.megjelenik();
      await vi.advanceTimersByTimeAsync(10);
      kerelmek.length = 0;
      k.szetoszt({ tipus: 'naptar_valtozas', allapot: 'engedelyezve', uj: 0, valtozott: 1, torolt: 0, valtozasok: [] });
      k.szetoszt({ tipus: 'naptar_javaslat', uj: 1 });
      await vi.advanceTimersByTimeAsync(1000);
      expect(kerelmek.filter((x) => x.url === '/api/ma')).toHaveLength(1);
      megjelent();
      le();
    } finally {
      vi.useRealTimers();
    }
  });
});
