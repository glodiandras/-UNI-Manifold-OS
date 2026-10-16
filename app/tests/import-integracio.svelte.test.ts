// F8: az import elérhetősége — Setup (Workspace lépés) és Settings (Files & links), a v2-import kapuja (csak Developer mód).
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/svelte';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import BeallitasokAblak from '../src/beallitasok/Beallitasok.svelte';
import { beallitasAblak, SZAKASZOK, szakaszLathato } from '../src/beallitasok/allapot.svelte';
import { beallitasokTelepit } from '../src/beallitasok';
import Setup from '../src/setup/Setup.svelte';
import { BeallitasokTar, beallitasok } from '../src/lib/beallitasok/allapot.svelte';
import { alapBeallitasok, type BeallitasokValasz } from '../src/lib/beallitasok/tipusok';
import { importApi } from '../src/lib/import/api';
import { nyelv } from '../src/lib/i18n';
import { ModellTar } from '../src/lib/modellek/allapot.svelte';
import { Regiszter } from '../src/lib/parancsok/regiszter';
import { Feladatsor } from '../src/lib/vezerlo/feladatsor.svelte';
import { FORRAS, allapot, elonezet, v2Elonezet } from './import-fixture';

const valasz = (fejleszto = false): BeallitasokValasz => {
  const ertek = alapBeallitasok();
  ertek.fejleszto.mod = fejleszto;
  return { verzio: 1, rev: 'r1', ertek, munkater: { id: 'synthetic', nev: 'Synthetic workspace', vault: '/synthetic/vault' }, setup_szukseges: true, ujrainditas: [] };
};

beforeEach(() => {
  nyelv.beallit('en');
  beallitasAblak.szakasz = 'altalanos';
  vi.spyOn(importApi, 'lista').mockResolvedValue({ importok: [allapot()] });
});
afterEach(() => { cleanup(); beallitasok.adat = null; vi.restoreAllMocks(); nyelv.beallit('hu'); });

describe('Setup › Your workspace', () => {
  async function workspaceLepes() {
    const tar = new BeallitasokTar();
    tar.fogad(valasz());
    const onbezar = vi.fn();
    render(Setup, { props: { tar, modelltar: new ModellTar(new Feladatsor()), onbezar } });
    await waitFor(() => expect(screen.getByRole('heading', { name: 'Welcome to Manifold' })).toBeTruthy());
    await fireEvent.click(screen.getByRole('button', { name: 'Continue' }));
    await waitFor(() => expect(screen.getByRole('heading', { name: 'Your workspace' })).toBeTruthy());
    return { onbezar };
  }

  it('a Workspace lépésen elérhető az „Import an Obsidian vault”; megnyitja a folyamatot, és vissza lehet lépni', async () => {
    const elo = vi.spyOn(importApi, 'obsidianElonezet').mockResolvedValue(elonezet());
    await workspaceLepes();
    expect(screen.getByText('Coming from Obsidian?')).toBeTruthy();
    await fireEvent.click(screen.getByRole('button', { name: 'Import an Obsidian vault' }));
    expect(screen.getByRole('heading', { name: 'Import from Obsidian' })).toBeTruthy();
    expect(screen.getByText(/Your original vault is not modified/)).toBeTruthy();
    // a varázsló lépés-gombjai nem zavarnak a folyamat alatt
    expect(screen.queryByRole('button', { name: 'Continue' })).toBeNull();
    await fireEvent.input(screen.getByRole('textbox', { name: 'Obsidian vault folder' }), { target: { value: FORRAS } });
    await fireEvent.click(screen.getByRole('button', { name: 'Preview import' }));
    await waitFor(() => expect(elo).toHaveBeenCalled());
    await waitFor(() => expect(screen.getByRole('button', { name: 'Start import' })).toBeTruthy());
    await fireEvent.click(screen.getByRole('button', { name: 'Change folders' }));
    await fireEvent.click(screen.getByRole('button', { name: 'Close' }));
    expect(screen.getByRole('heading', { name: 'Your workspace' })).toBeTruthy();
    expect(screen.getByRole('button', { name: 'Continue' })).toBeTruthy();
  });

  it('a többi lépésen nincs import-kártya', async () => {
    await workspaceLepes();
    await fireEvent.click(screen.getByRole('button', { name: 'Continue' }));
    expect(screen.queryByText('Coming from Obsidian?')).toBeNull();
  });
});

describe('Settings › Files & links', () => {
  function nyit(fejleszto: boolean) {
    const tar = new BeallitasokTar();
    tar.fogad(valasz(fejleszto));
    beallitasok.fogad(valasz(fejleszto));
    render(BeallitasokAblak, { props: { tar, onbezar: vi.fn(), onsetup: vi.fn(), onrendszer: vi.fn() } });
  }

  it('az Obsidian-import itt is elérhető: leírás, indító és az előzmények (kérésre töltődnek)', async () => {
    nyit(false);
    await fireEvent.click(screen.getByRole('button', { name: 'Files & links' }));
    expect(screen.getByRole('heading', { name: 'Import from Obsidian' })).toBeTruthy();
    expect(screen.getAllByText(/Your original vault is not modified/).length).toBeGreaterThan(0);
    expect(importApi.lista).not.toHaveBeenCalled();
    await fireEvent.click(screen.getByRole('button', { name: 'Show import history' }));
    await waitFor(() => expect(screen.getByText('Completed')).toBeTruthy());
    expect(importApi.lista).toHaveBeenCalledTimes(1);
    await fireEvent.click(screen.getByRole('button', { name: 'Import an Obsidian vault' }));
    expect(screen.getByRole('textbox', { name: 'Obsidian vault folder' })).toBeTruthy();
    await fireEvent.click(within(document.querySelector('[data-import-folyamat]') as HTMLElement).getByRole('button', { name: 'Close' }));
    expect(screen.getByRole('button', { name: 'Import an Obsidian vault' })).toBeTruthy();
  });

  it('a megszakadt import a listából folytatható: az előnézet a naplózott mappákkal fut, a jóváhagyás külön lépés', async () => {
    const a = allapot({ allapot: 'fut', fut: false, eredmeny: null });
    vi.mocked(importApi.lista).mockResolvedValue({ importok: [a] });
    const elo = vi.spyOn(importApi, 'obsidianElonezet').mockResolvedValue(elonezet({ allapot: a }));
    const indit = vi.spyOn(importApi, 'obsidianIndit').mockResolvedValue({ id: a.id, allapot: 'fut' });
    nyit(false);
    await fireEvent.click(screen.getByRole('button', { name: 'Files & links' }));
    await fireEvent.click(screen.getByRole('button', { name: 'Show import history' }));
    await fireEvent.click(await screen.findByRole('button', { name: 'Review and resume' }));
    await waitFor(() => expect(elo).toHaveBeenCalledWith(a.forras, a.cel, { obsidian_mappa: true, kuka_mappa: false, nev: '' }));
    await waitFor(() => expect(screen.getByRole('button', { name: 'Resume import' })).toBeTruthy());
    expect(indit).not.toHaveBeenCalled();
  });

  it('normál módban nincs v2-import: sem a navigációban, sem a parancsok közt, sem a szakaszban', async () => {
    nyit(false);
    expect(screen.queryByRole('button', { name: 'Import from Manifold v2' })).toBeNull();
    expect(szakaszLathato('fejleszto_import', false)).toBe(false);
    expect(SZAKASZOK.some((s) => s.id === 'fejleszto_import')).toBe(true);
    beallitasAblak.szakasz = 'fejleszto_import';
    await waitFor(() => expect(screen.getByRole('heading', { level: 2 }).textContent).toBe('About Manifold'));   // a kapuzott szakasz nem nyitható
    expect(document.body.textContent).not.toContain('Manifold v2');
    const reg = new Regiszter();
    beallitasok.fogad(valasz(false));
    const le = beallitasokTelepit(reg);
    const parancs = reg.kap('beallitasok.fejleszto-import')!;
    expect(parancs).toBeTruthy();
    expect(reg.elerheto(parancs)).toBe(false);
    beallitasok.fogad(valasz(true));
    expect(reg.elerheto(parancs)).toBe(true);
    le();
  });

  it('Developer módban megjelenik az „Import from Manifold v2” szakasz a v2-előzményekkel, és működik a folyamat', async () => {
    vi.mocked(importApi.lista).mockResolvedValue({ importok: [allapot(), allapot({ id: 'v2-0123456789abcdef', fajta: 'v2', cel: undefined, eredmeny: { id: 'v2-0123456789abcdef', allapot: 'kesz', valtozas: 1 } })] });
    const elo = vi.spyOn(importApi, 'v2Elonezet').mockResolvedValue(v2Elonezet());
    nyit(true);
    await fireEvent.click(screen.getByRole('button', { name: 'Import from Manifold v2' }));
    await waitFor(() => expect(screen.getByRole('heading', { level: 2 }).textContent).toBe('Import from Manifold v2'));
    await waitFor(() => expect(document.querySelector('[data-import="v2-0123456789abcdef"]')).toBeTruthy());
    expect(document.querySelector('[data-import="obs-0123456789abcdef"]')).toBeNull();
    await fireEvent.click(screen.getByRole('button', { name: 'Import settings from a Manifold-OS folder' }));
    await fireEvent.input(screen.getByRole('textbox', { name: 'Manifold-OS folder' }), { target: { value: '/synthetic/old-os' } });
    await fireEvent.click(screen.getByRole('button', { name: 'Preview import' }));
    await waitFor(() => expect(elo).toHaveBeenCalledWith('/synthetic/old-os'));
    await waitFor(() => expect(screen.getByRole('button', { name: 'Apply import' })).toBeTruthy());
    expect(within(document.body).getByRole('table', { name: 'Settings to write' })).toBeTruthy();
  });
});
