// Az Asszisztens (C30a) felületi állapota: a jegyzet higiénia-tételei (gyors váltásnál a régi válasz eldobódik, a hiányzó
// vagy épülő index nem hiba, gépelés után csak csend után frissül), a „Ma” összegzése és a heti javaslat, a statisztika
// és az egy gombos törlés; a megjelenítési segédek.

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { asszisztensMa, asszisztensStatisztika, JegyzetHigienia } from '../src/lib/asszisztens/adat.svelte';
import { aranySzoveg, fajtaCim, kuszobSzoveg, szamolvaSzoveg } from '../src/lib/asszisztens/megjelenites';
import type { HigieniaOsszegzes, HigieniaTetel, Statisztika, SzokasJavaslat } from '../src/lib/asszisztens/tipusok';
import { CoreKapcsolat } from '../src/lib/core/ws.svelte';

const json = (adat: unknown, kod = 200) => new Response(JSON.stringify(adat), { status: kod, headers: { 'Content-Type': 'application/json' } });

const tetel = (n: number, mezok: Partial<HigieniaTetel> = {}): HigieniaTetel => ({
  azonosito: `torott_link:${n}`, fajta: 'torott_link', szint: 'hiba', ut: 'A.md', sor: n, uzenet: `Törött link: ${n}`, ...mezok,
});

const OSSZEGZES: HigieniaOsszegzes = {
  kapcsolo: true, kesz: true, szamolva: '2026-10-04T21:00:00+02:00', szamol: false, szunetel: false, hiba: null, alapvonal: false,
  osszesites: { ossz: 5 }, ossz: 5, uj: 2, uj_tetelek: [tetel(1), tetel(2)],
};

const JAVASLAT: SzokasJavaslat = {
  azon: 'szokas:2026-W41:Mathematics', allapot: 'uj', tantargy: 'Mathematics', tantargy_nev: 'matematika', nap_neve: 'szerda', hit: 6, het: 8,
  atlag_perc: 48, legutobbi_ut: 'M01/F.md', szoveg: 'Szerdánként általában tanulsz.',
};

const STAT: Statisztika = {
  kapcsolo: { asszisztens: true, tracker: true }, ablak_nap: 30, osszes: { elfogad: 3, elutasit: 1 },
  fajtak: {
    emlites: { elfogad: 3, elutasit: 1, db: 4, arany: 0.75, kuszob: { szint: 'alap', szorzo: 1 } },
    szokas: { elfogad: 0, elutasit: 0, db: 0, arany: null, kuszob: { szint: 'alap', szorzo: 1 } },
    higienia: { elfogad: 0, elutasit: 0, db: 0, arany: null, kuszob: { szint: 'alap', szorzo: 1 } },
  },
};

let kerelmek: { url: string; metodus: string; body?: unknown }[];
let valaszok: Record<string, (url: URL, init?: RequestInit) => Response | Promise<Response>>;

beforeEach(() => {
  kerelmek = [];
  valaszok = {};
  vi.stubGlobal('fetch', async (url: string, init?: RequestInit) => {
    const u = new URL(url, 'http://127.0.0.1/');
    const metodus = init?.method ?? 'GET';
    kerelmek.push({ url: u.pathname + u.search, metodus, body: init?.body ? JSON.parse(String(init.body)) : undefined });
    const f = valaszok[`${metodus} ${u.pathname}`];
    return f ? f(u, init) : json({ hiba: 'nincs' }, 404);
  });
  asszisztensMa.osszegzes = null;
  asszisztensMa.szokas = null;
  asszisztensMa.hiba = null;
  asszisztensStatisztika.adat = null;
  asszisztensStatisztika.hiba = null;
});

afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

describe('a jegyzet higiénia-tételei', () => {
  it('md-jegyzetnél lekéri a tételeket; más fájlnál és fül nélkül nem kérdez', async () => {
    valaszok['GET /api/higienia'] = () => json({ kesz: true, jegyzetek: 1, tetelek: [tetel(3), tetel(7)] });
    const h = new JegyzetHigienia();
    await h.frissit('Matek/A.md');
    expect(kerelmek[0].url).toBe('/api/higienia?ut=Matek%2FA.md');
    expect(h.tetelek.map((t) => t.sor)).toEqual([3, 7]);
    kerelmek.length = 0;
    await h.frissit('Könyvek/m.pdf');
    await h.frissit(null);
    expect(kerelmek).toEqual([]);
    expect(h.tetelek).toEqual([]);
  });

  it('a hiányzó jegyzet (404) és az épülő index (503) nem hiba; más hiba látszik', async () => {
    const h = new JegyzetHigienia();
    valaszok['GET /api/higienia'] = () => json({ hiba: 'nincs ilyen jegyzet' }, 404);
    await h.frissit('A.md');
    expect(h.hiba).toBeNull();
    valaszok['GET /api/higienia'] = () => json({ hiba: 'az index épül' }, 503);
    await h.frissit('A.md');
    expect(h.hiba).toBeNull();
    valaszok['GET /api/higienia'] = () => json({ hiba: 'váratlan' }, 500);
    await h.frissit('A.md');
    expect(h.hiba).toBe('váratlan');
    expect(h.tetelek).toEqual([]);
  });

  it('gyors váltásnál a régi válasz eldobódik', async () => {
    const lassu: { felold: (r: Response) => void }[] = [];
    valaszok['GET /api/higienia'] = (u) =>
      u.searchParams.get('ut') === 'A.md' ? new Promise<Response>((f) => lassu.push({ felold: f })) : json({ kesz: true, jegyzetek: 1, tetelek: [tetel(9)] });
    const h = new JegyzetHigienia();
    const elso = h.frissit('A.md');
    await h.frissit('B.md');
    lassu[0].felold(json({ kesz: true, jegyzetek: 1, tetelek: [tetel(1)] }));
    await elso;
    expect(h.tetelek.map((t) => t.sor)).toEqual([9]);
  });

  it('a változásra 1,5 s csend után frissít, gépelés közben nem (a trailing debounce kitolódik)', async () => {
    vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout'] });
    valaszok['GET /api/higienia'] = () => json({ kesz: true, jegyzetek: 1, tetelek: [] });
    const k = new CoreKapcsolat('ws://x');
    const h = new JegyzetHigienia();
    const le = h.figyel(k, () => 'A.md');
    for (let i = 0; i < 5; i++) {
      k.szetoszt({ tipus: 'vault_iras', ut: 'A.md' });
      await vi.advanceTimersByTimeAsync(1000);
    }
    expect(kerelmek).toHaveLength(0);
    await vi.advanceTimersByTimeAsync(600);
    expect(kerelmek).toHaveLength(1);
    k.szetoszt({ tipus: 'asszisztens_valtozas' });
    await vi.advanceTimersByTimeAsync(1600);
    expect(kerelmek).toHaveLength(2);
    le();
    k.szetoszt({ tipus: 'vault_iras', ut: 'A.md' });
    await vi.advanceTimersByTimeAsync(3000);
    expect(kerelmek).toHaveLength(2);
  });

  it('nincs aktív jegyzet: a változásra sem kérdez', async () => {
    vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout'] });
    const k = new CoreKapcsolat('ws://x');
    const h = new JegyzetHigienia();
    h.figyel(k, () => null);
    k.szetoszt({ tipus: 'index' });
    await vi.advanceTimersByTimeAsync(2000);
    expect(kerelmek).toEqual([]);
  });
});

describe('a „Ma” oldal Asszisztens-állapota', () => {
  it('betölti az összegzést és a heti javaslatot; a javaslat hibája nem hiba', async () => {
    valaszok['GET /api/asszisztens/higienia'] = () => json(OSSZEGZES);
    valaszok['GET /api/asszisztens/szokas'] = () => json({ javaslat: JAVASLAT });
    await asszisztensMa.betoltOsszegzes();
    await asszisztensMa.betoltSzokas();
    expect(asszisztensMa.osszegzes?.uj).toBe(2);
    expect(asszisztensMa.szokas?.tantargy_nev).toBe('matematika');
    valaszok['GET /api/asszisztens/szokas'] = () => json({ hiba: 'x' }, 500);
    await asszisztensMa.betoltSzokas();
    expect(asszisztensMa.szokas).toBeNull();
    expect(asszisztensMa.hiba).toBeNull();
  });

  it('a „Láttam” a core válaszával nullázza az újat', async () => {
    valaszok['POST /api/asszisztens/higienia/latva'] = () => json({ ...OSSZEGZES, uj: 0, uj_tetelek: [] });
    await asszisztensMa.latva();
    expect(kerelmek[0]).toMatchObject({ metodus: 'POST', url: '/api/asszisztens/higienia/latva' });
    expect(asszisztensMa.osszegzes?.uj).toBe(0);
    expect(asszisztensMa.foglalt).toBe(false);
  });

  it('a „Láttam” hibája látszik, a foglalt jelző visszaáll', async () => {
    valaszok['POST /api/asszisztens/higienia/latva'] = () => json({ hiba: 'még nincs kész riport' }, 409);
    await asszisztensMa.latva();
    expect(asszisztensMa.hiba).toBe('még nincs kész riport');
    expect(asszisztensMa.foglalt).toBe(false);
  });

  it('a javaslat döntése a core-nak megy, és a javaslat eltűnik', async () => {
    asszisztensMa.szokas = JAVASLAT;
    valaszok['POST /api/asszisztens/szokas/dontes'] = () => json({ ok: true });
    await asszisztensMa.szokasDontes('elutasit');
    expect(kerelmek[0].body).toEqual({ azon: JAVASLAT.azon, dontes: 'elutasit' });
    expect(asszisztensMa.szokas).toBeNull();
  });

  it('a javaslat döntésének hibájánál a javaslat újratöltődik, a hiba látszik', async () => {
    asszisztensMa.szokas = JAVASLAT;
    valaszok['POST /api/asszisztens/szokas/dontes'] = () => json({ hiba: 'a javaslatról már döntöttek' }, 409);
    valaszok['GET /api/asszisztens/szokas'] = () => json({ javaslat: null });
    await asszisztensMa.szokasDontes('elfogad');
    await vi.waitFor(() => expect(asszisztensMa.szokas).toBeNull());
    expect(asszisztensMa.hiba).toBe('a javaslatról már döntöttek');
  });

  it('az asszisztens_valtozas eseményre újra kéri az összegzést', async () => {
    valaszok['GET /api/asszisztens/higienia'] = () => json(OSSZEGZES);
    const k = new CoreKapcsolat('ws://x');
    const le = asszisztensMa.figyel(k);
    k.szetoszt({ tipus: 'asszisztens_valtozas', mi: 'higienia' });
    await vi.waitFor(() => expect(asszisztensMa.osszegzes?.ossz).toBe(5));
    le();
  });
});

describe('a statisztika', () => {
  it('betöltés és egy gombos törlés (a törlés után újratölt)', async () => {
    valaszok['GET /api/asszisztens/statisztika'] = () => json(STAT);
    valaszok['POST /api/asszisztens/statisztika/torles'] = () => json({ torolt: 4, tisztitva: true });
    await asszisztensStatisztika.betolt();
    expect(asszisztensStatisztika.adat?.fajtak.emlites.db).toBe(4);
    kerelmek.length = 0;
    expect(await asszisztensStatisztika.torol()).toBe(true);
    expect(kerelmek.map((k) => `${k.metodus} ${k.url}`)).toEqual(['POST /api/asszisztens/statisztika/torles', 'GET /api/asszisztens/statisztika']);
    expect(asszisztensStatisztika.foglalt).toBe(false);
  });

  it('a törlés hibája látszik, nem törölt', async () => {
    valaszok['POST /api/asszisztens/statisztika/torles'] = () => json({ hiba: 'a statisztika adatbázisa nem írható' }, 503);
    expect(await asszisztensStatisztika.torol()).toBe(false);
    expect(asszisztensStatisztika.hiba).toBe('a statisztika adatbázisa nem írható');
  });
});

describe('megjelenítési segédek', () => {
  it('fajta-cím, arány, küszöb', () => {
    expect(fajtaCim('torott_link')).toBe('Törött link');
    expect(fajtaCim('ismeretlen_fajta')).toBe('ismeretlen_fajta');
    expect(aranySzoveg(null)).toBe('—');
    expect(aranySzoveg(0.753)).toBe('75%');
    expect(kuszobSzoveg({ szint: 'alap', szorzo: 1 })).toBe('alap');
    expect(kuszobSzoveg({ szint: 'szigoru', szorzo: 1.5 })).toBe('szigorúbb (×1,5)');
    expect(kuszobSzoveg({ szint: 'nema', szorzo: null })).toBe('néma (nem javasol)');
    expect(szamolvaSzoveg(null)).toBe('');
    expect(szamolvaSzoveg('nem dátum')).toBe('');
    expect(szamolvaSzoveg('2026-10-04T21:00:00+02:00')).not.toBe('');
  });
});
