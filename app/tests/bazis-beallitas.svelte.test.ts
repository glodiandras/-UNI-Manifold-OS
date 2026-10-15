// A Bases nézet-beállításai (C12b 8. lépés) jsdom-ban ál-core-ral: rendezés a fejlécre kattintva, oszlop-átméretezés,
// -átrendezés, fejléc-menü, nézetek, szűrő- és képletmező élő ellenőrzéssel, oszlopválasztó, nézet-beállítások, YAML-forrás.

import { cleanup, fireEvent, render, waitFor } from '@testing-library/svelte';
import { afterEach, describe, expect, it, vi } from 'vitest';
import type { BazisApi } from '../src/bazis/api';
import BazisNezet from '../src/bazis/BazisNezet.svelte';
import { rogzitettForras, type BazisForras } from '../src/bazis/forras';
import Tabla from '../src/bazis/Tabla.svelte';
import type { Muvelet, Oszlop, Sor, Valasz } from '../src/bazis/tipusok';

const OSZLOPOK: Oszlop[] = [
  { id: 'file.name', nev: 'Fájlnév', ter: 'file', tipus: 'text', szerkesztheto: false, szelesseg: null },
  { id: 'Status', nev: 'Status', ter: 'note', tipus: 'text', szerkesztheto: true, szelesseg: null },
  { id: 'Rating', nev: 'Értékelés', ter: 'note', tipus: 'number', szerkesztheto: true, szelesseg: 90 },
  { id: 'Done', nev: 'Kész', ter: 'note', tipus: 'checkbox', szerkesztheto: true, szelesseg: null },
];

function sor(i: number): Sor {
  const ut = `K/Jegyzet ${i}.md`;
  return { ut, nev: `Jegyzet ${i}`, md: true, cellak: [{ t: 'link', cel: ut, ut, nev: `Jegyzet ${i}` }, 'Kész', i, i % 2 === 0] };
}

function valasz(beallitas: Record<string, unknown> = {}, kieg: Partial<Valasz> = {}): Valasz {
  return {
    ok: true,
    nezetek: [
      { nev: 'Táblázat', tipus: 'table', ismert: true },
      { nev: 'Kártyák', tipus: 'cards', ismert: true },
    ],
    nezet: { index: 0, nev: 'Táblázat', tipus: 'table', eredeti_tipus: 'table', beallitas },
    oszlopok: OSZLOPOK,
    sorok: [sor(1), sor(2)],
    csoportok: null,
    osszesitok: {},
    fajl: {
      szuro: '',
      szuro_nezet: 'Status != "x"',
      kepletek: { dupla: 'Rating * 2' },
      osszesitok: ['Sajat'],
      elerheto: [
        { id: 'file.name', nev: 'Fájlnév', ter: 'file', tipus: 'text' },
        { id: 'file.mtime', nev: 'Módosítva', ter: 'file', tipus: 'datetime' },
        { id: 'Status', nev: 'Status', ter: 'note', tipus: 'text' },
        { id: 'Rating', nev: 'Rating', ter: 'note', tipus: 'number' },
        { id: 'Done', nev: 'Done', ter: 'note', tipus: 'checkbox' },
        { id: 'formula.dupla', nev: 'dupla', ter: 'formula', tipus: 'formula' },
      ],
    },
    osszes: 2,
    levagva: false,
    hibak: [],
    figyelmeztetesek: [],
    ido_ms: 3,
    generacio: 1,
    ...kieg,
  };
}

afterEach(() => {
  cleanup();
  document.querySelectorAll('.nt-lebego').forEach((e) => e.remove());
});

const menuElem = (nev: string) => [...document.querySelectorAll<HTMLElement>('.nt-lebego .nt-menu-elem')].find((e) => e.querySelector('.nt-menu-nev')?.textContent === nev);

describe('Tabla: rendezés, méret, sorrend, menü', () => {
  const fejlecGomb = (c: HTMLElement, nev: string) => [...c.querySelectorAll<HTMLButtonElement>('.fejlec-gomb')].find((b) => b.textContent?.includes(nev))!;

  it('a fejléc-kattintás rendez: növekvő; ismét: csökkenő; ⇧: új kulcs', async () => {
    const muvelet = vi.fn();
    const { container, rerender } = render(Tabla, { props: { valasz: valasz(), irhato: true, muvelet } });
    await fireEvent.click(fejlecGomb(container, 'Értékelés'));
    expect(muvelet).toHaveBeenLastCalledWith({ fajta: 'nezet_beallit', nezet: 0, kulcs: 'sort', ertek: [{ property: 'Rating', direction: 'ASC' }] });
    await rerender({ valasz: valasz({ sort: [{ property: 'Rating', direction: 'ASC' }] }), irhato: true, muvelet });
    expect(container.querySelector('[aria-sort=ascending]')).not.toBeNull();
    await fireEvent.click(fejlecGomb(container, 'Értékelés'));
    expect(muvelet).toHaveBeenLastCalledWith(expect.objectContaining({ ertek: [{ property: 'Rating', direction: 'DESC' }] }));
    await fireEvent.click(fejlecGomb(container, 'Status'), { shiftKey: true });
    expect(muvelet).toHaveBeenLastCalledWith(
      expect.objectContaining({
        ertek: [
          { property: 'Rating', direction: 'DESC' }, // a második kattintás eredménye, még az új válasz előtt
          { property: 'Status', direction: 'ASC' },
        ],
      }),
    );
  });

  it('a gyors második kattintás az első eredményéből számol (nem várja meg az új választ)', async () => {
    const muvelet = vi.fn();
    const { container } = render(Tabla, { props: { valasz: valasz(), irhato: true, muvelet } });
    await fireEvent.click(fejlecGomb(container, 'Értékelés'));
    await fireEvent.click(fejlecGomb(container, 'Értékelés'));
    expect(muvelet.mock.calls.map((c) => (c[0] as { ertek: unknown }).ertek)).toEqual([[{ property: 'Rating', direction: 'ASC' }], [{ property: 'Rating', direction: 'DESC' }]]);
  });

  it('csak olvasható nézetben a fejléc nem rendez, és nincs átméretező és menü', async () => {
    const muvelet = vi.fn();
    const { container } = render(Tabla, { props: { valasz: valasz(), irhato: false, muvelet } });
    expect(container.querySelector('.atmeret')).toBeNull();
    expect(container.querySelector('.fejlec-menu')).toBeNull();
    await fireEvent.click(fejlecGomb(container, 'Értékelés'));
    expect(muvelet).not.toHaveBeenCalled();
  });

  it('többkulcsú rendezésnél a fejléc sorszámot mutat', () => {
    const { container } = render(Tabla, {
      props: { valasz: valasz({ sort: [{ property: 'Status', direction: 'ASC' }, { property: 'Rating', direction: 'DESC' }] }), irhato: true },
    });
    expect([...container.querySelectorAll('.irany sup')].map((e) => e.textContent)).toEqual(['1', '2']);
    expect(container.querySelector('[aria-sort=descending]')?.textContent).toContain('Értékelés');
  });

  it('az oszlop szélessége billentyűvel állítható (←→ 16 px, ⇧ 48 px), és a korlátok közt marad', async () => {
    const muvelet = vi.fn();
    const { container } = render(Tabla, { props: { valasz: valasz(), irhato: true, muvelet } });
    const sep = container.querySelectorAll<HTMLElement>('.atmeret')[2]; // Értékelés: 90 px
    expect(sep.getAttribute('aria-valuenow')).toBe('90');
    await fireEvent.keyDown(sep, { key: 'ArrowRight' });
    expect(muvelet).toHaveBeenLastCalledWith({ fajta: 'nezet_beallit', nezet: 0, kulcs: 'columnSize', alkulcs: 'Rating', ertek: 106 });
    await fireEvent.keyDown(sep, { key: 'ArrowLeft', shiftKey: true });
    expect(muvelet).toHaveBeenLastCalledWith(expect.objectContaining({ ertek: 60 })); // 90 - 48 = 42 → 60
  });

  it('húzással a szélesség élőben követi az egeret, elengedéskor ment', async () => {
    const muvelet = vi.fn();
    const { container } = render(Tabla, { props: { valasz: valasz(), irhato: true, muvelet } });
    const sep = container.querySelectorAll<HTMLElement>('.atmeret')[2];
    sep.setPointerCapture = () => {};
    await fireEvent.pointerDown(sep, { button: 0, clientX: 100, pointerId: 1 });
    await fireEvent.pointerMove(sep, { clientX: 150, pointerId: 1 });
    expect((container.querySelector('.fejlec') as HTMLElement).style.gridTemplateColumns).toContain('140px');
    expect(muvelet).not.toHaveBeenCalled();
    await fireEvent.pointerUp(sep, { clientX: 150, pointerId: 1 });
    expect(muvelet).toHaveBeenCalledWith({ fajta: 'nezet_beallit', nezet: 0, kulcs: 'columnSize', alkulcs: 'Rating', ertek: 140 });
  });

  it('a fejléc húzással átrendezhető: a Status az Kész mögé kerül', async () => {
    const muvelet = vi.fn();
    const { container } = render(Tabla, { props: { valasz: valasz(), irhato: true, muvelet } });
    const fejek = container.querySelectorAll<HTMLElement>('[role=columnheader]');
    await fireEvent.dragStart(fejek[1]);
    await fireEvent.dragOver(fejek[3]);
    await fireEvent.drop(fejek[3]);
    expect(muvelet).toHaveBeenCalledWith({ fajta: 'nezet_beallit', nezet: 0, kulcs: 'order', ertek: ['file.name', 'Rating', 'Done', 'Status'] });
  });

  it('a fejléc-menü: rendezés irányra, csoportosítás, összesítő almenüből, elrejtés', async () => {
    const muvelet = vi.fn();
    const { container } = render(Tabla, { props: { valasz: valasz(), irhato: true, muvelet } });
    const menuGomb = () => container.querySelectorAll<HTMLElement>('.fejlec-menu')[2];
    await fireEvent.click(menuGomb());
    await fireEvent.click(menuElem('Rendezés csökkenő')!);
    expect(muvelet).toHaveBeenLastCalledWith({ fajta: 'nezet_beallit', nezet: 0, kulcs: 'sort', ertek: [{ property: 'Rating', direction: 'DESC' }] });
    await fireEvent.click(menuGomb());
    await fireEvent.click(menuElem('Csoportosítás ezzel')!);
    expect(muvelet).toHaveBeenLastCalledWith(expect.objectContaining({ kulcs: 'groupBy', ertek: { property: 'Rating', direction: 'ASC' } }));
    await fireEvent.click(menuGomb());
    await fireEvent.click(menuElem('Összesítő')!);
    await fireEvent.click(menuElem('Átlag')!);
    expect(muvelet).toHaveBeenLastCalledWith({ fajta: 'nezet_beallit', nezet: 0, kulcs: 'summaries', alkulcs: 'Rating', ertek: 'Average' });
    await fireEvent.click(menuGomb());
    await fireEvent.click(menuElem('Oszlop elrejtése')!);
    expect(muvelet).toHaveBeenLastCalledWith({ fajta: 'nezet_beallit', nezet: 0, kulcs: 'order', ertek: ['file.name', 'Status', 'Done'] });
  });

  it('az egyedi összesítők is az almenüben állnak', async () => {
    const { container } = render(Tabla, { props: { valasz: valasz(), irhato: true, muvelet: vi.fn() } });
    await fireEvent.click(container.querySelectorAll<HTMLElement>('.fejlec-menu')[2]);
    await fireEvent.click(menuElem('Összesítő')!);
    expect(menuElem('Sajat')).toBeDefined();
    expect(menuElem('Nincs')).toBeDefined();
  });

  it('az oszlop átnevezése: a megjelenített nevet írja (üres: törli)', async () => {
    const atnevez = vi.fn();
    const { container } = render(Tabla, { props: { valasz: valasz(), irhato: true, muvelet: vi.fn(), atnevez } });
    await fireEvent.click(container.querySelectorAll<HTMLElement>('.fejlec-menu')[2]);
    await fireEvent.click(menuElem('Átnevezés…')!);
    const mezo = container.querySelector<HTMLInputElement>('input.atnevezo')!;
    await fireEvent.input(mezo, { target: { value: 'Pont' } });
    await fireEvent.keyDown(mezo, { key: 'Enter' });
    expect(atnevez).toHaveBeenCalledWith('Rating', 'Pont');
  });
});

// ---------------------------------------------------------------------- BazisNezet: eszköztár, panelek

interface Hivas {
  muvelet: Muvelet;
}

function keret(o: { valaszok?: (m: number) => Valasz; modosit?: (szoveg: string, m: Muvelet) => { ok: boolean; hibak?: { hely: string; uzenet: string }[] } } = {}) {
  const modositasok: Hivas[] = [];
  const api: BazisApi = {
    lekerdez: async () => (o.valaszok ? o.valaszok(0) : valasz()),
    modosit: async (szoveg, muvelet) => {
      modositasok.push({ muvelet });
      const r = o.modosit?.(szoveg, muvelet) ?? { ok: true };
      return { ok: r.ok, szoveg_uj: r.ok ? `UJ(${muvelet.fajta})` : szoveg, valtozas: muvelet.fajta, hibak: r.hibak ?? [] };
    },
  };
  const forras = rogzitettForras('views:\n  - type: table\n', 'X.base');
  return { api, forras, modositasok };
}

const gomb = (c: HTMLElement, nev: string) => [...c.querySelectorAll<HTMLButtonElement>('button')].find((b) => b.textContent?.trim().startsWith(nev))!;

describe('BazisNezet: eszköztár és panelek', () => {
  it('a nézetek fülek; az új nézet menüje nezet_uj műveletet küld, és az új nézetre vált', async () => {
    const { api, forras, modositasok } = keret();
    const valtott: number[] = [];
    const { container } = render(BazisNezet, { props: { forras, api, nezetValtott: (i: number) => valtott.push(i) } });
    await waitFor(() => expect(container.querySelectorAll('[role=tab]')).toHaveLength(2));
    await fireEvent.click(container.querySelector('[aria-label="Új nézet"]')!);
    await fireEvent.click(menuElem('Új nézet: Kanban')!);
    await waitFor(() => expect(modositasok.at(-1)!.muvelet).toEqual({ fajta: 'nezet_uj', tipus: 'kanban' }));
    await waitFor(() => expect(valtott).toEqual([2]));
    expect(forras.szoveg()).toBe('UJ(nezet_uj)');
  });

  it('a fül menüje: átnevezés, mozgatás, törlés (a törlés után a szomszéd nézet az aktív)', async () => {
    const { api, forras, modositasok } = keret();
    const valtott: number[] = [];
    const { container } = render(BazisNezet, { props: { forras, api, nezetValtott: (i: number) => valtott.push(i) } });
    await waitFor(() => expect(container.querySelectorAll('[role=tab]')).toHaveLength(2));
    await fireEvent.contextMenu(container.querySelectorAll('[role=tab]')[0]);
    expect(menuElem('Mozgatás balra')).toBeUndefined();
    await fireEvent.click(menuElem('Mozgatás jobbra')!);
    await waitFor(() => expect(modositasok.at(-1)!.muvelet).toEqual({ fajta: 'nezet_mozgat', nezet: 0, ujindex: 1 }));
    await waitFor(() => expect(valtott).toEqual([1]));
    await fireEvent.contextMenu(container.querySelectorAll('[role=tab]')[0]);
    await fireEvent.click(menuElem('Nézet törlése')!);
    await waitFor(() => expect(modositasok.at(-1)!.muvelet).toEqual({ fajta: 'nezet_torol', nezet: 0 }));
  });

  it('a fül dupla kattintásra átnevezhető', async () => {
    const { api, forras, modositasok } = keret();
    const { container } = render(BazisNezet, { props: { forras, api } });
    await waitFor(() => expect(container.querySelectorAll('[role=tab]')).toHaveLength(2));
    await fireEvent.dblClick(container.querySelectorAll('[role=tab]')[1]);
    const mezo = container.querySelector<HTMLInputElement>('input.fulatnevezo')!;
    await fireEvent.input(mezo, { target: { value: 'Galéria' } });
    await fireEvent.keyDown(mezo, { key: 'Enter' });
    await waitFor(() => expect(modositasok.at(-1)!.muvelet).toEqual({ fajta: 'nezet_beallit', nezet: 1, kulcs: 'name', ertek: 'Galéria' }));
  });

  it('a szűrőmező élő ellenőrzéssel: a hiba a mező alatt áll, az Alkalmaz addig tiltott', async () => {
    const { api, forras, modositasok } = keret({
      modosit: (_, m) => (m.fajta === 'szuro_beallit' && m.yaml.includes('???') ? { ok: false, hibak: [{ hely: 'filters', uzenet: 'váratlan jel: ?' }] } : { ok: true }),
    });
    const { container } = render(BazisNezet, { props: { forras, api } });
    await waitFor(() => expect(gomb(container, 'Szűrők')).toBeDefined());
    await fireEvent.click(gomb(container, 'Szűrők'));
    const mezo = container.querySelector<HTMLTextAreaElement>('textarea[aria-label="Szűrő minden nézetre"]')!;
    await fireEvent.input(mezo, { target: { value: 'a ??? b' } });
    await waitFor(() => expect(container.querySelector('[role=alert]')?.textContent).toContain('váratlan jel'));
    expect(modositasok.at(-1)!.muvelet).toEqual({ fajta: 'szuro_beallit', hol: 'globalis', yaml: 'a ??? b' });
    expect(gomb(container, 'Alkalmaz').disabled).toBe(true);
    await fireEvent.input(mezo, { target: { value: 'Rating > 3' } });
    await waitFor(() => expect(gomb(container, 'Alkalmaz').disabled).toBe(false));
    await fireEvent.click(gomb(container, 'Alkalmaz'));
    await waitFor(() => expect(forras.szoveg()).toBe('UJ(szuro_beallit)'));
  });

  it('a nézet szűrője a nézet sorszámát kapja; a meglévő szűrő szövege előtöltődik', async () => {
    const { api, forras, modositasok } = keret();
    const { container } = render(BazisNezet, { props: { forras, api } });
    await waitFor(() => expect(gomb(container, 'Szűrők')).toBeDefined());
    await fireEvent.click(gomb(container, 'Szűrők'));
    const mezo = container.querySelector<HTMLTextAreaElement>('textarea[aria-label="Szűrő erre a nézetre"]')!;
    expect(mezo.value).toBe('Status != "x"');
    await fireEvent.input(mezo, { target: { value: '' } });
    await waitFor(() => expect(modositasok.at(-1)!.muvelet).toEqual({ fajta: 'szuro_beallit', hol: 0, yaml: '' }));
  });

  it('a képlet törölhető; az új képletnek neve és kifejezése kell', async () => {
    const { api, forras, modositasok } = keret();
    const { container } = render(BazisNezet, { props: { forras, api } });
    await waitFor(() => expect(gomb(container, 'Szűrők')).toBeDefined());
    await fireEvent.click(gomb(container, 'Szűrők'));
    expect(container.querySelector('.keplet-fej code')?.textContent).toBe('formula.dupla');
    await fireEvent.click(gomb(container, 'Törlés'));
    await waitFor(() => expect(modositasok.at(-1)!.muvelet).toEqual({ fajta: 'keplet_beallit', nev: 'dupla', kifejezes: null }));
    await fireEvent.input(container.querySelector('input[aria-label="Új képlet neve"]')!, { target: { value: 'ossz' } });
    const mezo = await waitFor(() => container.querySelector<HTMLTextAreaElement>('textarea[aria-label="ossz képlet"]')!);
    expect(mezo).not.toBeNull();
    await fireEvent.input(mezo, { target: { value: 'Rating + 1' } });
    await waitFor(() => expect(gomb(container, 'Létrehoz').disabled).toBe(false));
    await fireEvent.click(gomb(container, 'Létrehoz'));
    await waitFor(() => expect(modositasok.at(-1)!.muvelet).toEqual({ fajta: 'keplet_beallit', nev: 'ossz', kifejezes: 'Rating + 1' }));
  });

  it('az oszlopválasztó a `order`-t írja: kijelölés, elrejtés, sorrend', async () => {
    const { api, forras, modositasok } = keret();
    const { container } = render(BazisNezet, { props: { forras, api } });
    await waitFor(() => expect(gomb(container, 'Oszlopok')).toBeDefined());
    await fireEvent.click(gomb(container, 'Oszlopok'));
    const dobozok = [...container.querySelectorAll<HTMLInputElement>('.oszlopok input[type=checkbox]')];
    expect(dobozok.filter((d) => d.checked)).toHaveLength(4);
    const modositva = container.querySelector<HTMLInputElement>('.oszlopok li:not(:has(input:checked)) input')!;
    await fireEvent.click(modositva); // a file.mtime kijelölése
    await waitFor(() => expect(modositasok.at(-1)!.muvelet).toEqual({ fajta: 'nezet_beallit', nezet: 0, kulcs: 'order', ertek: ['file.name', 'Status', 'Rating', 'Done', 'file.mtime'] }));
    await fireEvent.click(container.querySelector('[aria-label="Status feljebb"]')!);
    await waitFor(() => expect(modositasok.at(-1)!.muvelet).toEqual({ fajta: 'nezet_beallit', nezet: 0, kulcs: 'order', ertek: ['Status', 'file.name', 'Rating', 'Done'] }));
  });

  it('a nézet-beállítások: típus, csoportosítás, limit, sormagasság; hibás szám nem megy el', async () => {
    const { api, forras, modositasok } = keret();
    const { container } = render(BazisNezet, { props: { forras, api } });
    await waitFor(() => expect(gomb(container, 'Nézet')).toBeDefined());
    await fireEvent.click(gomb(container, 'Nézet'));
    await fireEvent.click(gomb(container, 'Kanban'));
    await waitFor(() => expect(modositasok.at(-1)!.muvelet).toEqual({ fajta: 'nezet_beallit', nezet: 0, kulcs: 'type', ertek: 'kanban' }));
    const limit = container.querySelector<HTMLInputElement>('input[placeholder="korlát nélkül"]')!;
    await fireEvent.change(limit, { target: { value: 'sok' } });
    expect(container.querySelector('.beallitas [role=alert]')?.textContent).toContain('pozitív egész');
    const n = modositasok.length;
    await fireEvent.change(limit, { target: { value: '25' } });
    await waitFor(() => expect(modositasok.at(-1)!.muvelet).toEqual({ fajta: 'nezet_beallit', nezet: 0, kulcs: 'limit', ertek: 25 }));
    expect(modositasok.length).toBe(n + 1);
    const csoportValaszto = container.querySelector<HTMLSelectElement>('select[aria-labelledby="csoport-cim"]')!;
    await fireEvent.change(csoportValaszto, { target: { value: 'Status' } });
    await waitFor(() => expect(modositasok.at(-1)!.muvelet).toEqual({ fajta: 'nezet_beallit', nezet: 0, kulcs: 'groupBy', ertek: { property: 'Status', direction: 'ASC' } }));
    await fireEvent.change(container.querySelector<HTMLSelectElement>('select option[value="tall"]')!.parentElement!, { target: { value: 'tall' } });
    await waitFor(() => expect(modositasok.at(-1)!.muvelet).toEqual({ fajta: 'nezet_beallit', nezet: 0, kulcs: 'rowHeight', ertek: 'tall' }));
  });

  it('YAML-forrás: a teljes szöveg szerkeszthető; a `forras_csere` ellenőrzi és beírja', async () => {
    const { api, forras, modositasok } = keret();
    const { container } = render(BazisNezet, { props: { forras, api } });
    await waitFor(() => expect(gomb(container, 'YAML')).toBeDefined());
    await fireEvent.click(gomb(container, 'YAML'));
    const mezo = container.querySelector<HTMLTextAreaElement>('textarea[aria-label="A .base fájl teljes YAML-forrása"]')!;
    expect(mezo.value).toBe('views:\n  - type: table\n');
    expect(container.querySelector('[role=table]')).toBeNull();
    await fireEvent.input(mezo, { target: { value: '# megjegyzés\nviews: []\n' } });
    await waitFor(() => expect(modositasok.at(-1)!.muvelet).toEqual({ fajta: 'forras_csere', szoveg: '# megjegyzés\nviews: []\n' }));
    await waitFor(() => expect(gomb(container, 'Alkalmaz').disabled).toBe(false));
    await fireEvent.click(gomb(container, 'Alkalmaz'));
    await waitFor(() => expect(forras.szoveg()).toBe('UJ(forras_csere)'));
  });

  it('a YAML-hiba ellenére a forrásnézet elérhető (nem értelmezhető fájl)', async () => {
    const { api, forras } = keret({
      valaszok: () => valasz({}, { ok: false, nezetek: [], nezet: null, oszlopok: [], sorok: [], fajl: undefined, hibak: [{ hely: 'yaml', uzenet: 'rossz behúzás' }] }),
    });
    const { container } = render(BazisNezet, { props: { forras, api } });
    await waitFor(() => expect(container.textContent).toContain('rossz behúzás'));
    expect(gomb(container, 'YAML')).toBeDefined();
    expect(container.querySelector('[role=tab]')).toBeNull();
  });

  it('csak olvasható forrásnál nincs szerkesztő elem, és az írási hiba látszik', async () => {
    const { api } = keret();
    const forras: BazisForras = { ...rogzitettForras('x', 'X.base'), csakOlvashato: () => 'A fájl csak olvasható.' };
    const { container } = render(BazisNezet, { props: { forras, api } });
    await waitFor(() => expect(container.querySelectorAll('[role=tab]')).toHaveLength(2));
    expect(container.querySelector('[aria-label="Új nézet"]')).toBeNull();
    expect([...container.querySelectorAll('button')].some((b) => b.textContent?.includes('Szűrők'))).toBe(false);
    expect([...container.querySelectorAll('button')].some((b) => b.textContent?.includes('YAML'))).toBe(false);
  });
});
