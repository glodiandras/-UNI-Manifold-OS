// A vezérlő „Naptár és emlékeztetők” szakasza (C29): engedély-sorok, szinkron most, az emlékeztető-tükör, az ütközések
// láttamozása, a naptárak kategóriái (a javaslat megerősítése), a változások — és a szakasz helye a vezérlő lapján.

import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/svelte';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import ManifoldLap from '../src/hej/ManifoldLap.svelte';
import NaptarSzakasz from '../src/hej/vezerlo/NaptarSzakasz.svelte';
import { CoreKapcsolat } from '../src/lib/core/ws.svelte';
import { Felulet } from '../src/lib/elrendezes/felulet.svelte';
import { KORNYEZET_KULCS } from '../src/lib/kornyezet';
import { naptarVezerlo } from '../src/lib/naptar/allapot.svelte';
import { naptarHid } from '../src/lib/naptar/hid.svelte';
import type { NaptarAllapotValasz, Utkozes } from '../src/lib/naptar/tipusok';
import { VaultFajlok } from '../src/lib/vault/fajlok.svelte';

function utkozes(id: number, mezok: Partial<Utkozes> = {}): Utkozes {
  return { id, mikor: '2026-10-03T08:00:00+02:00', kulcs: `k${id}`, ut: 'X01/Teendők.md', szoveg: `Feladat ${id}`, fajta: 'kesz', reszlet: null, latva: null, ...mezok };
}

function allapot(): NaptarAllapotValasz {
  return {
    seged: true,
    esemeny_engedely: 'engedelyezve',
    emlekezteto_engedely: 'engedelyezve',
    utolso: '2026-10-03T08:00:00+02:00',
    hiba: null,
    naptar: { allapot: 'engedelyezve', uj: 1, valtozott: 0, torolt: 0, osszes: 48, valtozasok: [], blokkok: 3 },
    emlekezteto_kor: { allapot: 'ok', uj: 0 },
    utolso_szinkron: { vege: '2026-10-03T08:00:03+02:00', allapot: 'engedelyezve', utolso_sikeres: '2026-10-03T08:00:03+02:00', uzenet: null },
    naptarak: [
      { azon: 'n1', nev: 'Órarend', forras: 'iCloud', szin: '#78a6e6', kategoria: 'orarend', kategoria_forras: 'auto', eltunt: null },
      { azon: 'n2', nev: 'Matek-felkészülés', forras: 'iCloud', szin: '#a08cf6', kategoria: 'egyeb', kategoria_forras: 'javaslat', eltunt: null },
      { azon: 'n3', nev: 'Régi naptár', forras: 'iCloud', szin: null, kategoria: 'egyeb', kategoria_forras: 'gazda', eltunt: '2026-10-01T10:00:00+02:00' },
    ],
    valtozasok: [
      { mikor: '2026-10-02T09:00:00+02:00', azon: 'n3', fajta: 'eltunt', regi: 'Régi naptár', uj: null },
      { mikor: '2026-10-01T09:00:00+02:00', azon: 'n1', fajta: 'atnevezve', regi: 'Suli', uj: 'Órarend' },
    ],
    kategoriak: [
      { id: 'tanulas', nev: 'Tanulás' },
      { id: 'orarend', nev: 'Órarend' },
      { id: 'egyeb', nev: 'Egyéb' },
    ],
    automatikus: true,
    emlekezteto_allapot: {
      be: true,
      lista: 'Manifold',
      tukor: { aktiv: 5, kezi_torolt: 2, torolve: 1 },
      utkozesek: [utkozes(3, { fajta: 'szerkesztve', reszlet: 'A telefonon átírták a címet.' }), utkozes(2), utkozes(1, { latva: '2026-10-02T10:00:00+02:00' })],
      utolso: null,
    },
    javaslatok: [],
  };
}

let adat: NaptarAllapotValasz;
let kerelmek: { url: string; metodus: string; body?: Record<string, unknown> }[];
let valaszok: Record<string, (init?: RequestInit) => Response>;
const json = (a: unknown, kod = 200) => new Response(JSON.stringify(a), { status: kod, headers: { 'Content-Type': 'application/json' } });

beforeEach(() => {
  adat = allapot();
  kerelmek = [];
  valaszok = {};
  naptarVezerlo.adat = null;
  naptarVezerlo.hiba = null;
  naptarVezerlo.muveletHiba = null;
  naptarVezerlo.foglalt = false;
  naptarVezerlo.kategoriaFolyamatban = [];
  naptarHid.engedely = null;
  naptarHid.hiba = null;
  naptarHid.kerdesben = false;
  vi.stubGlobal('fetch', async (url: string, init?: RequestInit) => {
    const u = new URL(url, 'http://127.0.0.1/');
    const metodus = init?.method ?? 'GET';
    kerelmek.push({ url: u.pathname + u.search, metodus, body: init?.body ? JSON.parse(String(init.body)) : undefined });
    const f = valaszok[`${metodus} ${u.pathname}`];
    if (f) return f(init);
    if (u.pathname === '/api/naptar/allapot' || u.pathname === '/api/naptar/szinkron') return json(adat);
    return json({ hiba: 'nincs' }, 404);
  });
});

afterEach(() => {
  cleanup();
  document.body.textContent = '';
  delete (window as unknown as { webkit?: unknown }).webkit;
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

async function megjelenit() {
  const r = render(NaptarSzakasz);
  await screen.findByText('Szinkron most');
  return r;
}

describe('az állapot', () => {
  it('az engedélyek két sora, az utolsó szinkron és eredménye', async () => {
    await megjelenit();
    const sorok = [...document.querySelectorAll('dt')].map((dt) => `${dt.textContent}=${dt.nextElementSibling?.textContent}`);
    expect(sorok).toContain('Naptár=engedélyezve');
    expect(sorok).toContain('Emlékeztetők=engedélyezve');
    expect(sorok.find((s) => s.startsWith('Utolsó szinkron='))).toMatch(/^Utolsó szinkron=(ma|okt\. 3\.) 08:00$/);
    expect(sorok).toContain('Eredmény=48 esemény (1 új)');
    expect(sorok).toContain('Aktív=5');
    expect(sorok).toContain('Kézzel törölt=2');
  });

  it('a betöltés hibája riasztás', async () => {
    valaszok['GET /api/naptar/allapot'] = () => json({ hiba: 'a core nem válaszol' }, 503);
    render(NaptarSzakasz);
    expect((await screen.findByRole('alert')).textContent).toContain('a core nem válaszol');
  });

  it('nincs döntés böngészőben: magyarázat, gomb nélkül; a héjban gomb', async () => {
    adat.esemeny_engedely = 'nincs_dontes';
    await megjelenit();
    expect(screen.getByText('Az engedélyt a Manifold.app kéri; böngészőből nem kérhető.')).toBeTruthy();
    expect(screen.queryByRole('button', { name: 'Naptár-engedély kérése' })).toBeNull();
    cleanup();
    const kuldott: unknown[] = [];
    (window as unknown as { webkit: unknown }).webkit = { messageHandlers: { manifold: { postMessage: (u: unknown) => kuldott.push(u) } } };
    naptarVezerlo.adat = null;
    await megjelenit();
    await fireEvent.click(screen.getByRole('button', { name: 'Naptár-engedély kérése' }));
    expect(kuldott).toContainEqual({ tipus: 'naptar-engedely', esemeny: true, emlekezteto: true });
  });

  it('megtagadott engedélynél a Rendszerbeállítások teendője áll', async () => {
    adat.emlekezteto_engedely = 'megtagadva';
    await megjelenit();
    expect(screen.getByText(/Rendszerbeállítások › Adatvédelem és biztonság › Naptárak/)).toBeTruthy();
  });

  it('kikapcsolt emlékeztető-tükör: egy sor a számok helyett', async () => {
    adat.emlekezteto_allapot.be = false;
    await megjelenit();
    expect(screen.getByText('Az emlékeztető-tükör ki van kapcsolva.')).toBeTruthy();
    expect(screen.queryByText('Kézzel törölt')).toBeNull();
  });
});

describe('szinkron most', () => {
  it('a POST-ot küldi, közben foglalt, a válasz az új állapot', async () => {
    let kiold: () => void = () => {};
    const var_ = new Promise<void>((r) => (kiold = r));
    valaszok['POST /api/naptar/szinkron'] = (() => {
      throw new Error('nem használt');
    }) as never;
    vi.stubGlobal('fetch', async (url: string, init?: RequestInit) => {
      const u = new URL(url, 'http://127.0.0.1/');
      kerelmek.push({ url: u.pathname, metodus: init?.method ?? 'GET' });
      if (u.pathname === '/api/naptar/szinkron') {
        await var_;
        return json({ ...adat, naptar: { ...adat.naptar!, osszes: 50, uj: 2 } });
      }
      return json(adat);
    });
    await megjelenit();
    const gomb = screen.getByRole('button', { name: 'Szinkron most' }) as HTMLButtonElement;
    await fireEvent.click(gomb);
    await waitFor(() => expect(screen.getByRole('button', { name: 'Szinkronizálás…' })).toBeTruthy());
    expect((screen.getByRole('button', { name: 'Szinkronizálás…' }) as HTMLButtonElement).disabled).toBe(true);
    kiold();
    await screen.findByText('50 esemény (2 új)');
    expect(kerelmek.filter((k) => k.metodus === 'POST' && k.url === '/api/naptar/szinkron')).toHaveLength(1);
    expect((screen.getByRole('button', { name: 'Szinkron most' }) as HTMLButtonElement).disabled).toBe(false);
  });

  it('a hiba megjelenik', async () => {
    valaszok['POST /api/naptar/szinkron'] = () => json({ hiba: 'a segéd nem indult' }, 500);
    await megjelenit();
    await fireEvent.click(screen.getByRole('button', { name: 'Szinkron most' }));
    expect((await screen.findByRole('alert')).textContent).toContain('a segéd nem indult');
  });
});

describe('az ütközések', () => {
  it('az új ütközések sorai a fajtával; a láttamozott nem látszik, de számolva van', async () => {
    await megjelenit();
    expect(screen.getByText('Feladat 3')).toBeTruthy();
    expect(screen.getByText(/Az emlékeztetőt átírták: a jegyzet nyert · (ma|okt\. 3\.) 08:00/)).toBeTruthy();
    expect(screen.getByText('A telefonon átírták a címet.')).toBeTruthy();
    expect(screen.getByText('Feladat 2')).toBeTruthy();
    expect(screen.queryByText('Feladat 1')).toBeNull();
  });

  it('a „Láttam” egy azonosítót, a „Mind láttam” az összeset láttamozza', async () => {
    valaszok['POST /api/emlekezteto/utkozes/latva'] = () => json({ ok: true, db: 1 });
    await megjelenit();
    await fireEvent.click(screen.getByRole('button', { name: 'Láttam: Feladat 3' }));
    await waitFor(() => expect(kerelmek.some((k) => k.url === '/api/emlekezteto/utkozes/latva' && JSON.stringify(k.body) === '{"azonok":[3]}')).toBe(true));
    await fireEvent.click(screen.getByRole('button', { name: 'Mind láttam' }));
    await waitFor(() => expect(kerelmek.filter((k) => k.url === '/api/emlekezteto/utkozes/latva' && JSON.stringify(k.body) === '{}')).toHaveLength(1));
  });

  it('nincs új ütközés: egy halk sor; egy ütközésnél nincs „Mind láttam”', async () => {
    adat.emlekezteto_allapot.utkozesek = [utkozes(1, { latva: 'x' })];
    await megjelenit();
    expect(screen.getByText('Nincs új ütközés. (1 már látott)')).toBeTruthy();
    expect(screen.queryByRole('button', { name: 'Mind láttam' })).toBeNull();
  });
});

describe('a naptárak', () => {
  it('a lista kategória-választóval; az eltűnt jelölve; a javaslat „erősítsd meg”', async () => {
    await megjelenit();
    const orarend = screen.getByRole('combobox', { name: 'Kategória: Órarend' }) as HTMLSelectElement;
    expect(orarend.value).toBe('orarend');
    expect([...orarend.options].map((o) => o.textContent)).toEqual(['Tanulás', 'Órarend', 'Egyéb']);
    expect(screen.getByText(/Régi naptár \(eltűnt\)/)).toBeTruthy();
    expect(screen.getAllByText('javaslat — erősítsd meg')).toHaveLength(1);
    expect(screen.getByRole('button', { name: 'Megerősítem: Matek-felkészülés' })).toBeTruthy();
    expect(screen.queryByRole('button', { name: 'Megerősítem: Órarend' })).toBeNull();
  });

  it('a kategória állítása a core-nak megy, és újratölt', async () => {
    valaszok['POST /api/naptar/kategoria'] = () => {
      adat.naptarak[1] = { ...adat.naptarak[1], kategoria: 'tanulas', kategoria_forras: 'gazda' };
      return json({ ok: true });
    };
    await megjelenit();
    await fireEvent.change(screen.getByRole('combobox', { name: 'Kategória: Matek-felkészülés' }), { target: { value: 'tanulas' } });
    await waitFor(() => expect(screen.queryByText('javaslat — erősítsd meg')).toBeNull());
    expect(kerelmek.find((k) => k.url === '/api/naptar/kategoria')?.body).toEqual({ azon: 'n2', kategoria: 'tanulas' });
    expect((screen.getByRole('combobox', { name: 'Kategória: Matek-felkészülés' }) as HTMLSelectElement).value).toBe('tanulas');
  });

  it('a „Megerősítem” a javasolt kategóriát küldi (gazda lesz)', async () => {
    valaszok['POST /api/naptar/kategoria'] = () => json({ ok: true });
    await megjelenit();
    await fireEvent.click(screen.getByRole('button', { name: 'Megerősítem: Matek-felkészülés' }));
    await waitFor(() => expect(kerelmek.find((k) => k.url === '/api/naptar/kategoria')?.body).toEqual({ azon: 'n2', kategoria: 'egyeb' }));
  });

  it('a kategória hibája látszik', async () => {
    valaszok['POST /api/naptar/kategoria'] = () => json({ hiba: 'ismeretlen kategória: x' }, 400);
    await megjelenit();
    await fireEvent.change(screen.getByRole('combobox', { name: 'Kategória: Órarend' }), { target: { value: 'egyeb' } });
    expect((await screen.findByRole('alert')).textContent).toContain('ismeretlen kategória');
  });

  it('a változások: az átnevezett és az eltűnt naptár röviden, dátummal', async () => {
    await megjelenit();
    const lista = screen.getByRole('heading', { name: 'Változások' }).nextElementSibling as HTMLElement;
    const sorok = within(lista).getAllByRole('listitem').map((l) => l.textContent!.replace(/\s+/g, ' ').trim());
    expect(sorok).toEqual(['eltűnt: „Régi naptár” okt. 2. 09:00', 'átnevezve: „Suli” → „Órarend” okt. 1. 09:00']);
  });
});

describe('a vezérlő lapján', () => {
  it('a szakasz zárva kezd, és csak nyitva kérdez a core-tól; nyitva tölt', async () => {
    const felulet = new Felulet();
    const context = new Map<unknown, unknown>([[KORNYEZET_KULCS, { felulet, fajlok: new VaultFajlok(), kapcsolat: new CoreKapcsolat('ws://x') }]]);
    render(ManifoldLap, { context });
    const fejlec = screen.getByRole('button', { name: 'Naptár és emlékeztetők' });
    expect(fejlec.getAttribute('aria-expanded')).toBe('false');
    expect(kerelmek.some((k) => k.url.startsWith('/api/naptar'))).toBe(false);
    await fireEvent.click(fejlec);
    await screen.findByText('Szinkron most');
    expect(felulet.vezerlo.nyitott.naptar).toBe(true);
    expect(kerelmek.some((k) => k.url === '/api/naptar/allapot')).toBe(true);
  });
});

describe('a WS-események', () => {
  it('a látszó szakasz összevonva újratölt, a nem látszó nem', async () => {
    vi.useFakeTimers();
    try {
      const k = new CoreKapcsolat('ws://x');
      const le = naptarVezerlo.figyel(k);
      k.szetoszt({ tipus: 'emlekezteto_utkozes' });
      await vi.advanceTimersByTimeAsync(1000);
      expect(kerelmek).toHaveLength(0);
      const meg = naptarVezerlo.megjelenik();
      await vi.advanceTimersByTimeAsync(10);
      kerelmek.length = 0;
      k.szetoszt({ tipus: 'emlekezteto_utkozes' });
      k.szetoszt({ tipus: 'naptar_valtozas' });
      k.szetoszt({ tipus: 'emlekezteto_valtozas' });
      await vi.advanceTimersByTimeAsync(1000);
      expect(kerelmek.filter((x) => x.url === '/api/naptar/allapot')).toHaveLength(1);
      meg();
      le();
    } finally {
      vi.useRealTimers();
    }
  });
});
