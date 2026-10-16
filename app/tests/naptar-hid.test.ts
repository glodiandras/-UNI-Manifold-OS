// A naptár (C29) natív hídja, a WS-értesítések és a parancsok: a `naptarEngedely` kezelő, az engedély-válasz utómunkája,
// az értesítés-szövegek a core eseményeire, és a két parancs a regiszterben.

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { CoreKapcsolat } from '../src/lib/core/ws.svelte';
import { Felulet } from '../src/lib/elrendezes/felulet.svelte';
import { ertesitesek } from '../src/lib/ertesites/ertesites.svelte';
import { naptarVezerlo } from '../src/lib/naptar/allapot.svelte';
import { naptarHid } from '../src/lib/naptar/hid.svelte';
import { Regiszter } from '../src/lib/parancsok/regiszter';
import { maAdat } from '../src/ma/modell.svelte';
import { naptarTelepit, engedelyValasz } from '../src/naptar';
import { bejelentettekTorol } from '../src/naptar/ertesites';

let kuldott: unknown[];
let kerelmek: { url: string; metodus: string }[];
let allapotValasz: Record<string, unknown>;
const json = (a: unknown, kod = 200) => new Response(JSON.stringify(a), { status: kod, headers: { 'Content-Type': 'application/json' } });

const hejTelepit = () => {
  (window as unknown as { webkit: unknown }).webkit = { messageHandlers: { manifold: { postMessage: (u: unknown) => kuldott.push(u) } } };
};

function alapAllapot(mezok: Record<string, unknown> = {}) {
  return {
    seged: true,
    esemeny_engedely: 'engedelyezve',
    emlekezteto_engedely: 'engedelyezve',
    utolso: null,
    hiba: null,
    naptar: null,
    emlekezteto_kor: null,
    utolso_szinkron: null,
    naptarak: [],
    valtozasok: [],
    kategoriak: [],
    automatikus: true,
    emlekezteto_allapot: { be: true, lista: 'Manifold', tukor: { aktiv: 0, kezi_torolt: 0, torolve: 0 }, utkozesek: [], utolso: null },
    javaslatok: [],
    ...mezok,
  };
}

beforeEach(() => {
  kuldott = [];
  kerelmek = [];
  allapotValasz = alapAllapot();
  naptarHid.engedely = null;
  naptarHid.hiba = null;
  naptarHid.kerdesben = false;
  naptarVezerlo.adat = null;
  naptarVezerlo.muveletHiba = null;
  ertesitesek.lista = [];
  ertesitesek.elozmeny = [];
  bejelentettekTorol();
  vi.stubGlobal('fetch', async (url: string, init?: RequestInit) => {
    const u = new URL(url, 'http://127.0.0.1/');
    kerelmek.push({ url: u.pathname + u.search, metodus: init?.method ?? 'GET' });
    if (u.pathname === '/api/naptar/allapot' || u.pathname === '/api/naptar/szinkron') return json(allapotValasz);
    return json({ hiba: 'nincs' }, 404);
  });
});

afterEach(() => {
  delete (window as unknown as { webkit?: unknown }).webkit;
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe('a natív híd', () => {
  it('héj nélkül az engedély nem kérhető: nincs üzenet, a gomb sem lép tiltott állapotba', () => {
    expect(naptarHid.elerheto).toBe(false);
    expect(naptarHid.kerd()).toBe(false);
    expect(naptarHid.kerdesben).toBe(false);
    expect(kuldott).toEqual([]);
  });

  it('a kérés a héjnak megy a megadott entitásokkal; az állapot-lekérdezés külön üzenet', () => {
    hejTelepit();
    expect(naptarHid.elerheto).toBe(true);
    expect(naptarHid.kerd(true, false)).toBe(true);
    expect(naptarHid.kerdesben).toBe(true);
    naptarHid.allapotKer();
    expect(kuldott).toEqual([{ tipus: 'naptar-engedely', esemeny: true, emlekezteto: false }, { tipus: 'naptar-allapot' }]);
  });

  it('a `naptarEngedely` válasz a store-ba kerül, a kérés-állapot lezárul, a figyelők értesülnek', () => {
    hejTelepit();
    const kapott: [unknown, boolean][] = [];
    const le = naptarHid.figyel((v, kerdesre) => kapott.push([v, kerdesre]));
    naptarHid.kerd();
    naptarHid.fogad({ esemeny: 'engedelyezve', emlekezteto: 'megtagadva' });
    expect(naptarHid.engedely).toEqual({ esemeny: 'engedelyezve', emlekezteto: 'megtagadva' });
    expect(naptarHid.kerdesben).toBe(false);
    expect(naptarHid.hiba).toBeNull();
    expect(kapott[0][1]).toBe(true);
    naptarHid.fogad({ esemeny: 'engedelyezve', emlekezteto: 'engedelyezve' }); // kérés nélküli válasz
    expect(kapott[1][1]).toBe(false);
    le();
    naptarHid.fogad({ esemeny: 'nincs_dontes', emlekezteto: 'nincs_dontes' });
    expect(kapott).toHaveLength(2);
  });

  it('a hibás alakú válaszot eldobja, az ismeretlen állapotnevet null-ra hozza, a hibát megtartja', () => {
    naptarHid.fogad(null);
    naptarHid.fogad('szöveg');
    expect(naptarHid.engedely).toBeNull();
    naptarHid.fogad({ esemeny: 'valami', emlekezteto: 3, hiba: 'a rendszer megszakította' });
    expect(naptarHid.engedely).toEqual({ esemeny: null, emlekezteto: null });
    expect(naptarHid.hiba).toBe('a rendszer megszakította');
  });

  it('a válasz utómunkája: a core engedélye frissül (frissit=1), a kapott olvasási engedélynél egy kör indul', async () => {
    const utemez = vi.spyOn(maAdat, 'utemez').mockImplementation(() => {});
    await engedelyValasz({ esemeny: 'engedelyezve', emlekezteto: 'engedelyezve' }, true);
    expect(kerelmek.map((k) => `${k.metodus} ${k.url}`)).toEqual(['GET /api/naptar/allapot?frissit=1', 'POST /api/naptar/szinkron']);
    expect(utemez).toHaveBeenCalled();
    expect(ertesitesek.lista.map((e) => e.cim)).toEqual(['A naptár-hozzáférés engedélyezve']);
  });

  it('ha az olvasás már megy, nincs új kör; a megtagadás és a hiba értesít, kör nélkül', async () => {
    vi.spyOn(maAdat, 'utemez').mockImplementation(() => {});
    allapotValasz = alapAllapot({ naptar: { allapot: 'engedelyezve', uj: 0, valtozott: 0, torolt: 0, osszes: 3, valtozasok: [], blokkok: 0 } });
    await engedelyValasz({ esemeny: 'engedelyezve', emlekezteto: 'engedelyezve' }, false);
    expect(kerelmek.map((k) => k.metodus)).toEqual(['GET']);
    expect(ertesitesek.lista).toHaveLength(0); // kérés nélküli válasznál nincs értesítés

    kerelmek.length = 0;
    allapotValasz = alapAllapot({ esemeny_engedely: 'megtagadva' });
    await engedelyValasz({ esemeny: 'megtagadva', emlekezteto: 'megtagadva' }, true);
    expect(kerelmek.map((k) => k.metodus)).toEqual(['GET']);
    expect(ertesitesek.lista[0].cim).toBe('A naptár-hozzáférés nincs engedélyezve');
    expect(ertesitesek.lista[0].szoveg).toContain('megtagadva');

    await engedelyValasz({ hiba: 'a rendszer nem válaszolt' }, true);
    expect(ertesitesek.lista.at(-1)?.szint).toBe('hiba');
    expect(ertesitesek.lista.at(-1)?.szoveg).toBe('a rendszer nem válaszolt');
  });
});

describe('a parancsok', () => {
  it('a két parancs magyar címmel regisztrálódik, gyorsbillentyű nélkül; a leiratkozás eltávolítja őket', () => {
    const reg = new Regiszter();
    const le = naptarTelepit(reg, new Felulet(), new CoreKapcsolat('ws://x'));
    const szinkron = reg.kap('naptar.szinkron')!;
    const engedely = reg.kap('naptar.engedely')!;
    expect(szinkron.nev).toBe('Naptár szinkronizálása');
    expect(engedely.nev).toBe('Naptár-engedély kérése…');
    expect(szinkron.billentyu).toBeUndefined();
    expect(engedely.billentyu).toBeUndefined();
    expect(szinkron.kategoria).toBe('Napló');
    le();
    expect(reg.kap('naptar.szinkron')).toBeUndefined();
  });

  it('az engedély-parancs csak a héjban érhető el, és a híd üzenetét küldi', () => {
    const reg = new Regiszter();
    const le = naptarTelepit(reg, new Felulet(), new CoreKapcsolat('ws://x'));
    expect(reg.lista().some((p) => p.id === 'naptar.engedely')).toBe(false);
    hejTelepit();
    expect(reg.lista().some((p) => p.id === 'naptar.engedely')).toBe(true);
    reg.futtat('naptar.engedely', 'paletta');
    expect(kuldott).toEqual([{ tipus: 'naptar-engedely', esemeny: true, emlekezteto: true }]);
    le();
  });

  it('a „Naptár szinkronizálása” egy kört indít, és az eredményt értesítésben mondja', async () => {
    vi.spyOn(maAdat, 'utemez').mockImplementation(() => {});
    allapotValasz = alapAllapot({ naptar: { allapot: 'engedelyezve', uj: 0, valtozott: 2, torolt: 0, osszes: 12, valtozasok: [], blokkok: 1 } });
    const reg = new Regiszter();
    const le = naptarTelepit(reg, new Felulet(), new CoreKapcsolat('ws://x'));
    await reg.kap('naptar.szinkron')!.futtat();
    expect(kerelmek.some((k) => k.metodus === 'POST' && k.url === '/api/naptar/szinkron')).toBe(true);
    expect(ertesitesek.lista[0]).toMatchObject({ szint: 'siker', cim: 'A naptár szinkronizálva', szoveg: '12 esemény (2 változott)' });
    le();
  });

  it('a szinkron hibája hiba-értesítés', async () => {
    vi.spyOn(maAdat, 'utemez').mockImplementation(() => {});
    vi.stubGlobal('fetch', async () => json({ hiba: 'a segéd nem indult' }, 500));
    const reg = new Regiszter();
    const le = naptarTelepit(reg, new Felulet(), new CoreKapcsolat('ws://x'));
    await reg.kap('naptar.szinkron')!.futtat();
    expect(ertesitesek.lista[0].szint).toBe('hiba');
    expect(ertesitesek.lista[0].szoveg).toContain('a segéd nem indult');
    le();
  });
});

describe('az értesítések a WS-eseményekre', () => {
  let k: CoreKapcsolat;
  let felulet: Felulet;
  let le: () => void;
  beforeEach(() => {
    k = new CoreKapcsolat('ws://x');
    felulet = new Felulet();
    le = naptarTelepit(new Regiszter(), felulet, k);
  });
  afterEach(() => le());

  it('emlekezteto_utkozes: „A jegyzet nyert: …”, a részlettel; a „Megnyitás” a jegyzetet nyitja', () => {
    k.szetoszt({ tipus: 'emlekezteto_utkozes', id: 4, kulcs: 'k', ut: 'X01/Teendők.md', szoveg: 'Házi beadása', fajta: 'kesz', reszlet: 'Ellentétes pipálás.' });
    const e = ertesitesek.lista[0];
    expect(e.szint).toBe('figyelmeztetes');
    expect(e.cim).toBe('A jegyzet nyert: Házi beadása');
    expect(e.szoveg).toBe('ellentétes pipálás — Ellentétes pipálás.');
    e.muvelet!.futtat();
    expect(felulet.munkaterulet.aktivFul?.ut).toBe('X01/Teendők.md');
  });

  it('naptar_valtozas: átnevezett és eltűnt naptár; a szín és a kategória-esemény néma', () => {
    k.szetoszt({
      tipus: 'naptar_valtozas', allapot: 'engedelyezve', uj: 0, valtozott: 0, torolt: 0,
      valtozasok: [
        { azon: 'a', fajta: 'atnevezve', regi: 'Suli', uj: 'Órarend' },
        { azon: 'b', fajta: 'eltunt', regi: 'Edzés', uj: null },
        { azon: 'c', fajta: 'szin', regi: '#1', uj: '#2' },
      ],
    });
    k.szetoszt({ tipus: 'naptar_valtozas', allapot: 'kategoria', uj: 0, valtozott: 0, torolt: 0, valtozasok: [] });
    expect(ertesitesek.lista.map((e) => e.cim)).toEqual(['A(z) „Órarend” naptár átnevezve', 'A(z) „Edzés” naptár eltűnt']);
  });

  it('új naptár: csak ha a vezérlő listájában javaslat a kategóriája, naptáranként egyszer', async () => {
    allapotValasz = alapAllapot({
      naptarak: [
        { azon: 'n1', nev: 'Szakkör', forras: 'iCloud', szin: null, kategoria: 'egyeb', kategoria_forras: 'javaslat', eltunt: null },
        { azon: 'n2', nev: 'Edzés', forras: 'iCloud', szin: null, kategoria: 'edzes', kategoria_forras: 'auto', eltunt: null },
      ],
    });
    const esemeny = {
      tipus: 'naptar_valtozas', allapot: 'engedelyezve', uj: 0, valtozott: 0, torolt: 0,
      valtozasok: [
        { azon: 'n1', fajta: 'uj', regi: null, uj: 'Szakkör' },
        { azon: 'n2', fajta: 'uj', regi: null, uj: 'Edzés' },
      ],
    };
    k.szetoszt(esemeny);
    await vi.waitFor(() => expect(ertesitesek.lista).toHaveLength(1));
    expect(ertesitesek.lista[0].cim).toBe('Új naptár: „Szakkör”');
    expect(ertesitesek.lista[0].szoveg).toBe('A kategóriát a vezérlőben erősítheted meg.');
    ertesitesek.lista[0].muvelet!.futtat();
    expect(felulet.manifoldLap).toBe(true);
    expect(felulet.vezerlo.nyitott.naptar).toBe(true);
    ertesitesek.mindElvet();
    k.szetoszt(esemeny);
    await vi.waitFor(() => expect(kerelmek.filter((x) => x.url === '/api/naptar/allapot').length).toBe(2));
    await Promise.resolve();
    expect(ertesitesek.lista).toHaveLength(0); // már bejelentettük
  });

  it('naptar_javaslat: új javaslatnál egy halk értesítés; az elvetés és a beírás néma', () => {
    k.szetoszt({ tipus: 'naptar_javaslat', elvetett: 3 });
    k.szetoszt({ tipus: 'naptar_javaslat', beirva: 3 });
    expect(ertesitesek.lista).toHaveLength(0);
    k.szetoszt({ tipus: 'naptar_javaslat', uj: 2 });
    expect(ertesitesek.lista).toHaveLength(1);
    expect(ertesitesek.lista[0]).toMatchObject({ szint: 'info', cim: 'Új tanulási blokk javaslat a Ma oldalon' });
  });
});
