// A tracker nézetei (C27): a Statisztika és a Használat nézet-fül, a vezérlő két szakasza, az adatkezelés (export,
// kétlépcsős törlés), a saját SVG-grafikonok, a fülsor címkéi és a parancsok megnyitása.

import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/svelte';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import Fulsor from '../src/hej/Fulsor.svelte';
import HasznalatSzakasz from '../src/hej/vezerlo/HasznalatSzakasz.svelte';
import StatisztikaSzakasz from '../src/hej/vezerlo/StatisztikaSzakasz.svelte';
import { CoreKapcsolat } from '../src/lib/core/ws.svelte';
import { Felulet } from '../src/lib/elrendezes/felulet.svelte';
import { ertesitesek } from '../src/lib/ertesites/ertesites.svelte';
import { KORNYEZET_KULCS } from '../src/lib/kornyezet';
import { Regiszter, regiszter } from '../src/lib/parancsok/regiszter';
import { StatisztikaAdat, hasznalatVezerlo, statisztikaVezerlo } from '../src/lib/tracker/adat.svelte';
import { trackerKliens } from '../src/lib/tracker/kliens.svelte';
import Adatkezeles from '../src/lib/tracker/Adatkezeles.svelte';
import Kesleltetes from '../src/lib/tracker/grafikon/Kesleltetes.svelte';
import Oszlopok from '../src/lib/tracker/grafikon/Oszlopok.svelte';
import Savok from '../src/lib/tracker/grafikon/Savok.svelte';
import { maiNap, napEltol } from '../src/lib/tracker/megjelenites';
import type { Hasznalat, Statisztika } from '../src/lib/tracker/tipusok';
import { vezerloKapcsolok } from '../src/lib/vezerlo/kapcsolok.svelte';
import { VaultFajlok } from '../src/lib/vault/fajlok.svelte';
import { trackerTelepit } from '../src/tracker';
import HasznalatNezet from '../src/tracker/HasznalatNezet.svelte';
import StatisztikaNezet from '../src/tracker/StatisztikaNezet.svelte';

function statisztika(mezok: Partial<Statisztika> = {}): Statisztika {
  const ig = maiNap();
  const napok = Array.from({ length: 7 }, (_, i) => ({
    nap: napEltol(ig, i - 6), aktiv_mp: i === 6 ? 5400 : i * 600, beszurt: i * 100, torolt: i * 10,
    kartya: 0, kviz: i === 5 ? 2 : 0, integralt: 0, terv_mp: i === 2 ? 2700 : 0,
  }));
  return {
    tol: napEltol(ig, -6), ig, bontas: 'nap', kapcsolo: true, napok,
    osszes: { aktiv_mp: 5400 + 9000, beszurt: 1500, torolt: 150, kartya: 0, kviz: 2, integralt: 0, terv_mp: 2700 },
    tantargyak: [
      { tantargy: 'Mathematics', aktiv_mp: 9000, beszurt: 900, torolt: 80 },
      { tantargy: 'Physics', aktiv_mp: 5400, beszurt: 600, torolt: 70 },
    ],
    jegyzetek: [{ ut: 'M01 - Matek/Függvények.md', tantargy: 'Mathematics', aktiv_mp: 7200 }],
    elerheto: { kartya: false, kviz: true, integralt: false, terv: true },
    ...mezok,
  };
}

function hasznalat(mezok: Partial<Hasznalat> = {}): Hasznalat {
  const vedrok = new Array(17).fill(0);
  vedrok[3] = 90; // ≤ 8 ms
  vedrok[6] = 8; // ≤ 50 ms
  vedrok[11] = 2; // ≤ 300 ms
  return {
    tol: '2026-09-04', ig: '2026-10-03', kapcsolo: true,
    parancsok: [
      { parancs: 'manifold.most', db: 7, forrasok: { paletta: 5, billentyu: 2 } },
      { parancs: 'szerkeszto.mentes', db: 3, forrasok: { billentyu: 3 } },
    ],
    gepi: [{ funkcio: 'mos-kartya', iras: 4, visszavonas: 1, elfogadas: 0.75 }],
    kesleltetes: {
      gepeles: { db: 100, p50_ms: 8, p95_ms: 50, max_ms: 260, vedrok },
      mentes: { db: 0, p50_ms: null, p95_ms: null, max_ms: null },
    },
    vedrok_ms: [1, 2, 4, 8, 16, 32, 50, 75, 100, 150, 200, 300, 500, 1000, 2000, 5000],
    szunetek: { memoria: { db: 3, mp: 95 }, hutes: { db: 1, mp: 0 } },
    ...mezok,
  };
}

let kerelmek: { url: string; metodus: string; body?: Record<string, unknown> }[];
let torlesKod: number;
let stat: Statisztika;
let has: Hasznalat;
let felulet: Felulet;
let context: Map<unknown, unknown>;

const json = (adat: unknown, kod = 200) => new Response(JSON.stringify(adat), { status: kod, headers: { 'Content-Type': 'application/json' } });

beforeEach(() => {
  kerelmek = [];
  torlesKod = 200;
  stat = statisztika();
  has = hasznalat();
  vezerloKapcsolok.ertek = { asszisztens: true, tracker: true };
  statisztikaVezerlo.adat = null;
  statisztikaVezerlo.hiba = null;
  hasznalatVezerlo.adat = null;
  hasznalatVezerlo.hiba = null;
  trackerKliens.nemFogad = null;
  ertesitesek.lista = [];
  vi.stubGlobal(
    'fetch',
    vi.fn(async (url: string, init?: RequestInit) => {
      kerelmek.push({ url, metodus: init?.method ?? 'GET', body: init?.body ? JSON.parse(String(init.body)) : undefined });
      if (url.startsWith('/api/tracker/statisztika')) return json({ ...stat, bontas: url.includes('bontas=het') ? 'het' : 'nap' });
      if (url.startsWith('/api/tracker/hasznalat')) return json(has);
      if (url === '/api/tracker/esemenyek') return json({ fogadva: true });
      if (url === '/api/tracker/export') {
        const tev = JSON.parse(String(init?.body)).tevekenyseg;
        return json({ ut: `/var/szemelyes/export/hasznalat${tev ? '-tevekenyseggel' : ''}-2026-10-03.json`, tartalom: { verzio: 1 } });
      }
      if (url === '/api/tracker/torles') return torlesKod === 200 ? json({ torolt: 12, tisztitva: true }) : json({ hiba: 'a tracker adatbázisa nem írható' }, torlesKod);
      return json({}, 404);
    }),
  );
  felulet = new Felulet({});
  context = new Map<unknown, unknown>([[KORNYEZET_KULCS, { felulet, fajlok: new VaultFajlok(), kapcsolat: new CoreKapcsolat('ws://x') }]]);
});

afterEach(() => {
  cleanup();
  document.body.textContent = '';
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

const nezetProps = (tipus: string) => ({ ful: { id: 'f1', ut: null, nezet: { tipus } }, info: undefined, aktiv: true });

describe('Statisztika nézet', () => {
  it('nem aktív panelben is tölt; betöltés előtt „Betöltés…” (T167)', async () => {
    render(StatisztikaNezet, { context, props: { ...nezetProps('statisztika'), aktiv: false } });
    expect(screen.getByRole('status').textContent).toContain('Betöltés…');
    await screen.findByText('Tantárgyanként');
    cleanup();
    render(HasznalatNezet, { context, props: { ...nezetProps('hasznalat'), aktiv: false } });
    expect(screen.getByRole('status').textContent).toContain('Betöltés…');
    await screen.findByText('Gépi írások funkciónként');
  });

  it('az összegzés, az oszlopok, a tantárgyak és a jegyzetek szövegben is látszanak; a gyűjtő nélküli forrás „nincs adat”', async () => {
    render(StatisztikaNezet, { context, props: nezetProps('statisztika') });
    await screen.findByText('Tantárgyanként');
    expect(screen.getByText('Aktív idő').nextElementSibling?.textContent).toBe('4 ó 00 p');
    expect(screen.getByText('Kártyaválasz').nextElementSibling?.textContent).toBe('nincs adat'); // nincs gyűjtő (C23)
    expect(screen.getByText('Kvíz').nextElementSibling?.textContent).toBe('2');
    expect(screen.getByText('Tervezett tanulási idő').nextElementSibling?.textContent).toBe('45 p');
    expect(screen.getByRole('img', { name: /aktív idő naponta/i })).toBeTruthy();
    expect(screen.getByRole('img', { name: 'Az aktív idő tantárgyanként' })).toBeTruthy();
    expect(screen.getByText('Mathematics', { selector: 'text' })).toBeTruthy();
    expect(screen.getByText('Függvények')).toBeTruthy();
    expect(screen.getAllByRole('row').length).toBeGreaterThanOrEqual(8); // fejléc + 7 nap
  });

  it('a bontás váltása és a lapozás új tartományt kér; a „későbbi” a mai tartománynál tiltott', async () => {
    render(StatisztikaNezet, { context, props: nezetProps('statisztika') });
    await screen.findByText('Tantárgyanként');
    const kesobbi = screen.getByRole('button', { name: 'Későbbi tartomány' }) as HTMLButtonElement;
    expect(kesobbi.disabled).toBe(true);
    await fireEvent.click(screen.getByRole('button', { name: 'Korábbi tartomány' }));
    await waitFor(() => expect(kerelmek.at(-1)!.url).toContain(`ig=${napEltol(maiNap(), -7)}`));
    expect((screen.getByRole('button', { name: 'Későbbi tartomány' }) as HTMLButtonElement).disabled).toBe(false);
    await fireEvent.click(screen.getByRole('button', { name: 'Hét' }));
    await waitFor(() => expect(kerelmek.at(-1)!.url).toContain('bontas=het'));
    expect(screen.getByRole('button', { name: 'Hét' }).getAttribute('aria-pressed')).toBe('true');
  });

  it('kikapcsolt trackernél jelzi, hogy új adat nem gyűlik; hibánál hibát mutat', async () => {
    vezerloKapcsolok.ertek = { asszisztens: true, tracker: false };
    render(StatisztikaNezet, { context, props: nezetProps('statisztika') });
    expect(await screen.findByText(/A Tracker ki van kapcsolva/)).toBeTruthy();
    cleanup();
    vi.stubGlobal('fetch', async () => json({ hiba: 'elromlott' }, 500));
    statisztikaVezerlo.adat = null;
    render(StatisztikaNezet, { context, props: nezetProps('statisztika') });
    expect((await screen.findByRole('alert')).textContent).toContain('elromlott');
  });

  it('a régebbi (lassabban érkező) válasz nem írja felül az újabbat (gyors Nap/Hét váltás)', async () => {
    const elengedok: (() => void)[] = [];
    vi.stubGlobal('fetch', async (url: string) => {
      if (url.startsWith('/api/tracker/statisztika')) {
        const het = url.includes('bontas=het');
        if (!het) await new Promise<void>((r) => elengedok.push(r)); // a „Nap” kérés lassú
        return json({ ...stat, bontas: het ? 'het' : 'nap' });
      }
      return json({ fogadva: true });
    });
    const m = new StatisztikaAdat();
    const elso = m.frissit();
    m.valt('het');
    await waitFor(() => expect(m.adat?.bontas).toBe('het'));
    await waitFor(() => expect(elengedok.length).toBe(1));
    elengedok[0]();
    await elso;
    expect(m.adat?.bontas).toBe('het');
  });

  it('bukott frissítésnél a régi adat mellett is látszik a hiba', async () => {
    render(StatisztikaNezet, { context, props: nezetProps('statisztika') });
    await screen.findByText('Tantárgyanként');
    vi.stubGlobal('fetch', async () => json({ hiba: 'elromlott' }, 500));
    await fireEvent.click(screen.getByRole('button', { name: 'Hét' }));
    const jelzes = await screen.findByRole('alert');
    expect(jelzes.textContent).toContain('A frissítés nem sikerült');
    expect(jelzes.textContent).toContain('elromlott');
    expect(screen.getByText('Tantárgyanként')).toBeTruthy(); // a régi adat marad
  });

  it('üres tartomány: üres állapot a tantárgyaknál', async () => {
    stat = statisztika({ tantargyak: [], jegyzetek: [], osszes: { aktiv_mp: 0, beszurt: 0, torolt: 0, kartya: 0, kviz: 0, integralt: 0, terv_mp: 0 } });
    render(StatisztikaNezet, { context, props: nezetProps('statisztika') });
    expect(await screen.findByText('Ebben a tartományban nincs rögzített aktív idő.')).toBeTruthy();
  });
});

describe('Használat nézet', () => {
  it('a parancsok forrásonként, a gépi írás elfogadása, a késleltetés p50/p95/max és a szünetek', async () => {
    render(HasznalatNezet, { context, props: nezetProps('hasznalat') });
    await screen.findByText('Gépi írások funkciónként');
    expect(screen.getByText('manifold.most')).toBeTruthy();
    expect(screen.getByText('paletta 5 · billentyű 2')).toBeTruthy();
    expect(screen.getByText('mos-kartya')).toBeTruthy();
    expect(screen.getByText('75 %')).toBeTruthy();
    const osszeg = document.querySelector('.osszeg')!.textContent!;
    expect(osszeg).toContain('p50 ≤ 8 ms');
    expect(osszeg).toContain('p95 ≤ 50 ms');
    expect(osszeg).toContain('max 260 ms');
    expect(screen.getByRole('img', { name: 'Gépelés késleltetésének eloszlása' })).toBeTruthy();
    expect(screen.getByText('Még nincs minta.')).toBeTruthy(); // a mentésnek nincs
    expect(screen.getByText('Memória-szünet').nextElementSibling?.textContent).toContain('3');
  });

  it('a tartomány váltása új lekérdezés', async () => {
    render(HasznalatNezet, { context, props: nezetProps('hasznalat') });
    await screen.findByText('Gépi írások funkciónként');
    await fireEvent.click(screen.getByRole('button', { name: '7 nap' }));
    await waitFor(() => expect(kerelmek.at(-1)!.url).toContain(`tol=${napEltol(maiNap(), -6)}`));
  });

  it('üres adatnál üres állapotok', async () => {
    has = hasznalat({ parancsok: [], gepi: [], kesleltetes: { gepeles: { db: 0, p50_ms: null, p95_ms: null, max_ms: null }, mentes: { db: 0, p50_ms: null, p95_ms: null, max_ms: null } } });
    render(HasznalatNezet, { context, props: nezetProps('hasznalat') });
    expect(await screen.findByText('Még nincs rögzített parancshasználat.')).toBeTruthy();
    expect(screen.getByText(/Még nem írt gép a vaultba/)).toBeTruthy();
    expect(screen.getAllByText('Még nincs minta.')).toHaveLength(2);
  });
});

describe('vezérlő-szakaszok', () => {
  it('a Statisztika szakasz a mai időt mutatja, a Részletek a nézetet az áttekintő mellé nyitja (CX-007)', async () => {
    const reg = regiszter;
    const futott = vi.fn(() => felulet.munkaterulet.megnyitNezet('statisztika'));
    const le = reg.regisztral({ id: 'manifold.statisztika', nev: 'Statisztika megnyitása', futtat: futott });
    felulet.manifoldMegnyit();
    render(StatisztikaSzakasz, { context });
    expect((await screen.findAllByText('1 ó 30 p')).every(e => e.tagName === 'B')).toBe(true);
    expect(screen.getByLabelText('Tanulási idő tantárgyanként')).toBeTruthy();
    expect(screen.getByRole('img', { name: 'Az aktív idő az utolsó 7 napban' })).toBeTruthy();
    await fireEvent.click(screen.getByRole('button', { name: 'Részletek' }));
    expect(futott).toHaveBeenCalledOnce();
    // az áttekintő fül megmarad, a Rendszer szakasza nyitva marad; a Statisztika saját fület kap mellette
    expect(felulet.manifoldLap).toBe(false);
    expect(felulet.manifoldRendszer).toBe(true);
    expect(felulet.munkaterulet.aktivPanel.fulek.map((f) => f.nezet?.tipus)).toEqual(['manifold', 'statisztika']);
    le();
  });

  it('a Statisztika szakasz jelzi, ha a core nem fogadja az eseményeket (T007)', async () => {
    trackerKliens.nemFogad = 'a tracker adatbázisa nem írható';
    render(StatisztikaSzakasz, { context });
    const figy = await screen.findByText(/A Tracker nem tud írni/);
    expect(figy.textContent).toContain('a tracker adatbázisa nem írható');
    expect(figy.getAttribute('role')).toBe('alert');
  });

  it('a Használat szakasz a p95-öt, a szüneteket és a top parancsokat mutatja', async () => {
    render(HasznalatSzakasz, { context });
    await screen.findByText('Gépelés p95');
    expect(screen.getByText('Gépelés p95').nextElementSibling?.textContent).toBe('≤ 50 ms');
    expect(screen.getByText('Mentés p95').nextElementSibling?.textContent).toBe('még nincs minta');
    expect(screen.getByText('manifold.most')).toBeTruthy();
    expect(screen.getByRole('button', { name: 'Export (használat)' })).toBeTruthy();
  });
});

describe('adatkezelés', () => {
  it('az export alapból csak a használati adatot kéri (T111), és kimondja, mi került a vágólapra', async () => {
    const vagolap = vi.fn(async () => {});
    Object.assign(navigator, { clipboard: { writeText: vagolap } });
    render(Adatkezeles);
    await fireEvent.click(screen.getByRole('button', { name: 'Export (használat)' }));
    await waitFor(() => expect(ertesitesek.lista.length).toBe(1));
    expect(kerelmek.find((k) => k.url === '/api/tracker/export')!.body).toMatchObject({ tevekenyseg: false });
    const e = ertesitesek.lista[0];
    expect(e.szoveg).toContain('hasznalat-2026-10-03.json');
    expect(e.szoveg).toContain('vágólap');
    expect(e.szoveg).toMatch(/jegyzetútvonal nélkül/);
    expect(e.szoveg).not.toMatch(/tevékenységnapló/);
    expect(vagolap).toHaveBeenCalledTimes(1);
  });

  it('a tevékenységnapló exportja külön, megnevezett választás: jegyzetútvonalakat visz, és az értesítés ezt kimondja', async () => {
    Object.assign(navigator, { clipboard: { writeText: vi.fn(async () => {}) } });
    render(Adatkezeles);
    const gomb = screen.getByRole('button', { name: 'Export (használat + tevékenységnapló)' });
    expect(gomb.getAttribute('title')).toMatch(/jegyzet/);
    await fireEvent.click(gomb);
    await waitFor(() => expect(ertesitesek.lista.length).toBe(1));
    expect(kerelmek.find((k) => k.url === '/api/tracker/export')!.body).toMatchObject({ tevekenyseg: true });
    const e = ertesitesek.lista[0];
    expect(e.szoveg).toContain('hasznalat-tevekenyseggel-2026-10-03.json');
    expect(e.szoveg).toMatch(/jegyzetútvonalak/);
    expect(e.szoveg).toContain('vágólap');
  });

  it('ha a vágólap nem érhető el, az értesítés nem állítja, hogy oda másolt', async () => {
    Object.assign(navigator, { clipboard: { writeText: vi.fn(async () => { throw new Error('tiltva'); }) } });
    render(Adatkezeles);
    await fireEvent.click(screen.getByRole('button', { name: 'Export (használat)' }));
    await waitFor(() => expect(ertesitesek.lista.length).toBe(1));
    expect(ertesitesek.lista[0].szoveg).not.toContain('vágólap');
  });

  it('a törlés kétlépcsős: megerősítés nélkül nincs kérés, a Mégse visszavisz', async () => {
    render(Adatkezeles);
    await fireEvent.click(screen.getByRole('button', { name: 'Törlés…' }));
    await fireEvent.click(screen.getByRole('button', { name: 'Minden' }));
    expect(screen.getByRole('alert').textContent).toContain('a tracker minden adatát');
    expect(kerelmek.some((k) => k.url === '/api/tracker/torles')).toBe(false);
    await fireEvent.click(screen.getByRole('button', { name: 'Mégse' }));
    expect(screen.getByRole('button', { name: 'Törlés…' })).toBeTruthy();
    await fireEvent.click(screen.getByRole('button', { name: 'Törlés…' }));
    await fireEvent.click(screen.getByRole('button', { name: 'Használati mérés' }));
    await fireEvent.click(screen.getByRole('button', { name: 'Igen, törlés' }));
    await waitFor(() => expect(kerelmek.find((k) => k.url === '/api/tracker/torles')?.body).toEqual({ mit: 'hasznalat' }));
    await waitFor(() => expect(ertesitesek.lista.some((e) => e.cim.includes('Törölve'))).toBe(true));
  });
});

describe('a törlés és a küldés összehangolása (T110)', () => {
  const torolMinden = async () => {
    await fireEvent.click(screen.getByRole('button', { name: 'Törlés…' }));
    await fireEvent.click(screen.getByRole('button', { name: 'Minden' }));
    await fireEvent.click(screen.getByRole('button', { name: 'Igen, törlés' }));
  };

  it('a törlés előtt a puffer eldobódik: a törlés előtti adat nem megy el, a törlés után a küldés újra működik', async () => {
    trackerKliens.aktivMp('M01/titkos.md', 5, '2026-10-03');
    trackerKliens.parancs('a.b', 'gomb');
    render(Adatkezeles);
    await torolMinden();
    await waitFor(() => expect(kerelmek.find((k) => k.url === '/api/tracker/torles')?.body).toEqual({ mit: 'minden' }));
    await waitFor(() => expect(ertesitesek.lista.some((e) => e.cim.includes('Törölve'))).toBe(true));
    expect(trackerKliens.uresPuffer).toBe(true);
    expect(kerelmek.some((k) => k.url === '/api/tracker/esemenyek')).toBe(false);
    trackerKliens.aktivMp('F01/b.md', 3, '2026-10-03');
    await trackerKliens.kuld();
    expect(kerelmek.filter((k) => k.url === '/api/tracker/esemenyek')).toHaveLength(1);
  });

  it('a sikertelen törlés is visszaengedi a küldést', async () => {
    torlesKod = 503;
    render(Adatkezeles);
    await torolMinden();
    await waitFor(() => expect(ertesitesek.lista.some((e) => e.cim.includes('A törlés nem sikerült'))).toBe(true));
    trackerKliens.aktivMp('F01/b.md', 3, '2026-10-03');
    await trackerKliens.kuld();
    expect(kerelmek.filter((k) => k.url === '/api/tracker/esemenyek')).toHaveLength(1);
  });
});

describe('grafikonok', () => {
  it('az oszlopdiagram oszloponként <title>-t ad, a tervezett idő jelölő, az üres nap nem rajzol oszlopot', () => {
    const { container } = render(Oszlopok, {
      props: {
        leiras: 'próba',
        oszlopok: [
          { cimke: 'H', ertek: 3600, terv: 1800, cim: 'hétfő: 1 ó' },
          { cimke: 'K', ertek: 0, cim: 'kedd: 0' },
        ],
      },
    });
    expect([...container.querySelectorAll('title')].map((t) => t.textContent)).toEqual(['hétfő: 1 ó', 'kedd: 0']);
    expect(container.querySelectorAll('rect.oszlop')).toHaveLength(1);
    expect(container.querySelectorAll('line.terv')).toHaveLength(1);
  });

  it('a sávdiagram és a késleltetés-grafikon: szöveges érték, azonos vödörbe eső p50/p95 egy jelölő', () => {
    const s = render(Savok, { props: { leiras: 'sávok', savok: [{ nev: 'Mathematics', ertek: 10, szoveg: '10 p' }, { nev: 'Physics', ertek: 5, szoveg: '5 p' }] } });
    expect(s.container.querySelectorAll('rect.sav')).toHaveLength(2);
    expect(s.getByText('10 p')).toBeTruthy();
    s.unmount();
    const hatarok = [1, 2, 4, 8, 16];
    const k = render(Kesleltetes, { props: { leiras: 'késleltetés', vedrok: [0, 0, 3, 5, 0, 0], hatarok, p50: 8, p95: 8 } });
    expect(k.container.querySelectorAll('line.jelolo')).toHaveLength(1);
    expect(k.getByText('p50 és p95 ≤ 8 ms')).toBeTruthy();
    k.unmount();
    const k2 = render(Kesleltetes, { props: { leiras: 'késleltetés', vedrok: [0, 0, 3, 5, 1, 0], hatarok, p50: 8, p95: 16 } });
    expect(k2.container.querySelectorAll('line.jelolo')).toHaveLength(2);
  });
});

describe('fülsor és telepítés', () => {
  it('a Statisztika- és a Használat-fül saját címet kap', () => {
    const m = felulet.munkaterulet;
    m.megnyitNezet('statisztika');
    m.megnyitNezet('hasznalat');
    render(Fulsor, { context, props: { panel: m.aktivPanel, aktivPanel: true, nezetId: 'nezet' } });
    expect(screen.getAllByRole('tab').map((t) => t.textContent?.trim())).toEqual(['Statisztika', 'Használat']);
  });

  it('a telepítés regisztrálja a parancsokat és a megfigyelőt; a parancs a nézet-fület az áttekintő mellé nyitja', () => {
    const reg = new Regiszter();
    const le = trackerTelepit(reg, felulet);
    expect(reg.kap('manifold.statisztika')).toBeTruthy();
    expect(reg.kap('manifold.hasznalat')).toBeTruthy();
    felulet.manifoldMegnyit();
    reg.futtat('manifold.hasznalat', 'paletta');
    expect(felulet.manifoldLap).toBe(false);
    expect(felulet.manifoldRendszer).toBe(true); // CX-007: a Rendszer szakasz nem csukódik össze
    expect(felulet.munkaterulet.aktivFul?.nezet?.tipus).toBe('hasznalat');
    expect(felulet.munkaterulet.aktivPanel.fulek.some((f) => f.nezet?.tipus === 'manifold')).toBe(true);
    le();
    expect(reg.kap('manifold.statisztika')).toBeUndefined();
  });
});
