// A „Ma” oldal (C15): a szakaszok és az üres/hibás állapotaik, a dolgozat-kártya, a naptár, a napi jegyzet két
// állapota (parancsot futtat), a feladatok megnyitása a sorra, a régi naptár jelzése, a kártyák helyőrzője.

import { cleanup, fireEvent, render, screen, within } from '@testing-library/svelte';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { CoreKapcsolat } from '../src/lib/core/ws.svelte';
import { Felulet } from '../src/lib/elrendezes/felulet.svelte';
import { KORNYEZET_KULCS } from '../src/lib/kornyezet';
import { regiszter } from '../src/lib/parancsok/regiszter';
import { VaultFajlok } from '../src/lib/vault/fajlok.svelte';
import Ma from '../src/ma/Ma.svelte';
import { maAdat } from '../src/ma/modell.svelte';
import type { DolgozatSzakasz, MaValasz, NaptarSzakasz } from '../src/ma/tipusok';
import { szerkesztok } from '../src/szerkeszto/szerkesztok.svelte';

const NAPI = 'X01 - Napló & To-Do/2026-10/Napló/2026-10-02.md';
const FELKESZULES = 'X01 - Napló & To-Do/2026-10/Dolgozatok/2026-10-05 - Irodalom.md';

function alap(): MaValasz {
  return {
    datum: '2026-10-02',
    felirat: '2026. október 2., péntek',
    ma: true,
    napi: { ut: NAPI, letezik: false, kivonat: '' },
    dolgozatok: {
      lista: [
        { azon: 'e5', cim: 'Himnusz', nap: '2026-10-05', egesznap: false, ora: '10:35', hely: 'Berzsenyi - 117', szin: '#ff383c', napok: 3, jegyzet: FELKESZULES, kotes: 'valoszinu' },
        { azon: 'e6', cim: 'Német - Röpdolgozat', nap: '2026-10-06', egesznap: false, ora: '10:00', hely: '', szin: '#ff383c', napok: 4, jegyzet: null, kotes: null },
        { azon: 'e7', cim: 'Német - Röpdolgozat', nap: '2026-10-13', egesznap: false, ora: '10:00', hely: '', szin: '#ff383c', napok: 11, jegyzet: null, kotes: null },
      ],
      utolso_szinkron: '2026-10-02T06:00:00+02:00',
      regi: false,
    },
    naptar: {
      esemenyek: [
        { azon: 'a', cim: 'Mai egész napos', egesznap: true, kezd: '2026-10-02T00:00:00+02:00', veg: '2026-10-03T00:00:00+02:00', kezd_ora: '', veg_ora: '', hely: '', szin: '#ff8d28', kategoria: 'tanulas', naptar: 'Studying' },
        { azon: 'b', cim: 'Testnevelés', egesznap: false, kezd: '2026-10-02T08:55:00+02:00', veg: '2026-10-02T09:40:00+02:00', kezd_ora: '08:55', veg_ora: '09:40', hely: 'T2', szin: '#8b5cf6', kategoria: 'orarend', naptar: 'Órarend' },
      ],
      utolso_szinkron: '2026-10-02T06:00:00+02:00',
      regi: false,
    },
    feladatok: { ma: [], lejart: [], osszes_ma: 0, osszes_lejart: 0 },
    kartyak: { allapot: 'nincs', esedekes: 0 },
  };
}

let valasz: MaValasz;
let felulet: Felulet;
let context: Map<unknown, unknown>;

async function megjelenit(v: MaValasz = valasz) {
  valasz = v;
  await maAdat.frissit();
  return render(Ma, { context, props: { ful: { id: 'f1', ut: null, nezet: { tipus: 'ma' } }, info: undefined, aktiv: true } });
}

beforeEach(() => {
  valasz = alap();
  vi.stubGlobal('fetch', async (url: string) => new Response(JSON.stringify(String(url).includes('/api/tracker/') ? { napok: [], tantargyak: [], osszes: { aktiv_mp: 0 } } : valasz), { status: 200, headers: { 'Content-Type': 'application/json' } }));
  felulet = new Felulet({});
  context = new Map<unknown, unknown>([[KORNYEZET_KULCS, { felulet, fajlok: new VaultFajlok(), kapcsolat: new CoreKapcsolat('ws://x') }]]);
});

afterEach(() => {
  cleanup();
  document.body.textContent = '';
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

const szakasz = (nev: string | RegExp) => screen.getByRole('region', { name: nev });

describe('szakaszok', () => {
  it('a dátumfej és az öt szakasz a jóváhagyott sorrendben', async () => {
    await megjelenit();
    expect(screen.getByRole('heading', { level: 1 }).textContent).toBe('Manifold');
    expect(screen.getByText('2026. október 2., péntek')).toBeTruthy();
    const cimek = screen.getAllByRole('heading', { level: 2 }).map((h) => h.textContent!.replace(/\s+/g, ' ').trim());
    expect(cimek).toEqual(['Tanulás a héten', 'Következő dolgozat / határidő', 'A nap', 'Napi jegyzet', 'Feladatok ma 0', 'Kártyák —']);
  });

  it('a következő dolgozat a nagy kártya (relatív nap, dátum, idő, hely), alatta a további kettő', async () => {
    await megjelenit();
    const s = szakasz('Következő dolgozat / határidő');
    expect(within(s).getByText('Himnusz')).toBeTruthy();
    expect(within(s).getByText('3 nap múlva · 2026. október 5. · 10:35 · Berzsenyi - 117')).toBeTruthy();
    const kicsi = within(s).getAllByRole('listitem');
    expect(kicsi).toHaveLength(2);
    expect(kicsi[0].textContent).toContain('okt. 6.');
    expect(kicsi[0].textContent).toContain('4 nap múlva');
    expect(kicsi[1].textContent).toContain('okt. 13.');
  });

  it('a felkészülési jegyzet gombja megnyitja a kötött jegyzetet (⌘: új fülben)', async () => {
    await megjelenit();
    const gomb = screen.getByRole('button', { name: 'Felkészülési jegyzet' });
    await fireEvent.click(gomb);
    expect(felulet.munkaterulet.aktivFul?.ut).toBe(FELKESZULES);
    await fireEvent.click(gomb, { metaKey: true });
    expect(felulet.munkaterulet.aktivPanel.fulek.filter((f) => f.ut === FELKESZULES).length).toBeGreaterThanOrEqual(1);
  });

  it('kötés nélküli dolgozatnál nincs jegyzet-gomb', async () => {
    const v = alap();
    const d = v.dolgozatok as DolgozatSzakasz;
    v.dolgozatok = { ...d, lista: [d.lista[1]] };
    await megjelenit(v);
    expect(screen.queryByRole('button', { name: 'Felkészülési jegyzet' })).toBeNull();
  });

  it('nincs közelgő határidő: egy halvány sor', async () => {
    const v = alap();
    v.dolgozatok = { lista: [], utolso_szinkron: null, regi: false };
    await megjelenit(v);
    expect(within(szakasz('Következő dolgozat / határidő')).getByText('Nincs közelgő határidő a naptárban.')).toBeTruthy();
  });

  it('a nap: az események idővel (egész napos elöl), hellyel', async () => {
    await megjelenit();
    const sorok = within(szakasz('A nap')).getAllByRole('listitem').map((l) => l.textContent!.replace(/\s+/g, ' ').trim());
    expect(sorok).toEqual(['egész nap Mai egész napos', '08:55–09:40 Testnevelés T2']);
  });

  it('üres naptár: egy sor', async () => {
    const v = alap();
    v.naptar = { esemenyek: [], utolso_szinkron: null, regi: false };
    await megjelenit(v);
    expect(within(szakasz('A nap')).getByText('Nincs esemény a naptárban.')).toBeTruthy();
  });
});

describe('napi jegyzet', () => {
  let futott: string[];
  beforeEach(() => {
    futott = [];
    vi.spyOn(regiszter, 'futtat').mockImplementation(((id: string) => {
      futott.push(id);
      return true;
    }) as never);
  });

  it('nincs még: „Létrehozás” a parancsot futtatja', async () => {
    await megjelenit();
    const s = szakasz('Napi jegyzet');
    expect(within(s).getByText('Még nincs.')).toBeTruthy();
    await fireEvent.click(within(s).getByRole('button', { name: /Létrehozás/ }));
    expect(futott).toEqual(['naplo.napi']);
  });

  it('van: a név, a kivonat és a „Megnyitás” a parancsot futtatja', async () => {
    const v = alap();
    v.napi = { ut: NAPI, letezik: true, kivonat: 'mostanában egyre jobban fáradok.' };
    await megjelenit(v);
    const s = szakasz('Napi jegyzet');
    expect(within(s).getByText('2026-10-02')).toBeTruthy();
    expect(within(s).getByText('mostanában egyre jobban fáradok.')).toBeTruthy();
    await fireEvent.click(within(s).getByRole('button', { name: /Megnyitás/ }));
    expect(futott).toEqual(['naplo.napi']);
  });

  it('üres jegyzetnél „A jegyzet még üres.”', async () => {
    const v = alap();
    v.napi = { ut: NAPI, letezik: true, kivonat: '' };
    await megjelenit(v);
    expect(within(szakasz('Napi jegyzet')).getByText('A jegyzet még üres.')).toBeTruthy();
  });
});

describe('feladatok', () => {
  it('üresen egy sor, a súgóval a tooltipben', async () => {
    await megjelenit();
    const sor = within(szakasz(/Feladatok ma/)).getByText('Nincs mára esedékes feladat.');
    expect(sor.getAttribute('title')).toContain('📅 ÉÉÉÉ-HH-NN');
  });

  it('a mai és a lejárt feladat; a sorra kattintva megnyílik a jegyzet és a sorra ugrik', async () => {
    const v = alap();
    v.feladatok = {
      ma: [{ ut: 'Tennivalók.md', sor: 4, szoveg: 'ütemezett', hatarido: null, utemezve: '2026-10-02' }],
      lejart: [{ ut: 'Más/Lejárt.md', sor: 2, szoveg: 'lejárt', hatarido: '2026-09-30', utemezve: null }],
      osszes_ma: 1,
      osszes_lejart: 1,
    };
    await megjelenit(v);
    const ugras = vi.spyOn(szerkesztok, 'ugras').mockImplementation(() => {});
    const s = szakasz(/Feladatok ma/);
    expect(within(s).getByRole('heading', { level: 3 }).textContent!.replace(/\s+/g, ' ').trim()).toBe('Lejárt 1');
    expect(within(s).getByText('szept. 30.')).toBeTruthy();
    await fireEvent.click(within(s).getByRole('button', { name: /ütemezett/ }));
    expect(felulet.munkaterulet.aktivFul?.ut).toBe('Tennivalók.md');
    expect(ugras).toHaveBeenCalledWith('Tennivalók.md', 4);
    await fireEvent.click(within(s).getByRole('button', { name: /lejárt/ }));
    expect(ugras).toHaveBeenLastCalledWith('Más/Lejárt.md', 2);
  });
});

describe('állapotok', () => {
  it('a régi naptáradat jelzése a fejben, egyszer', async () => {
    const v = alap();
    v.naptar = { ...(v.naptar as NaptarSzakasz), regi: true, utolso_szinkron: '2026-09-27T22:00:29+02:00' };
    await megjelenit(v);
    expect(screen.getAllByText('Az itt látott naptár a 2026. szeptember 27-i állapot.')).toHaveLength(1);
  });

  it('friss adatnál nincs jelzés', async () => {
    await megjelenit();
    expect(screen.queryByText(/Az itt látott naptár/)).toBeNull();
  });

  it('az elérhetetlen forrás csak a saját szakaszát viszi el', async () => {
    const v = alap();
    v.naptar = { hiba: 'nincs naptáradat (pos.sqlite): a naptár-szinkron a C29-ben készül' };
    v.dolgozatok = { hiba: 'nincs naptáradat (pos.sqlite): a naptár-szinkron a C29-ben készül' };
    await megjelenit(v);
    expect(within(szakasz('A nap')).getByText(/nincs naptáradat/i)).toBeTruthy();
    expect(within(szakasz('Következő dolgozat / határidő')).getByText(/nincs naptáradat/i)).toBeTruthy();
    expect(within(szakasz('Napi jegyzet')).getByText('Még nincs.')).toBeTruthy(); // a többi szakasz él
    expect(screen.queryByRole('alert')).toBeNull();
  });

  it('a kártyák (C23b): esedékes, új, holnap és az Ismétlés gomb; a régi core helyőrzője „—”', async () => {
    await megjelenit();
    expect(szakasz(/^Kártyák/).querySelector('.szam')?.textContent).toBe('—');
    cleanup();
    const v = alap();
    v.kartyak = { allapot: 'kesz', esedekes: 3, uj: 2, holnap: 4, osszes: 40 };
    await megjelenit(v);
    const sz = szakasz(/^Kártyák/);
    expect(sz.querySelector('.szam')?.textContent).toBe('5');
    expect(sz.textContent).toContain('3 esedékes · 2 új · holnap 4');
    expect(within(sz).getByRole('button', { name: 'Ismétlés' })).toBeTruthy();
  });

  it('a teljes betöltési hiba riasztás, a szakaszok nélkül', async () => {
    maAdat.adat = null;
    vi.stubGlobal('fetch', async () => new Response(JSON.stringify({ hiba: 'az index még épül' }), { status: 503, headers: { 'Content-Type': 'application/json' } }));
    await maAdat.frissit();
    render(Ma, { context, props: { ful: { id: 'f1', ut: null, nezet: { tipus: 'ma' } }, info: undefined, aktiv: false } });
    expect((await screen.findByRole('alert')).textContent).toContain('az index még épül');
  });
});
