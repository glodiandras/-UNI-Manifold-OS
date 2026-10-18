// S0: a közös keret valódi komponensei és menüi, szintetikus core-/forrás-határral. Nincs valódi vault vagy lemezírás.
import { cleanup, fireEvent, render, waitFor } from '@testing-library/svelte';
import { afterEach, describe, expect, it, vi } from 'vitest';
import BazisNezet from '../src/bazis/BazisNezet.svelte';
import type { BazisApi } from '../src/bazis/api';
import { blokkForras, rogzitettForras, type BazisForras } from '../src/bazis/forras';
import { kimenetSzoveg } from '../src/bazis/csv';
import type { Muvelet, NezetTipus, Valasz } from '../src/bazis/tipusok';

interface Nezet { nev: string; tipus: NezetTipus; beallitas: Record<string, unknown> }

function valasz(nezetek: Nezet[], index = 0): Valasz {
  const n = nezetek[index];
  return {
    ok: true,
    nezetek: nezetek.map(({ nev, tipus }) => ({ nev, tipus, ismert: true })),
    nezet: { index, nev: n.nev, tipus: n.tipus, eredeti_tipus: n.tipus, beallitas: n.beallitas },
    oszlopok: [
      { id: 'file.name', nev: 'Name', ter: 'file', tipus: 'text', szerkesztheto: false, szelesseg: null },
      { id: 'Stage', nev: 'Stage', ter: 'note', tipus: 'text', szerkesztheto: true, szelesseg: null },
    ],
    sorok: [
      { ut: 'Notes/Alpha.md', nev: 'Alpha', md: true, cellak: [{ t: 'link', cel: 'Notes/Alpha.md', ut: 'Notes/Alpha.md', nev: 'Alpha' }, 'Ready'] },
      { ut: 'Notes/Beta.md', nev: 'Beta', md: true, cellak: [{ t: 'link', cel: 'Notes/Beta.md', ut: 'Notes/Beta.md', nev: 'Beta' }, '=formula'] },
    ],
    csoportok: n.beallitas.groupBy ? [{ kulcs: 'Ready', cimke: 'Ready', tol: 0, db: 2, osszesitok: {}, huzhato: true }] : null,
    osszesitok: {},
    fajl: { szuro: '', szuro_nezet: '', kepletek: {}, osszesitok: [], elerheto: [{ id: 'Stage', nev: 'Stage', ter: 'note', tipus: 'text' }] },
    osszes: 2, levagva: false, hibak: [], figyelmeztetesek: [], ido_ms: 1, generacio: 1,
  };
}

function keret(tipus: NezetTipus = 'list', beallitas: Record<string, unknown> = {}) {
  const kezdo: Nezet[] = [{ nev: 'Overview', tipus, beallitas }];
  const szoveg = JSON.stringify(kezdo);
  const modositasok: Muvelet[] = [];
  const api: BazisApi = {
    lekerdez: vi.fn(async (s, o) => valasz(JSON.parse(s) as Nezet[], typeof o?.nezet === 'number' ? o.nezet : 0)),
    modosit: vi.fn(async (s, m) => {
      modositasok.push(m);
      const nezetek = JSON.parse(s) as Nezet[];
      if (m.fajta === 'nezet_uj') nezetek.push({ nev: 'New view', tipus: m.tipus ?? 'table', beallitas: {} });
      if (m.fajta === 'nezet_beallit') {
        if (m.kulcs === 'type') nezetek[m.nezet].tipus = m.ertek as NezetTipus;
        else nezetek[m.nezet].beallitas[m.kulcs] = m.ertek;
      }
      return { ok: true, szoveg_uj: JSON.stringify(nezetek), valtozas: '', hibak: [] };
    }),
  };
  const memoria = rogzitettForras(szoveg, 'Views/Overview.base');
  const forras: BazisForras = { ...memoria, cellaIras: () => true, ir: vi.fn((s) => memoria.ir(s)) };
  return { api, forras, modositasok, szoveg };
}

const gomb = (c: HTMLElement, nev: string) => [...c.querySelectorAll<HTMLButtonElement>('button')].find((e) => e.textContent?.trim() === nev)!;
const menuElem = (nev: string) => [...document.querySelectorAll<HTMLElement>('.nt-lebego .nt-menu-elem')].find((e) => e.querySelector('.nt-menu-nev')?.textContent === nev)!;
const kesz = async (c: HTMLElement) => waitFor(() => expect(c.querySelector('[role=tab]')).not.toBeNull());

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  document.querySelectorAll('.nt-lebego').forEach((e) => e.remove());
});

describe('S0 Bases: közös nézetintegráció', () => {
  it.each([
    ['table', '[role=table]'], ['cards', '.racs'], ['list', '[role=group][aria-label="Lista"]'], ['kanban', '.kanban'],
  ] as const)('%s a saját komponensét rendereli', async (tipus, szelektor) => {
    const { forras, api } = keret(tipus, { groupBy: { property: 'Stage' } });
    const { container } = render(BazisNezet, { props: { forras, api } });
    await kesz(container);
    expect(container.querySelector(szelektor)).not.toBeNull();
    if (tipus !== 'table') expect(container.querySelector('[role=table]')).toBeNull();
    expect(container.textContent).toContain('Alpha');
  });

  it.each(['fajl', 'blokk', 'olvaso'] as const)('List %s-forrásból: számozás, tulajdonságok és csoportösszecsukás', async (hely) => {
    const k = keret('list', { markers: 'number', indentProperties: true, groupBy: { property: 'Stage' } });
    const csere = vi.fn(() => true);
    const forras = hely === 'blokk' ? blokkForras('Notes/Host.md', k.szoveg, { csakOlvashato: false, csere })
      : hely === 'olvaso' ? rogzitettForras(k.szoveg, 'Notes/Host.md') : k.forras;
    const { container } = render(BazisNezet, { props: { forras, api: k.api, kompakt: hely !== 'fajl' } });
    await kesz(container);
    expect(container.querySelector('ol.lista')).not.toBeNull();
    expect(container.querySelectorAll('.alpont')).toHaveLength(2);
    expect(container.querySelector('[role=table]')).toBeNull();
    await fireEvent.click(container.querySelector('h3 [aria-expanded=true]')!);
    expect(container.querySelectorAll('.elem[data-ut]')).toHaveLength(0);
    await fireEvent.click(container.querySelector('h3 [aria-expanded=false]')!);
    expect(container.querySelectorAll('.elem[data-ut]')).toHaveLength(2);
    expect(k.api.modosit).not.toHaveBeenCalled();
    expect(csere).not.toHaveBeenCalled();
    if (hely === 'olvaso') expect(gomb(container, 'Új')).toBeUndefined();
  });

  it('a List a létrehozási menüből valóban új nézetként megnyílik és a forráson át íródik', async () => {
    const k = keret('table');
    const valtott = vi.fn();
    const { container } = render(BazisNezet, { props: { ...k, nezetValtott: valtott } });
    await kesz(container);
    await fireEvent.click(container.querySelector('[aria-label="Új nézet"]')!);
    expect(menuElem('Új nézet: Lista')).toBeDefined();
    await fireEvent.click(menuElem('Új nézet: Lista'));
    await waitFor(() => expect(container.querySelector('[role=tab][aria-selected=true]')?.textContent).toBe('New view'));
    expect(k.modositasok).toEqual([{ fajta: 'nezet_uj', tipus: 'list' }]);
    expect(k.forras.ir).toHaveBeenCalledTimes(1);
    expect(container.querySelector('[aria-label="Lista"]')).not.toBeNull();
    expect(valtott).toHaveBeenCalledWith(1);
  });

  it('a fül Típus menüje Listre vált, és a Nézet panel mind a négy elrendezést eléri', async () => {
    const k = keret('table');
    const { container } = render(BazisNezet, { props: k });
    await kesz(container);
    await fireEvent.contextMenu(container.querySelector('[role=tab]')!);
    await fireEvent.click(menuElem('Típus'));
    await fireEvent.click(menuElem('Lista'));
    await waitFor(() => expect(container.querySelector('[aria-label="Lista"]')).not.toBeNull());
    expect(k.modositasok[0]).toEqual({ fajta: 'nezet_beallit', nezet: 0, kulcs: 'type', ertek: 'list' });
    await fireEvent.click(gomb(container, 'Nézet'));
    const panel = container.querySelector<HTMLElement>('[role=dialog]')!;
    expect([...panel.querySelectorAll('.szegmens button')].map((e) => e.textContent)).toEqual(['Táblázat', 'Kártyák', 'Lista', 'Kanban']);
    expect(gomb(panel, 'Lista').getAttribute('aria-pressed')).toBe('true');
    await fireEvent.click(gomb(panel, 'Kártyák'));
    await waitFor(() => expect(container.querySelector('.racs')).not.toBeNull());
  });

  it('sikertelen újnézet-mentésnél a meglévő nézet és a tartós nézetállapot marad aktív', async () => {
    const k = keret('table');
    const kulsoValtozas = k.forras.ir;
    k.forras.ir = vi.fn(async () => false);
    const valtott = vi.fn();
    const { container } = render(BazisNezet, { props: { ...k, nezetValtott: valtott } });
    await kesz(container);
    await fireEvent.click(container.querySelector('[aria-label="Új nézet"]')!);
    await fireEvent.click(menuElem('Új nézet: Lista'));
    await waitFor(() => expect(container.querySelector('[role=alert]')?.textContent).toBe('A módosítás nem íródott be.'));
    expect(valtott).not.toHaveBeenCalled();
    expect(k.forras.szoveg()).toBe(k.szoveg);
    // Egy későbbi forrásesemény is a létező nézetet kéri le, nem a létre nem jött új nézet indexét.
    await kulsoValtozas(k.szoveg);
    await waitFor(() => expect(k.api.lekerdez).toHaveBeenCalledTimes(2));
    expect(vi.mocked(k.api.lekerdez).mock.calls[1][1]?.nezet).toBeNull();
    expect(container.querySelector('[role=table]')).not.toBeNull();
    expect(container.querySelector('[role=tab][aria-selected=true]')?.textContent).toBe('Overview');
  });

  it('lassú mentés után is lekéri az új nézetet, ha a forrás a mentés befejezése előtt már jelzett', async () => {
    const k = keret('table');
    const ir = k.forras.ir;
    let befejez!: () => void;
    const kesleltetes = new Promise<void>((r) => { befejez = r; });
    k.forras.ir = vi.fn(async (s) => {
      await ir(s);
      await kesleltetes;
      return true;
    });
    const { container } = render(BazisNezet, { props: k });
    await kesz(container);
    await fireEvent.click(container.querySelector('[aria-label="Új nézet"]')!);
    await fireEvent.click(menuElem('Új nézet: Lista'));
    await waitFor(() => expect(k.api.lekerdez).toHaveBeenCalledTimes(2));
    expect(container.querySelector('[role=table]')).not.toBeNull();
    befejez();
    await waitFor(() => expect(container.querySelector('[aria-label="Lista"]')).not.toBeNull());
    expect(vi.mocked(k.api.lekerdez).mock.calls.at(-1)?.[1]?.nezet).toBe(1);
  });

  it('a rendezési és csoportpanel a meglévő közös írási úton működik Listben', async () => {
    const k = keret('list', { groupBy: { property: 'Stage' } });
    const { container } = render(BazisNezet, { props: k });
    await kesz(container);
    await fireEvent.click(gomb(container, 'Rendezés'));
    await fireEvent.change(container.querySelector('[aria-label="Rendezési kulcs hozzáadása"]')!, { target: { value: 'Stage' } });
    await waitFor(() => expect(k.modositasok.at(-1)).toEqual({ fajta: 'nezet_beallit', nezet: 0, kulcs: 'sort', ertek: [{ property: 'Stage', direction: 'ASC' }] }));
    await fireEvent.click(gomb(container, 'Rendezés'));
    await fireEvent.click(gomb(container, 'Csoportok'));
    const jelolo = container.querySelector<HTMLInputElement>('[role=dialog] input[type=checkbox]')!;
    expect(jelolo.checked).toBe(true);
    await fireEvent.click(jelolo);
    await waitFor(() => expect(k.modositasok.at(-1)).toEqual({ fajta: 'nezet_beallit', nezet: 0, kulcs: 'groupOrder', ertek: [] }));
    expect(k.forras.ir).toHaveBeenCalledTimes(2);
  });

  it('konfliktus/readonly alatt a menük és az új jegyzet nem érhetők el; egy már megnyitott művelet sem írhat', async () => {
    const k = keret('table');
    let tiltas: string | null = null;
    k.forras.csakOlvashato = () => tiltas;
    const { container } = render(BazisNezet, { props: k });
    await kesz(container);
    await fireEvent.contextMenu(container.querySelector('[role=tab]')!);
    await fireEvent.click(menuElem('Típus'));
    tiltas = 'Synthetic conflict';
    await fireEvent.click(menuElem('Lista'));
    await waitFor(() => expect(container.querySelector('[role=alert]')?.textContent).toBe('Synthetic conflict'));
    expect(k.api.modosit).not.toHaveBeenCalled();
    expect(k.forras.ir).not.toHaveBeenCalled();
    cleanup();
    const readonly = render(BazisNezet, { props: k });
    await kesz(readonly.container);
    expect(readonly.container.querySelector('[aria-label="Új nézet"]')).toBeNull();
    expect(gomb(readonly.container, 'Új')).toBeUndefined();
    expect(gomb(readonly.container, 'Rendezés')).toBeUndefined();
    expect(gomb(readonly.container, 'Másolás')).toBeDefined();
  });

  it('Új jegyzet: ütközésnél név és hiba marad, az újrapróba a meglévő létrehozási API-t hívja', async () => {
    const k = keret();
    let utkozes = true;
    const hiv = vi.fn(async (url: string, init?: RequestInit) => {
      expect(String(url)).toBe('/api/vault/uj');
      expect(init?.method).toBe('POST');
      const torzs = JSON.parse(String(init?.body));
      expect(torzs.nev).toBe('New note');
      return new Response(JSON.stringify(utkozes ? { hiba: 'Synthetic name conflict' } : { ut: 'New note.md' }), { status: utkozes ? 409 : 200, headers: { 'Content-Type': 'application/json' } });
    });
    vi.stubGlobal('fetch', hiv);
    const { container } = render(BazisNezet, { props: k });
    await kesz(container);
    await fireEvent.click(gomb(container, 'Új'));
    const mezo = container.querySelector<HTMLInputElement>('[aria-label="Az új jegyzet neve"]')!;
    await fireEvent.input(mezo, { target: { value: 'New note' } });
    await fireEvent.click(gomb(container, 'Létrehozás'));
    await waitFor(() => expect(container.querySelector('[role=alert]')?.textContent).toContain('Synthetic name conflict'));
    expect(mezo.value).toBe('New note');
    utkozes = false;
    await fireEvent.click(gomb(container, 'Létrehozás'));
    await waitFor(() => expect(container.querySelector('[aria-label="Az új jegyzet neve"]')).toBeNull());
    expect(hiv).toHaveBeenCalledTimes(2);
    expect(k.forras.ir).not.toHaveBeenCalled();
  });

  it('a már megnyitott Új űrlap az írás előtt újra ellenőrzi a readonly/ütközés kaput', async () => {
    const k = keret();
    let tiltas: string | null = null;
    k.forras.csakOlvashato = () => tiltas;
    const fetch = vi.fn();
    vi.stubGlobal('fetch', fetch);
    const { container } = render(BazisNezet, { props: k });
    await kesz(container);
    await fireEvent.click(gomb(container, 'Új'));
    const mezo = container.querySelector<HTMLInputElement>('[aria-label="Az új jegyzet neve"]')!;
    await fireEvent.input(mezo, { target: { value: 'New note' } });
    tiltas = 'Synthetic conflict';
    await fireEvent.click(gomb(container, 'Létrehozás'));
    expect(container.querySelector('[role=alert]')?.textContent).toBe('Synthetic conflict');
    expect(mezo.value).toBe('New note');
    expect(fetch).not.toHaveBeenCalled();
  });

  it.each(['csv', 'tsv', 'markdown'] as const)('%s másolása a tényleges lekérdezett, injekcióvédett adatot adja ki', async (fajta) => {
    const k = keret();
    const writeText = vi.fn<(s: string) => Promise<void>>().mockResolvedValue(undefined);
    vi.stubGlobal('navigator', { clipboard: { writeText } });
    const { container } = render(BazisNezet, { props: k });
    await kesz(container);
    await fireEvent.click(gomb(container, 'Másolás'));
    await fireEvent.click(menuElem(fajta === 'csv' ? 'CSV másolása' : fajta === 'tsv' ? 'Másolás táblázatként' : 'Másolás Markdown-táblázatként'));
    await waitFor(() => expect(writeText).toHaveBeenCalledWith(kimenetSzoveg(valasz(JSON.parse(k.szoveg)), fajta)));
    expect(container.querySelector('[role=status]')?.textContent).toBe('Másolva');
    if (fajta !== 'markdown') expect(writeText.mock.calls[0][0]).toContain("'=formula");
    expect(k.forras.ir).not.toHaveBeenCalled();
  });

  it('másolási hibát visszajelez, újrapróbával helyreáll', async () => {
    const k = keret();
    const writeText = vi.fn<(s: string) => Promise<void>>().mockRejectedValueOnce(new Error('Denied')).mockResolvedValueOnce(undefined);
    vi.stubGlobal('navigator', { clipboard: { writeText } });
    const { container } = render(BazisNezet, { props: k });
    await kesz(container);
    await fireEvent.click(gomb(container, 'Másolás'));
    await fireEvent.click(menuElem('CSV másolása'));
    await waitFor(() => expect(container.querySelector('[role=alert]')?.textContent).toContain('A vágólapra másolás nem sikerült'));
    await fireEvent.click(gomb(container, 'Másolás'));
    await fireEvent.click(menuElem('CSV másolása'));
    await waitFor(() => expect(container.querySelector('[role=status]')?.textContent).toBe('Másolva'));
    expect(container.querySelector('[role=alert]')).toBeNull();
  });
});
