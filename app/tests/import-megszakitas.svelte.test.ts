// F8: a natív mappaválasztó bekötése az import képernyőkbe, és a futó import megszakítása („Cancel import”, megerősítéssel).
// Mockolt API és mockolt héj-csatorna; nincs valódi útvonal.
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/svelte';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import ImportFolyamat from '../src/import/ImportFolyamat.svelte';
import ImportLista from '../src/import/ImportLista.svelte';
import ImportSzakasz from '../src/import/ImportSzakasz.svelte';
import { ApiHiba } from '../src/lib/core/api';
import { CoreKapcsolat } from '../src/lib/core/ws.svelte';
import { importApi } from '../src/lib/import/api';
import { ImportTar } from '../src/lib/import/allapot.svelte';
import { nyelv } from '../src/lib/i18n';
import { CEL, FORRAS, ID, allapot, elonezet } from './import-fixture';

let kapcsolat: CoreKapcsolat;
beforeEach(() => {
  nyelv.beallit('en');
  kapcsolat = new CoreKapcsolat('ws://127.0.0.1/ws');
});
afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
  delete (window as unknown as { manifold?: unknown }).manifold;
  nyelv.beallit('hu');
});

const mezo = (nev: string | RegExp) => screen.getByRole('textbox', { name: nev }) as HTMLInputElement;
const gomb = (nev: string | RegExp) => screen.getByRole('button', { name: nev }) as HTMLButtonElement;
const esemeny = (e: Record<string, unknown>) => kapcsolat.szetoszt({ tipus: 'import', fajta: 'obsidian', ...e });
const hejCsatorna = (postMessage: (u: unknown) => Promise<unknown>) => vi.stubGlobal('webkit', { messageHandlers: { mappaValaszto: { postMessage } } });

describe('natív mappaválasztó az import képernyőkben', () => {
  it('héj nélkül (böngésző, dev) nincs „Choose folder” gomb: a szövegmező marad', async () => {
    render(ImportFolyamat, { props: { tar: new ImportTar('obsidian'), kapcsolat } });
    expect(screen.queryByRole('button', { name: /Choose folder/ })).toBeNull();
    await fireEvent.input(mezo('Obsidian vault folder'), { target: { value: FORRAS } });
    expect(mezo('Obsidian vault folder').value).toBe(FORRAS);
  });

  it('a héj csatornájával a forrás és a cél választható; a kérés fix alakú, a cím angol; a forrásból cél-javaslat lesz', async () => {
    const kuld = vi.fn().mockResolvedValueOnce(FORRAS).mockResolvedValueOnce('/synthetic/Elsewhere');
    hejCsatorna(kuld);
    render(ImportFolyamat, { props: { tar: new ImportTar('obsidian'), kapcsolat } });
    const gombok = screen.getAllByRole('button', { name: /Choose folder/ });
    expect(gombok).toHaveLength(2);
    await fireEvent.click(gombok[0]);
    await waitFor(() => expect(mezo('Obsidian vault folder').value).toBe(FORRAS));
    expect(kuld).toHaveBeenCalledWith({ tipus: 'mappa-valaszto', cim: 'Choose the Obsidian vault folder' });
    expect(mezo('New workspace folder').value).toBe(CEL);
    await fireEvent.click(gombok[1]);
    await waitFor(() => expect(mezo('New workspace folder').value).toBe('/synthetic/Elsewhere'));
    expect(kuld).toHaveBeenLastCalledWith({ tipus: 'mappa-valaszto', cim: 'Choose the destination folder' });
  });

  it('megszakított választás (null) nem írja át a mezőt, és nem hiba; az útvonal csak a mezőbe kerül, az előnézet külön kattintás', async () => {
    hejCsatorna(vi.fn().mockResolvedValue(null));
    const elo = vi.spyOn(importApi, 'obsidianElonezet').mockResolvedValue(elonezet());
    render(ImportFolyamat, { props: { tar: new ImportTar('obsidian'), kapcsolat } });
    await fireEvent.input(mezo('Obsidian vault folder'), { target: { value: '/synthetic/Typed' } });
    await fireEvent.click(screen.getAllByRole('button', { name: /Choose folder/ })[0]);
    await waitFor(() => expect(screen.queryByRole('alert')).toBeNull());
    expect(mezo('Obsidian vault folder').value).toBe('/synthetic/Typed');
    expect(elo).not.toHaveBeenCalled();
  });

  it('a window.manifold.mappaValasztas hídon át megy, ha a híd telepítve van (a hid.ts szerződése)', async () => {
    hejCsatorna(vi.fn());            // a csatorna megléte kapcsolja be a gombot
    const hid = vi.fn().mockResolvedValue('/synthetic/ViaBridge');
    (window as unknown as { manifold: unknown }).manifold = { mappaValasztas: hid };
    render(ImportFolyamat, { props: { tar: new ImportTar('obsidian'), kapcsolat } });
    await fireEvent.click(screen.getAllByRole('button', { name: /Choose folder/ })[0]);
    await waitFor(() => expect(mezo('Obsidian vault folder').value).toBe('/synthetic/ViaBridge'));
    expect(hid).toHaveBeenCalledWith('Choose the Obsidian vault folder');
  });

  it('a hívó saját választója elsőbbséget élvez a natív csatornával szemben', async () => {
    const kuld = vi.fn();
    hejCsatorna(kuld);
    const sajat = vi.fn().mockResolvedValue('/synthetic/Own');
    render(ImportFolyamat, { props: { tar: new ImportTar('obsidian'), kapcsolat, valaszto: sajat } });
    await fireEvent.click(screen.getAllByRole('button', { name: /Choose folder/ })[0]);
    await waitFor(() => expect(mezo('Obsidian vault folder').value).toBe('/synthetic/Own'));
    expect(kuld).not.toHaveBeenCalled();
  });

  it('érvénytelen válasz (relatív út, nem szöveg) nem kerül a mezőbe', async () => {
    hejCsatorna(vi.fn().mockResolvedValueOnce('relative/dir').mockResolvedValueOnce({ ut: '/x' }));
    render(ImportFolyamat, { props: { tar: new ImportTar('obsidian'), kapcsolat } });
    const g = screen.getAllByRole('button', { name: /Choose folder/ })[0];
    await fireEvent.click(g);
    await fireEvent.click(g);
    await waitFor(() => expect(mezo('Obsidian vault folder').value).toBe(''));
  });

  it('a Settings-szakasz (ImportSzakasz) átadja: a folyamatban megjelenik a választó', async () => {
    hejCsatorna(vi.fn().mockResolvedValue(FORRAS));
    vi.spyOn(importApi, 'lista').mockResolvedValue({ importok: [] });
    render(ImportSzakasz, { props: { fajta: 'obsidian', kapcsolat } });
    await fireEvent.click(gomb('Import an Obsidian vault'));
    await fireEvent.click(screen.getAllByRole('button', { name: /Choose folder/ })[0]);
    await waitFor(() => expect(mezo('Obsidian vault folder').value).toBe(FORRAS));
  });
});

describe('„Cancel import”', () => {
  async function fut() {
    vi.spyOn(importApi, 'obsidianElonezet').mockResolvedValue(elonezet());
    vi.spyOn(importApi, 'obsidianIndit').mockResolvedValue({ id: ID, allapot: 'fut' });
    const onbezar = vi.fn();
    const tar = new ImportTar('obsidian');
    render(ImportFolyamat, { props: { tar, kapcsolat, onbezar } });
    await fireEvent.input(mezo('Obsidian vault folder'), { target: { value: FORRAS } });
    await fireEvent.click(gomb('Preview import'));
    await waitFor(() => gomb('Start import'));
    await fireEvent.click(gomb('Start import'));
    await waitFor(() => expect(screen.getByRole('heading', { name: 'Importing' })).toBeTruthy());
    esemeny({ id: ID, lepes: 'masolas', kesz_db: 5, osszes_db: 12, bajt: 2000 });
    await waitFor(() => expect(document.querySelector('[data-haladas]')!.textContent).toContain('5 of 12'));
    return { tar, onbezar };
  }

  it('a futó nézeten a „Hide” megmarad, mellette ott a „Cancel import”; a Hide nem szakít meg', async () => {
    const megszakit = vi.spyOn(importApi, 'megszakit');
    const { onbezar } = await fut();
    expect(gomb('Hide')).toBeTruthy();
    expect(gomb('Cancel import')).toBeTruthy();
    await fireEvent.click(gomb('Hide'));
    expect(onbezar).toHaveBeenCalledTimes(1);
    expect(megszakit).not.toHaveBeenCalled();
  });

  it('megerősítés nélkül nem megy a kérés; „Keep importing” visszavon, a fókusz a biztonságos válaszon van', async () => {
    const megszakit = vi.spyOn(importApi, 'megszakit');
    await fut();
    await fireEvent.click(gomb('Cancel import'));
    expect(screen.getByRole('heading', { name: 'Cancel this import?' })).toBeTruthy();
    expect(screen.getByText(/Copying stops after the file that is being copied/)).toBeTruthy();
    expect(screen.getAllByText(/Your original vault is not modified/).length).toBeGreaterThan(0);
    await waitFor(() => expect(document.activeElement).toBe(gomb('Keep importing')));
    expect(megszakit).not.toHaveBeenCalled();
    await fireEvent.click(gomb('Keep importing'));
    expect(screen.queryByRole('heading', { name: 'Cancel this import?' })).toBeNull();
    expect(megszakit).not.toHaveBeenCalled();
    expect(screen.getByRole('heading', { name: 'Importing' })).toBeTruthy();
  });

  it('megerősítés után a core megszakít: „Import cancelled”, a másolt darabszám, folytatás / visszafordítás / mappák váltása', async () => {
    const megszakit = vi.spyOn(importApi, 'megszakit').mockResolvedValue({ id: ID, allapot: 'megszakitva', megszakitva: true });
    vi.spyOn(importApi, 'allapot').mockResolvedValue(allapot({ allapot: 'megszakitva', eredmeny: null }));
    await fut();
    await fireEvent.click(gomb('Cancel import'));
    await fireEvent.click(screen.getAllByRole('button', { name: 'Cancel import' })[0]);
    await waitFor(() => expect(megszakit).toHaveBeenCalledWith(ID));
    await waitFor(() => expect(screen.getByRole('heading', { name: /Import cancelled/ })).toBeTruthy());
    expect(document.querySelector('[data-megszakitva-darab]')!.textContent).toBe('5 of 12 files were copied before the import stopped.');
    expect(screen.getByText(/The files copied so far are kept/)).toBeTruthy();
    expect(screen.getAllByText(/Your original vault is not modified/).length).toBeGreaterThan(0);
    expect(gomb('Review and resume')).toBeTruthy();
    expect(gomb('Undo import')).toBeTruthy();
    expect(gomb('Change folders')).toBeTruthy();
    expect(screen.queryByRole('button', { name: 'Hide' })).toBeNull();
  });

  it('a megszakított import folytatható: az előnézet „Resume import”-ot és magyarázatot mutat', async () => {
    vi.spyOn(importApi, 'megszakit').mockResolvedValue({ id: ID, allapot: 'megszakitva', megszakitva: true });
    vi.spyOn(importApi, 'allapot').mockResolvedValue(allapot({ allapot: 'megszakitva', eredmeny: null }));
    const { tar } = await fut();
    await fireEvent.click(gomb('Cancel import'));
    await fireEvent.click(screen.getAllByRole('button', { name: 'Cancel import' })[0]);
    await waitFor(() => expect(screen.getByRole('heading', { name: /Import cancelled/ })).toBeTruthy());
    vi.mocked(importApi.obsidianElonezet).mockResolvedValue(elonezet({ allapot: allapot({ allapot: 'megszakitva', eredmeny: null }), osszesites: { ...elonezet().osszesites, megvan_db: 5, masolando_db: 7 } }));
    await fireEvent.click(gomb('Review and resume'));
    await waitFor(() => expect(gomb('Resume import')).toBeTruthy());
    expect(screen.getByText(/stopped before it finished/)).toBeTruthy();
    expect(tar.folytatas).toBe(true);
    await fireEvent.click(gomb('Resume import'));
    await waitFor(() => expect(importApi.obsidianIndit).toHaveBeenCalledTimes(2));
    await waitFor(() => expect(screen.getByRole('heading', { name: 'Importing' })).toBeTruthy());
  });

  it('a megszakított import visszafordítható (megerősítéssel), a hívás a core visszafordítója', async () => {
    vi.spyOn(importApi, 'megszakit').mockResolvedValue({ id: ID, allapot: 'megszakitva', megszakitva: true });
    vi.spyOn(importApi, 'allapot').mockResolvedValue(allapot({ allapot: 'megszakitva', eredmeny: null }));
    const vissza = vi.spyOn(importApi, 'visszafordit').mockResolvedValue({ id: ID, allapot: 'visszaforditva', kukaba: [CEL] });
    await fut();
    await fireEvent.click(gomb('Cancel import'));
    await fireEvent.click(screen.getAllByRole('button', { name: 'Cancel import' })[0]);
    await waitFor(() => expect(screen.getByRole('heading', { name: /Import cancelled/ })).toBeTruthy());
    await fireEvent.click(gomb('Undo import'));
    expect(vissza).not.toHaveBeenCalled();
    await fireEvent.click(screen.getAllByRole('button', { name: 'Undo import' })[0]);
    await waitFor(() => expect(vissza).toHaveBeenCalledWith(ID));
  });

  it('202 (még az aktuális fájlt másolja): „Stopping…” jelzés, a gomb tiltott; a WS esemény zárja', async () => {
    vi.spyOn(importApi, 'megszakit').mockResolvedValue({ id: ID, allapot: 'megszakitas' });
    vi.spyOn(importApi, 'allapot').mockResolvedValue(allapot({ allapot: 'megszakitva', eredmeny: null }));
    await fut();
    await fireEvent.click(gomb('Cancel import'));
    await fireEvent.click(screen.getAllByRole('button', { name: 'Cancel import' })[0]);
    await waitFor(() => expect(document.querySelector('[data-megszakit-folyik]')!.textContent).toContain('Stopping after the current file'));
    expect(gomb('Cancel import').disabled).toBe(true);
    expect(screen.getByRole('heading', { name: 'Importing' })).toBeTruthy();
    esemeny({ id: ID, allapot: 'megszakitva', kesz_db: 7, osszes_db: 12 });
    await waitFor(() => expect(screen.getByRole('heading', { name: /Import cancelled/ })).toBeTruthy());
    expect(document.querySelector('[data-megszakitva-darab]')!.textContent).toContain('7 of 12 files');
  });

  it('más import megszakítás-eseménye nem állítja meg ezt', async () => {
    await fut();
    esemeny({ id: 'obs-ffffffffffffffff', allapot: 'megszakitva' });
    expect(screen.getByRole('heading', { name: 'Importing' })).toBeTruthy();
  });

  it('közben kész lett: a válasz „kesz”, az összegzés jön, nem a megszakítás képernyője', async () => {
    vi.spyOn(importApi, 'megszakit').mockResolvedValue({ id: ID, allapot: 'kesz', megszakitva: false });
    vi.spyOn(importApi, 'allapot').mockResolvedValue(allapot());
    await fut();
    await fireEvent.click(gomb('Cancel import'));
    await fireEvent.click(screen.getAllByRole('button', { name: 'Cancel import' })[0]);
    await waitFor(() => expect(screen.getByRole('heading', { name: /Import complete/ })).toBeTruthy());
    expect(screen.queryByRole('heading', { name: /Import cancelled/ })).toBeNull();
  });

  it('a „nem fut” hiba (409): ikonos hibapanel teendővel, a valós állapot a naplóból; a gomb újra használható, ha még fut', async () => {
    vi.spyOn(importApi, 'megszakit').mockRejectedValue(new ApiHiba(409, 'This import is not running.', { kod: 'import.nem_fut' }));
    vi.spyOn(importApi, 'allapot').mockResolvedValue(allapot({ allapot: 'fut', fut: true, eredmeny: null }));
    const { tar } = await fut();
    await fireEvent.click(gomb('Cancel import'));
    await fireEvent.click(screen.getAllByRole('button', { name: 'Cancel import' })[0]);
    await waitFor(() => expect(screen.getByRole('alert').textContent).toContain('This import is not running'));
    expect(screen.getByText(/Refresh the import history/)).toBeTruthy();
    expect(tar.fazis).toBe('fut');
    expect(tar.megszakitasFolyik).toBe(false);
    expect(gomb('Cancel import').disabled).toBe(false);
  });

  it('a megszakított állapot a tárban: nincs futó kérdezés, a folytatás jelzője igaz', async () => {
    const tar = new ImportTar('obsidian');
    tar.id = ID;
    tar.fazis = 'fut';
    tar.esemeny({ tipus: 'import', id: ID, allapot: 'megszakitva', kesz_db: 3, osszes_db: 9 } as never);
    expect(tar.fazis).toBe('megszakitva');
    expect(tar.halad).toMatchObject({ kesz_db: 3, osszes_db: 9 });
    tar.elonezet = elonezet({ allapot: allapot({ allapot: 'megszakitva' }) });
    expect(tar.folytatas).toBe(true);
    tar.lezar();
  });
});

describe('Import history: megszakított import', () => {
  it('„Cancelled” ikonnal és szóval, folytatható és visszafordítható; a futó import még nem', async () => {
    const ID2 = 'obs-aaaaaaaaaaaaaaaa';
    vi.spyOn(importApi, 'lista').mockResolvedValue({ importok: [
      allapot({ allapot: 'megszakitva', eredmeny: null }),
      allapot({ id: ID2, allapot: 'fut', fut: true, eredmeny: null }),
    ] });
    const onfolytat = vi.fn();
    render(ImportLista, { props: { kapcsolat, onfolytat } });
    const sor = (id: string) => document.querySelector<HTMLElement>(`[data-import="${id}"]`)!;
    await waitFor(() => expect(sor(ID)).toBeTruthy());
    expect(sor(ID).textContent).toContain('Cancelled');
    expect(sor(ID).getAttribute('data-allapot')).toBe('megszakitva');
    expect(sor(ID).querySelector('svg')).toBeTruthy();
    const folytat = sor(ID).querySelector<HTMLButtonElement>('button.m-gomb')!;
    expect(sor(ID).textContent).toContain('Undo import');
    await fireEvent.click(Array.from(sor(ID).querySelectorAll('button')).find((b) => b.textContent === 'Review and resume')!);
    expect(onfolytat).toHaveBeenCalledTimes(1);
    expect(folytat).toBeTruthy();
    expect(sor(ID2).textContent).toContain('Running');
    expect(sor(ID2).textContent).not.toContain('Undo import');
  });
});
