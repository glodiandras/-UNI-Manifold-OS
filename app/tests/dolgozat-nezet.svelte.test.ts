// A dolgozat-oldal (C28a): a szám és a „nincs adat” állapot, a témák és az összetevők lefúrása, a gyenge pontok, a napi
// terv, a dolgozat-váltó, a megnyitás, a hiba- és üres állapotok. A számok mindig szövegben is látszanak.

import { cleanup, fireEvent, render, screen, within } from '@testing-library/svelte';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import Dolgozat from '../src/dolgozat/Dolgozat.svelte';
import { dolgozatAdat } from '../src/dolgozat/modell.svelte';
import type { DolgozatSor, ListaValasz, Reszlet } from '../src/dolgozat/tipusok';
import { CoreKapcsolat } from '../src/lib/core/ws.svelte';
import { Felulet } from '../src/lib/elrendezes/felulet.svelte';
import { KORNYEZET_KULCS } from '../src/lib/kornyezet';
import { VaultFajlok } from '../src/lib/vault/fajlok.svelte';
import { FELK, T1, T2, T3, json, lista, reszlet, sor, tema } from './dolgozat-fixture';

let l: ListaValasz;
let r: Reszlet;
let felulet: Felulet;
let context: Map<unknown, unknown>;
let kerelmek: string[];
let ful: { id: string; ut: null; nezet: Record<string, unknown> };

async function megjelenit() {
  await dolgozatAdat.frissit();
  return render(Dolgozat, { context, props: { ful, info: undefined, aktiv: true } });
}

beforeEach(() => {
  Object.assign(dolgozatAdat, { lista: null, reszlet: null, valasztott: null, hiba: null, reszletHiba: null, betoltve: false });
  l = lista();
  r = reszlet();
  kerelmek = [];
  ful = { id: 'f1', ut: null, nezet: { tipus: 'dolgozat' } };
  vi.stubGlobal('fetch', async (url: string) => {
    kerelmek.push(url);
    return url.includes('/dolgozat?') ? json(r) : json(l);
  });
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

describe('szám nélkül (a ma jellemző állapot: nincs kártya, kvíz, tracker)', () => {
  it('a fej: cím, relatív nap, dátum, tantárgy; a szám helyén „—” és hogy mi hiányzik', async () => {
    await megjelenit();
    expect(screen.getByRole('heading', { level: 1 }).textContent).toBe('Matek témazáró');
    expect(screen.getByText('4 nap múlva · 2026. október 7. · 10:00 · Matematika')).toBeTruthy();
    const fej = szakasz('Felkészültség');
    expect(within(fej).getByText('—')).toBeTruthy();
    expect(within(fej).getByText('nincs adat')).toBeTruthy();
    expect(within(fej).getByText(/Még nincs elég mért adat a számhoz/)).toBeTruthy();
    expect(within(fej).getByText(/kártya: még nincs kártya/)).toBeTruthy();
    expect(within(fej).getByText(/kvíz: nincs kvíz-adatforrás/)).toBeTruthy();
    expect(within(fej).getByText(/biztos kötés/)).toBeTruthy();
  });

  it('a három téma „nincs adat”-tal, a források az oldalakkal', async () => {
    await megjelenit();
    const s = szakasz(/Témák/);
    expect(within(s).getAllByRole('meter')).toHaveLength(3);
    expect(within(s).getAllByRole('meter')[0].getAttribute('aria-valuetext')).toBe('nincs adat');
    expect(within(s).getByText(/Források:.*11 - Matematika\.pdf \(18–19, 28\. oldal\)/)).toBeTruthy();
  });

  it('a Próbakvíz és a Mai ismétlés gomb tiltott, a magyarázat a szövegben áll', async () => {
    await megjelenit();
    expect((screen.getByRole('button', { name: 'Próbakvíz' }) as HTMLButtonElement).disabled).toBe(true);
    expect((screen.getByRole('button', { name: 'Mai ismétlés' }) as HTMLButtonElement).disabled).toBe(true);
    expect(screen.getByText('A kvíz a C22 után indítható.')).toBeTruthy();
  });

  it('a napi terv napjai a szeletekkel és a javaslat jelzésével', async () => {
    r = reszlet({
      terv: {
        uzenet: null,
        napok: [
          { nap: '2026-10-03', perc: 45, kartya_esedekes: 3, naptar: [{ kezd: '2026-10-03T17:00:00+02:00', veg: '2026-10-03T18:00:00+02:00', cim: 'Matek gyakorlás' }],
            javaslat: { id: 1, allapot: 'uj' }, szeletek: [{ tema_ut: T1, tema: '01 - Hatvány', perc: 30, ok: 'nincs adat' }, { tema_ut: T2, tema: '02 - Gyökvonás', perc: 15, ok: 'gyenge: 41%' }] },
        ],
      },
    });
    await megjelenit();
    const s = szakasz(/Napi terv/);
    expect(within(s).getByText('okt. 3.')).toBeTruthy();
    expect(within(s).getByText('01 - Hatvány')).toBeTruthy();
    expect(within(s).getByText('30 perc · nincs adat')).toBeTruthy();
    expect(within(s).getByText('15 perc · gyenge: 41%')).toBeTruthy();
    expect(within(s).getByText('kb. 3 esedékes')).toBeTruthy();
    expect(within(s).getByText('A naptárban: Matek gyakorlás')).toBeTruthy();
    expect(within(s).getByText('17:00–18:00')).toBeTruthy();
    expect(within(s).getByText(/naptár-javaslat \(jóváhagyásra vár\)/)).toBeTruthy();
  });

  it('a terv üzenete (nincs téma, a dolgozat ma van) látszik', async () => {
    r = reszlet({ temak: [], terv: { uzenet: 'A dolgozat ma van.', napok: [] } });
    await megjelenit();
    expect(screen.getByText('A dolgozat ma van.')).toBeTruthy();
    expect(screen.getByText(/Nincs téma: a felkészülési jegyzet/)).toBeTruthy();
  });
});

describe('számmal', () => {
  beforeEach(() => {
    l = lista([sor({ szam: 0.62, kilatas: 0.55, szint: 'kozepes', lefedettseg: { van: 2, osszes: 3 } })]);
    r = reszlet({
      szam: 0.62, kilatas: 0.55, szint: 'kozepes', lefedettseg: { van: 2, osszes: 3 }, gyenge_db: 1, nincs_adat_db: 1,
      temak: [tema(T1, '01 - Hatvány', 0.82), tema(T2, '02 - Gyökvonás', 0.41), tema(T3, '03 - Logaritmus', null)],
      gyenge_pontok: {
        temak: [{ ut: T2, nev: '02 - Gyökvonás', szam: 0.41 }], nincs_adat: [{ ut: T3, nev: '03 - Logaritmus' }],
        kartyak: [{ azon: 'c-1', kerdes: 'Mi a köbgyök?', felidezes: 0.31, tema: T2 }],
      },
      esedekes_kartya: 4, uj_kartya: 2,
    });
  });

  it('a nagy szám, a szint, a kilátás és a lefedettség szövegben', async () => {
    await megjelenit();
    const fej = szakasz('Felkészültség');
    expect(within(fej).getByText('62%')).toBeTruthy();
    expect(within(fej).getByText('közepes')).toBeTruthy();
    expect(within(fej).getByText(/Ha ma nem tanulsz többet:/).textContent).toContain('55%');
    expect(within(fej).getByText(/2 \/ 3 témára van mért adat/)).toBeTruthy();
    expect(within(fej).getByText(/kalibrálatlan induló értékek/)).toBeTruthy();
  });

  it('a téma-sávok ARIA-értékkel és szöveges százalékkal', async () => {
    await megjelenit();
    const m = within(szakasz(/Témák/)).getAllByRole('meter');
    expect(m[0].getAttribute('aria-valuenow')).toBe('82');
    expect(m[0].getAttribute('aria-valuetext')).toBe('82%, jó');
    expect(m[1].getAttribute('aria-valuetext')).toBe('41%, gyenge');
    expect(m[2].getAttribute('aria-valuetext')).toBe('nincs adat');
    expect(within(szakasz(/Témák/)).getByText('82%')).toBeTruthy();
  });

  it('a „Hogyan?” kinyitja az összetevőket (érték, bizalom, súly, nyers adat)', async () => {
    await megjelenit();
    const gomb = within(szakasz(/Témák/)).getAllByRole('button', { name: 'Hogyan?' })[0];
    expect(gomb.getAttribute('aria-expanded')).toBe('false');
    await fireEvent.click(gomb);
    expect(gomb.getAttribute('aria-expanded')).toBe('true');
    const t = screen.getByRole('table');
    expect(within(t).getByText('Kártya (átlagos felidézés)')).toBeTruthy();
    expect(within(t).getByText('6 kártya, ebből 1 új')).toBeTruthy();
    expect(within(t).getByText('3 napja tanultál utoljára')).toBeTruthy();
    expect(within(t).getByText('nincs kvízeredmény')).toBeTruthy();
    expect(within(t).getByText('30 perc')).toBeTruthy();
    await fireEvent.click(gomb);
    expect(screen.queryByRole('table')).toBeNull();
  });

  it('a gyenge pontok: gyenge téma, nincs adat, leggyengébb kártya', async () => {
    await megjelenit();
    const s = szakasz('Gyenge pontok');
    expect(within(s).getByText('gyenge: 41%')).toBeTruthy();
    expect(within(s).getByText('nincs mért adat')).toBeTruthy();
    expect(within(s).getByText('Mi a köbgyök?')).toBeTruthy();
    expect(within(s).getByText('31%')).toBeTruthy();
  });

  it('az esedékes kártyák száma szövegben', async () => {
    await megjelenit();
    expect(within(szakasz(/Esedékes kártyák/)).getByText(/4 esedékes és 2 új/)).toBeTruthy();
  });

  it('a témára kattintva megnyílik a jegyzet', async () => {
    await megjelenit();
    await fireEvent.click(within(szakasz(/Témák/)).getByRole('button', { name: '01 - Hatvány' }));
    expect(felulet.munkaterulet.aktivFul?.ut).toBe(T1);
  });

  it('a felkészülési jegyzet gombja megnyitja a kötött jegyzetet', async () => {
    await megjelenit();
    await fireEvent.click(within(szakasz('Felkészültség')).getByRole('button', { name: /2026-10-07 - Matematika/ }));
    expect(felulet.munkaterulet.aktivFul?.ut).toBe(FELK);
  });

  it('az átnevezés előtti útvonalak említése a lefúrásban', async () => {
    r.temak[0].aliasok = ['M06/Régi Hatvány.md'];
    await megjelenit();
    await fireEvent.click(within(szakasz(/Témák/)).getAllByRole('button', { name: 'Hogyan?' })[0]);
    expect(screen.getByText(/átnevezés előtti útvonalakat is tartalmazza: Régi Hatvány\./)).toBeTruthy();
  });
});

describe('dolgozat-váltó, lezárt, régi naptár, hibák', () => {
  it('több dolgozatnál választó; a váltás a részletet a másik dolgozatra tölti', async () => {
    const d2: DolgozatSor = sor({ azon: 'd2|x', cim: 'Fizika dolgozat', nap: '2026-10-09', napok: 6 });
    l = lista([sor(), d2]);
    await megjelenit();
    const valaszto = screen.getByRole('combobox') as HTMLSelectElement;
    expect(Array.from(valaszto.options).map((o) => o.textContent?.trim())).toEqual(['okt. 7. · Matek témazáró', 'okt. 9. · Fizika dolgozat']);
    kerelmek.length = 0;
    r = reszlet({ azon: 'd2|x', cim: 'Fizika dolgozat' });
    await fireEvent.change(valaszto, { target: { value: 'd2|x' } });
    await vi.waitFor(() => expect(screen.getByRole('heading', { level: 1 }).textContent).toBe('Fizika dolgozat'));
    expect(kerelmek[0]).toBe(`/api/felkeszultseg/dolgozat?azon=${encodeURIComponent('d2|x')}`);
    expect(ful.nezet.azon).toBe('d2|x');
  });

  it('egy dolgozatnál nincs választó', async () => {
    await megjelenit();
    expect(screen.queryByRole('combobox')).toBeNull();
  });

  it('a lezárt dolgozat jelzett, kilátás nélkül', async () => {
    l = lista([sor({ lezart: true, napok: -1, szam: 0.7, szint: 'kozepes' })]);
    r = reszlet({ lezart: true, napok: -1, szam: 0.7, kilatas: null, szint: 'kozepes', lefedettseg: { van: 3, osszes: 3 } });
    await megjelenit();
    expect(screen.getByText(/már lezárult: a számok a mostani állapotot mutatják/)).toBeTruthy();
    expect(screen.queryByText(/Ha ma nem tanulsz többet/)).toBeNull();
  });

  it('régi naptáradat jelzése', async () => {
    r = reszlet({ naptar: { utolso_szinkron: '2026-09-27T08:00:00+02:00', regi: true } });
    await megjelenit();
    expect(screen.getByText(/Az itt látott naptár a 2026\. szeptember 27-i állapot/)).toBeTruthy();
  });

  it('a core figyelmeztetései megjelennek', async () => {
    r = reszlet({ figyelmeztetesek: ['A felkészülési jegyzet kötése nem biztos (athelyezve): áthelyezték?'] });
    await megjelenit();
    expect(screen.getByText(/kötése nem biztos/)).toBeTruthy();
  });

  it('nincs dolgozat: üres állapot a core üzenetével', async () => {
    l = lista([], { hiba: 'nincs naptáradat: a naptár-szinkron még nem futott' });
    await megjelenit();
    expect(screen.getByText(/nincs naptáradat/i)).toBeTruthy();
  });

  it('nincs dolgozat hiba nélkül: magyar üres mondat', async () => {
    l = lista([]);
    await megjelenit();
    expect(screen.getByText('Nincs közelgő dolgozat a naptárban.')).toBeTruthy();
  });

  it('a lista hibája role="alert"', async () => {
    vi.stubGlobal('fetch', async () => json({ hiba: 'az index még épül' }, 503));
    await megjelenit();
    expect(screen.getByRole('alert').textContent).toContain('az index még épül');
  });

  it('a részlet hibája role="alert"', async () => {
    vi.stubGlobal('fetch', async (url: string) => (url.includes('/dolgozat?') ? json({ hiba: 'nincs ilyen dolgozat' }, 404) : json(l)));
    await megjelenit();
    expect(screen.getByRole('alert').textContent).toContain('nincs ilyen dolgozat');
  });

  it('betöltés előtt „Betöltés…”', () => {
    render(Dolgozat, { context, props: { ful, info: undefined, aktiv: false } });
    expect(screen.getByRole('status').textContent).toContain('Betöltés');
  });
});
