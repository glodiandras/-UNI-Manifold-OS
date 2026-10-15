// A dolgozat-oldal C28b-s részei: a lezárt dolgozat kinyert eredménye, a szöveges értékelés (a helyi modell kattintásra fut; D9: próba
// jelzése; a szám-kapu bukása; elavult értékelés) és az önkalibráció állapota (ma: nem teljesíthető — kimondva).

import { cleanup, fireEvent, render, screen, within } from '@testing-library/svelte';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import Dolgozat from '../src/dolgozat/Dolgozat.svelte';
import { dolgozatAdat } from '../src/dolgozat/modell.svelte';
import type { ListaValasz, Reszlet } from '../src/dolgozat/tipusok';
import { CoreKapcsolat } from '../src/lib/core/ws.svelte';
import { Felulet } from '../src/lib/elrendezes/felulet.svelte';
import { KORNYEZET_KULCS } from '../src/lib/kornyezet';
import { VaultFajlok } from '../src/lib/vault/fajlok.svelte';
import { T1, T2, T3, ertekeles, json, kalibracio, lista, reszlet, sor, tema } from './dolgozat-fixture';

let l: ListaValasz;
let r: Reszlet;
let context: Map<unknown, unknown>;
let kerelmek: string[];
let torzsek: unknown[];
let ful: { id: string; ut: null; nezet: Record<string, unknown> };

type Valaszado = () => Response | Promise<Response>;

/** A `fetch` ál-válasza: a lista/részlet a megszokott, az értékelés és a kalibráció a megadott. */
function stub(felul: { ertekeles?: Valaszado; kalibracio?: Valaszado } = {}) {
  vi.stubGlobal('fetch', async (url: string, init?: RequestInit) => {
    kerelmek.push(url);
    if (url.includes('/ertekeles')) {
      torzsek.push(JSON.parse(String(init?.body)));
      return (felul.ertekeles ?? (() => json(ertekeles())))();
    }
    if (url.includes('/kalibracio')) return (felul.kalibracio ?? (() => json(kalibracio())))();
    return url.includes('/dolgozat?') ? json(r) : json(l);
  });
}

async function megjelenit() {
  await dolgozatAdat.frissit();
  return render(Dolgozat, { context, props: { ful, info: undefined, aktiv: true } });
}

beforeEach(() => {
  Object.assign(dolgozatAdat, {
    lista: null, reszlet: null, valasztott: null, hiba: null, reszletHiba: null, betoltve: false,
    ertekeles: null, ertekelesFut: false, ertekelesHiba: null, kalibracio: null, kalibracioHiba: null, kalibracioTolt: false,
  });
  // a kalibráció elavult-jelzője privát: egy változás-esemény állítja vissza (utemez), látszó nézet nélkül nem tölt
  dolgozatAdat.utemez();
  l = lista();
  r = reszlet();
  kerelmek = [];
  torzsek = [];
  ful = { id: 'f1', ut: null, nezet: { tipus: 'dolgozat' } };
  stub();
  context = new Map<unknown, unknown>([[KORNYEZET_KULCS, { felulet: new Felulet({}), fajlok: new VaultFajlok(), kapcsolat: new CoreKapcsolat('ws://x') }]]);
});

afterEach(() => {
  cleanup();
  document.body.textContent = '';
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

const szakasz = (nev: string | RegExp) => screen.getByRole('region', { name: nev });

const szamos = (felul: Partial<Reszlet> = {}) =>
  reszlet({
    szam: 0.62, kilatas: 0.55, szint: 'kozepes', lefedettseg: { van: 2, osszes: 3 }, ertekeles_kulcs: 'kulcs-1',
    temak: [tema(T1, '01 - Hatvány', 0.82), tema(T2, '02 - Gyökvonás', 0.41), tema(T3, '03 - Logaritmus', null)], ...felul,
  });

describe('a lezárt dolgozat eredménye', () => {
  it('a kinyert eredmény szövegben, pontokkal és a kiértékelő forrásával', async () => {
    r = reszlet({ lezart: true, napok: -1, eredmeny: { pont: 16, max: 23, szazalek: 69.6, forras: '16/23', szakasz: 'Szeptember 08', jegyzet: 'X/2026-09 - Dolgozat Napló.md' } });
    await megjelenit();
    const fej = szakasz('Felkészültség');
    const sor_ = within(fej).getByText(/A dolgozat eredménye:/);
    expect(sor_.textContent).toContain('69,6%');
    expect(sor_.textContent).toContain('16 / 23 pont');
    expect(within(fej).getByText(/a kiértékelő jegyzet szövegéből: „16\/23”/)).toBeTruthy();
    // C28c: a szövegből jött eredmény mellé a mező tippje
    expect(within(fej).getByText(/Egyértelműbb eredményhez/).textContent).toContain('Eredmény:: 16/23');
  });

  it('C28c: a szabott mezőből jött eredmény megmondja az eredetét, tipp nélkül', async () => {
    r = reszlet({ lezart: true, napok: -1, eredmeny: { pont: 16, max: 23, szazalek: 69.6, forras: 'Eredmény:: 16/23', szakasz: 's', jegyzet: 'j', eredet: 'mezo' } });
    await megjelenit();
    const fej = szakasz('Felkészültség');
    const jel = fej.querySelector('[data-eredet="mezo"]');
    expect(jel?.textContent).toContain('„Eredmény::” mezőből');
    expect(jel?.querySelector('code')?.textContent).toBe('Eredmény:: 16/23');
    expect(within(fej).queryByText(/Egyértelműbb eredményhez/)).toBeNull();
  });

  it('C28c: a hibás mező oka és a javítás tippje látszik', async () => {
    r = reszlet({
      lezart: true, napok: -1, eredmeny: null,
      eredmeny_ellentmondas: { ok: 'a mezőben a pont és a százalék ellentmond', jeloltek: [{ forras: 'Eredmény:: 18/31 (68%)', szazalek: null }],
        szakasz: 's', jegyzet: 'j', eredet: 'mezo' },
    });
    await megjelenit();
    const fej = szakasz('Felkészültség');
    expect(within(fej).getByText(/„Eredmény::” mezője nem használható: a mezőben a pont és a százalék ellentmond/)).toBeTruthy();
    expect(within(fej).getByText(/Javításként/)).toBeTruthy();
  });

  it('C28c: lezárt dolgozat eredmény nélkül: a mező tippje', async () => {
    r = reszlet({ lezart: true, napok: -1, eredmeny: null });
    await megjelenit();
    expect(within(szakasz('Felkészültség')).getByText(/Az eredmény megadásához/)).toBeTruthy();
  });

  it('százalékos eredmény pont nélkül', async () => {
    r = reszlet({ lezart: true, napok: -1, eredmeny: { pont: null, max: null, szazalek: 85, forras: '85%', szakasz: 'x', jegyzet: 'y' } });
    await megjelenit();
    const t = within(szakasz('Felkészültség')).getByText(/A dolgozat eredménye:/).textContent ?? '';
    expect(t).toContain('85%');
    expect(t).not.toContain('pont)');
  });

  it('ellentmondó eredmény: a két érték és a javítási kérés látszik, eredmény nincs', async () => {
    r = reszlet({
      lezart: true, napok: -1, eredmeny: null,
      eredmeny_ellentmondas: { ok: 'x', jeloltek: [{ forras: '68%', szazalek: 68 }, { forras: '18/31', szazalek: 58.1 }], szakasz: 's', jegyzet: 'j' },
    });
    await megjelenit();
    const fej = szakasz('Felkészültség');
    expect(within(fej).getByText(/ellentmondó eredmény áll \(68% · 18\/31\)/)).toBeTruthy();
    expect(within(fej).queryByText(/A dolgozat eredménye:/)).toBeNull();
  });

  it('eredmény nélkül semmi nem jelenik meg', async () => {
    await megjelenit();
    expect(screen.queryByText(/A dolgozat eredménye:/)).toBeNull();
    expect(screen.queryByText(/ellentmondó eredmény/)).toBeNull();
  });
});

describe('szöveges értékelés', () => {
  it('szám nélkül nincs gomb, hanem magyarázat', async () => {
    await megjelenit();
    const s = szakasz('Szöveges értékelés');
    expect(within(s).getByText(/Mért tudás \(kártya vagy kvíz\) nélkül nincs mit szavakba önteni/)).toBeTruthy();
    expect(within(s).queryByRole('button')).toBeNull();
  });

  it('a gomb az azonosítót küldi, és a szöveget a modell nevével mutatja', async () => {
    r = szamos();
    await megjelenit();
    const s = szakasz('Szöveges értékelés');
    await fireEvent.click(within(s).getByRole('button', { name: 'Értékelés kérése' }));
    await vi.waitFor(() => expect(within(s).getByText(/A felkészültséged most 62%/)).toBeTruthy());
    expect(torzsek).toEqual([{ azon: r.azon }]);
    expect(within(s).getByText(/Kalibrált helyi modell \(qwen35_9b\)/)).toBeTruthy();
    expect(within(s).getByText(/ezt a program ellenőrizte\./)).toBeTruthy();
    expect(within(s).getByRole('button', { name: 'Új értékelés' })).toBeTruthy();
  });

  it('próba (D9): a modell nincs kalibrálva — kimondja, és a második próbálkozást is', async () => {
    r = szamos();
    stub({ ertekeles: () => json(ertekeles({ proba: true, kalibralt: false, modell: 'qwen35_4b', probalkozas: 2 })) });
    await megjelenit();
    const s = szakasz('Szöveges értékelés');
    await fireEvent.click(within(s).getByRole('button', { name: 'Értékelés kérése' }));
    await vi.waitFor(() => expect(within(s).getByText(/Próba — a modell \(qwen35_4b\) erre a feladatra nincs kalibrálva/)).toBeTruthy());
    expect(within(s).getByText(/a második próbálkozásra sikerült/)).toBeTruthy();
  });

  it('futás közben a gomb tiltott és jelzi, hogy a modell dolgozik', async () => {
    r = szamos();
    let kiad: (v: Response) => void = () => {};
    stub({ ertekeles: () => new Promise<Response>((res) => (kiad = res)) });
    await megjelenit();
    const s = szakasz('Szöveges értékelés');
    await fireEvent.click(within(s).getByRole('button', { name: 'Értékelés kérése' }));
    const gomb = await within(s).findByRole('button', { name: 'A helyi modell dolgozik…' });
    expect((gomb as HTMLButtonElement).disabled).toBe(true);
    kiad(json(ertekeles()));
    await vi.waitFor(() => expect(within(s).getByRole('button', { name: 'Új értékelés' })).toBeTruthy());
  });

  it('kalibrált modell nélkül (503) a hiba role="alert"', async () => {
    r = szamos();
    stub({ ertekeles: () => json({ hiba: 'A szöveges értékelés modellje nincs kötve (a router-táblában nincs kalibrált `szoveg` modell).' }, 503) });
    await megjelenit();
    await fireEvent.click(within(szakasz('Szöveges értékelés')).getByRole('button', { name: 'Értékelés kérése' }));
    await vi.waitFor(() => expect(screen.getByRole('alert').textContent).toContain('nincs kalibrált `szoveg` modell'));
  });

  it('a kapu bukása: a szöveg nem jelenik meg, az üzenet igen', async () => {
    r = szamos();
    stub({
      ertekeles: () => json(ertekeles({
        allapot: 'kapu_bukott', szoveg: null, tiltott_szamok: ['97'],
        uzenet: 'A modell kétszer is olyan számot írt, amely nincs az adatok között — a szöveget nem mutatom.',
      })),
    });
    await megjelenit();
    const s = szakasz('Szöveges értékelés');
    await fireEvent.click(within(s).getByRole('button', { name: 'Értékelés kérése' }));
    await vi.waitFor(() => expect(within(s).getByText(/a szöveget nem mutatom/)).toBeTruthy());
    expect(within(s).queryByText(/A felkészültséged most/)).toBeNull();
  });

  it('ha a számok azóta változtak (más ujjlenyomat), jelzi', async () => {
    r = szamos();
    stub({ ertekeles: () => json(ertekeles({ kulcs: 'régi-kulcs' })) });
    await megjelenit();
    const s = szakasz('Szöveges értékelés');
    await fireEvent.click(within(s).getByRole('button', { name: 'Értékelés kérése' }));
    await vi.waitFor(() => expect(within(s).getByText(/A számok azóta változtak: kérj új értékelést\./)).toBeTruthy());
  });

  it('azonos ujjlenyomatnál nincs elavulás-jelzés', async () => {
    r = szamos();
    await megjelenit();
    const s = szakasz('Szöveges értékelés');
    await fireEvent.click(within(s).getByRole('button', { name: 'Értékelés kérése' }));
    await vi.waitFor(() => expect(within(s).getByText(/A felkészültséged most 62%/)).toBeTruthy());
    expect(within(s).queryByText(/A számok azóta változtak/)).toBeNull();
  });

  it('egy másik dolgozat részletén nem látszik az előző értékelése', async () => {
    r = szamos();
    l = lista([sor(), sor({ azon: 'd2|x', cim: 'Fizika dolgozat' })]);
    await megjelenit();
    await fireEvent.click(within(szakasz('Szöveges értékelés')).getByRole('button', { name: 'Értékelés kérése' }));
    await vi.waitFor(() => expect(screen.getByText(/A felkészültséged most 62%/)).toBeTruthy());
    r = szamos({ azon: 'd2|x', cim: 'Fizika dolgozat' });
    await fireEvent.change(screen.getByRole('combobox'), { target: { value: 'd2|x' } });
    await vi.waitFor(() => expect(screen.getByRole('heading', { level: 1 }).textContent).toBe('Fizika dolgozat'));
    expect(screen.queryByText(/A felkészültséged most 62%/)).toBeNull();
  });
});

describe('önkalibráció', () => {
  async function kinyit() {
    const reszek = screen.getByText('Önkalibráció és a becslés mért hibája').closest('details') as HTMLDetailsElement;
    reszek.open = true;
    await fireEvent(reszek, new Event('toggle'));
    return reszek;
  }

  it('nem tölt magától, csak a részlet megnyitásakor; a mai állapot: nem teljesíthető — kimondva', async () => {
    r = szamos();
    await megjelenit();
    expect(kerelmek.some((u) => u.includes('/kalibracio'))).toBe(false);
    const d = await kinyit();
    await vi.waitFor(() => expect(within(d).getByText('nem teljesíthető', { selector: 'strong' })).toBeTruthy());
    expect(within(d).getByText(/0 \/ 8 kalibrációs pont\./)).toBeTruthy();
    expect(within(d).getByText(/A súlyok addig nem változnak\./)).toBeTruthy();
    expect(within(d).getByText(/0 \/ 8 dolgozatra van egyszerre számszerű eredmény és mért tudás/)).toBeTruthy();
    expect(within(d).getByText(/A becslési hiba még nem mérhető/)).toBeTruthy();
    expect(kerelmek.filter((u) => u.includes('/kalibracio'))).toHaveLength(1);
  });

  it('kevés ponttal a mért hiba százalékpontban, kis minta jelzéssel, pontonkénti táblázattal és a kihagyottakkal', async () => {
    r = szamos();
    stub({
      kalibracio: () => json(kalibracio({
        pontok: 3, alap: { n: 3, rmse: 0.1234, mae: 0.1, torzitas: -0.05 },
        pontok_reszlet: [{ azon: 'a', cim: 'Matek témazáró', nap: '2026-09-14', eredmeny: 0.58, becsles: 0.62, hiba: 0.04, loo_becsles: 0.6 }],
        kihagyott: [{ azon: 'b', cim: 'Német', nap: '2026-09-15', ok: 'nincs mért tudás (kártya, kvíz) a D−3. napon' }],
      })),
    });
    await megjelenit();
    const d = await kinyit();
    await vi.waitFor(() => expect(within(d).getByText(/3 lezárt dolgozaton mért hiba: átlagosan 10 százalékpont/)).toBeTruthy());
    expect(within(d).getByText(/négyzetes átlag 12,3 százalékpont, torzítás -5 százalékpont/)).toBeTruthy();
    expect(within(d).getByText(/kevés a következtetéshez/)).toBeTruthy();
    expect(within(d).getByText('+4 százalékpont')).toBeTruthy();
    expect(within(d).getByText(/Kihagyva: .*Német \(nincs mért tudás/)).toBeTruthy();
  });

  it('a hiba role="alert"', async () => {
    r = szamos();
    stub({ kalibracio: () => json({ hiba: 'az index még épül' }, 503) });
    await megjelenit();
    await kinyit();
    await vi.waitFor(() => expect(screen.getByRole('alert').textContent).toContain('az index még épül'));
  });
});
