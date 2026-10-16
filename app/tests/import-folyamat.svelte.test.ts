// F8 „Import from Obsidian”: mappák → előnézet → explicit jóváhagyás → haladás (WS) → összegzés / hiba → visszavonás. Mockolt API.
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/svelte';
import { afterEach, beforeEach, describe, expect, it, vi, type Mock } from 'vitest';
import ImportFolyamat from '../src/import/ImportFolyamat.svelte';
import { ApiHiba } from '../src/lib/core/api';
import { CoreKapcsolat } from '../src/lib/core/ws.svelte';
import { importApi } from '../src/lib/import/api';
import { ImportTar } from '../src/lib/import/allapot.svelte';
import { nyelv } from '../src/lib/i18n';
import { CEL, FORRAS, ID, allapot, elonezet } from './import-fixture';

let kapcsolat: CoreKapcsolat;
let onbezar: Mock<() => void>;
let onkesz: Mock<() => void>;

beforeEach(() => {
  nyelv.beallit('en');
  kapcsolat = new CoreKapcsolat('ws://127.0.0.1/ws');
  onbezar = vi.fn();
  onkesz = vi.fn();
});
afterEach(() => { cleanup(); vi.restoreAllMocks(); vi.useRealTimers(); nyelv.beallit('hu'); });

const mezo = (nev: string | RegExp) => screen.getByRole('textbox', { name: nev }) as HTMLInputElement;
async function ir(m: HTMLInputElement, ertek: string) { await fireEvent.input(m, { target: { value: ertek } }); }

async function megnyit(props: Record<string, unknown> = {}) {
  const tar = new ImportTar('obsidian');
  const r = render(ImportFolyamat, { props: { tar, kapcsolat, onbezar, onkesz, ...props } });
  return { ...r, tar };
}
async function elonezetig(elo = elonezet()) {
  vi.spyOn(importApi, 'obsidianElonezet').mockResolvedValue(elo);
  const r = await megnyit();
  await ir(mezo('Obsidian vault folder'), FORRAS);
  await fireEvent.click(screen.getByRole('button', { name: 'Preview import' }));
  await waitFor(() => expect(screen.getByRole('heading', { name: 'Review before importing' })).toBeTruthy());
  return r;
}
const esemeny = (e: Record<string, unknown>) => kapcsolat.szetoszt({ tipus: 'import', fajta: 'obsidian', ...e });

describe('mappaválasztás', () => {
  it('a forrásból cél-javaslatot ad, a célt kézzel át lehet írni; kiemeli, hogy az eredeti vault nem módosul', async () => {
    await megnyit();
    expect(screen.getByText(/Your original vault is not modified/)).toBeTruthy();
    expect((screen.getByRole('button', { name: 'Preview import' }) as HTMLButtonElement).disabled).toBe(true);
    await ir(mezo('Obsidian vault folder'), FORRAS);
    expect(mezo('New workspace folder').value).toBe(CEL);
    await ir(mezo('New workspace folder'), '/synthetic/Elsewhere');
    await ir(mezo('Obsidian vault folder'), '/synthetic/Other');
    expect(mezo('New workspace folder').value).toBe('/synthetic/Elsewhere');   // a kézzel írt cél megmarad
    expect((screen.getByRole('button', { name: 'Preview import' }) as HTMLButtonElement).disabled).toBe(false);
  });

  it('relatív útvonalat nem enged: hiba szóval, az előnézet gomb tiltott', async () => {
    await megnyit();
    await ir(mezo('Obsidian vault folder'), 'relative/dir');
    expect(screen.getByRole('alert').textContent).toContain('Enter the full path');
    await ir(mezo('New workspace folder'), '/synthetic/Dest');
    expect((screen.getByRole('button', { name: 'Preview import' }) as HTMLButtonElement).disabled).toBe(true);
  });

  it('a mappaválasztó (ha van) kitölti a mezőt; a hibája szóval jelenik meg', async () => {
    const valaszto = vi.fn().mockResolvedValueOnce('/synthetic/Picked').mockRejectedValueOnce(new Error('x'));
    await megnyit({ valaszto });
    const gombok = screen.getAllByRole('button', { name: /Choose folder/ });
    expect(gombok).toHaveLength(2);
    await fireEvent.click(gombok[0]);
    await waitFor(() => expect(mezo('Obsidian vault folder').value).toBe('/synthetic/Picked'));
    expect(valaszto).toHaveBeenCalledWith('Choose the Obsidian vault folder');
    await fireEvent.click(gombok[1]);
    await waitFor(() => expect(screen.getByRole('alert').textContent).toContain('folder chooser could not be opened'));
  });

  it('a mappaválasztó nélkül nincs „Choose folder” gomb (csak a beírt útvonal)', async () => {
    await megnyit();
    expect(screen.queryByRole('button', { name: /Choose folder/ })).toBeNull();
  });

  it('az előnézet a mezők értékeivel és az opciókkal hívódik', async () => {
    const elo = vi.spyOn(importApi, 'obsidianElonezet').mockResolvedValue(elonezet());
    await megnyit();
    await ir(mezo('Obsidian vault folder'), FORRAS);
    await ir(mezo('Workspace name (optional)'), 'My notes');
    await fireEvent.click(screen.getByRole('switch', { name: "Copy Obsidian's trash folder" }));
    await fireEvent.click(screen.getByRole('button', { name: 'Preview import' }));
    await waitFor(() => expect(elo).toHaveBeenCalledWith(FORRAS, CEL, { obsidian_mappa: true, kuka_mappa: true, nev: 'My notes' }));
  });

  it('az előnézet hibája (pl. érvénytelen kérés) hibapanelben, a mezők megmaradnak', async () => {
    vi.spyOn(importApi, 'obsidianElonezet').mockRejectedValue(new ApiHiba(400, 'The import request is not valid.', { kod: 'import.ervenytelen_keres', param: { mezo: 'forras' } }));
    await megnyit();
    await ir(mezo('Obsidian vault folder'), FORRAS);
    await fireEvent.click(screen.getByRole('button', { name: 'Preview import' }));
    await waitFor(() => expect(screen.getByRole('alert').textContent).toContain('The import request is not valid (forras).'));
    expect(screen.getByText('Check the folder paths and try again.')).toBeTruthy();
    expect(mezo('Obsidian vault folder').value).toBe(FORRAS);
  });
});

describe('előnézet', () => {
  it('mutatja a fájlokat, méretet, kihagyott elemeket okkal, link-számlálást, leképezett beállításokat és a nem támogatott plugineket', async () => {
    await elonezetig();
    const szoveg = document.body.textContent ?? '';
    expect(document.querySelector('[data-mezo="fajl_db"]')!.textContent).toBe('12');
    expect(document.querySelector('[data-mezo="bajt"]')!.textContent).toBe('34.6 KB');
    expect(document.querySelector('[data-mezo="masolando_db"]')!.textContent).toBe('12');
    // kihagyott elemek, okkal
    expect(screen.getByText('Skipped items', { selector: 'h4' }).textContent).toContain('(2)');
    expect(szoveg).toContain('Obsidian trash folder');
    expect(szoveg).toContain('Shortcut (symbolic link)');
    // linkek
    expect(document.querySelector('[data-mezo="wikilink_db"]')!.textContent).toBe('5');
    expect(document.querySelector('[data-mezo="markdown_link_db"]')!.textContent).toBe('2');
    expect(document.querySelector('[data-mezo="beagyazas_db"]')!.textContent).toBe('3');
    expect(szoveg).toContain('Links stay exactly as written');
    // leképezett beállítások: érthető név és érték
    const tabla = screen.getByRole('table', { name: 'Mapped settings' });
    expect(within(tabla).getByRole('rowheader', { name: 'Tab size' })).toBeTruthy();
    expect(within(tabla).getByText('Relative path')).toBeTruthy();
    expect(within(tabla).getByText('Dark')).toBeTruthy();
    expect(within(tabla).getAllByText('Will be set')).toHaveLength(2);
    expect(within(tabla).getByText('Already the same')).toBeTruthy();
    expect(szoveg).toContain('Not supported by Manifold');                      // hotkeys.json nem vitt át
    // pluginok: „not supported” jelölve
    const kozossegi = document.querySelector('[data-plugin="dataview"]')!;
    expect(kozossegi.textContent).toContain('Not supported');
    expect(document.querySelector('[data-plugin="sync"]')!.textContent).toContain('Not supported');
    expect(document.querySelector('[data-plugin="backlink"]')!.textContent).toContain('Supported');
    expect(document.querySelector('[data-plugin="file-explorer"]')!.textContent).toContain('Built in');
    // figyelmeztetések szóval, nem nyers kóddal
    expect(szoveg).toContain('Some Obsidian plugins are not supported.');
    expect(szoveg).not.toContain('nem_tamogatott_pluginok');
    // változtatás nélküli másolás + a forrás érintetlen
    expect(szoveg).toContain('Files are copied unchanged');
    expect(screen.getAllByText(/Your original vault is not modified/).length).toBeGreaterThan(0);
  });

  it('nem indít semmit a jóváhagyás előtt; a Start import pontosan a látott tervet (terv_hash) indítja', async () => {
    const indit = vi.spyOn(importApi, 'obsidianIndit').mockResolvedValue({ id: ID, allapot: 'fut' });
    await elonezetig();
    expect(indit).not.toHaveBeenCalled();
    expect(screen.getByText(/Nothing is copied until you press Start import/)).toBeTruthy();
    await fireEvent.click(screen.getByRole('button', { name: 'Start import' }));
    await waitFor(() => expect(indit).toHaveBeenCalledWith(FORRAS, CEL, { obsidian_mappa: true, kuka_mappa: false, nev: '' }, 'hash-1'));
    await waitFor(() => expect(screen.getByRole('heading', { name: 'Importing' })).toBeTruthy());
  });

  it('akadály esetén hibapanel + az akadályok mondatként, nincs Start import', async () => {
    await elonezetig(elonezet({ eredmeny: 'tilos', akadaly: ['cel_nem_ures', 'keves_hely'], terv_hash: null }));
    expect(screen.getByText('The import cannot start.')).toBeTruthy();
    expect(screen.getByText('Change the folders and preview again.')).toBeTruthy();
    expect(screen.queryByRole('button', { name: 'Start import' })).toBeNull();
    const lista = screen.getByRole('list', { name: 'Reasons the import cannot start' });
    expect(lista.textContent).toContain('The destination folder is not empty');
    expect(lista.textContent).toContain('not enough free space');
    expect(lista.textContent).not.toContain('cel_nem_ures');
    await fireEvent.click(screen.getAllByRole('button', { name: 'Change folders' })[0]);
    expect(screen.getByRole('textbox', { name: 'Obsidian vault folder' })).toBeTruthy();
  });

  it('az ütközéseket felsorolja okkal, és az import nem indítható', async () => {
    await elonezetig(elonezet({
      eredmeny: 'tilos', akadaly: ['nev_utkozes'], terv_hash: null,
      utkozesek: [{ ut: 'Note.md', masik: 'note.md', ok: 'kis_nagy' }, { ut: 'Cafe.md', ok: 'cel_elter' }],
    }));
    const lista = document.querySelector('[data-lista="utkozesek"]')!;
    expect(lista.textContent).toContain('Note.md');
    expect(lista.textContent).toContain('note.md');
    expect(lista.textContent).toContain('Names differ only by letter case');
    expect(lista.textContent).toContain('A different file with this name already exists in the destination');
    expect(screen.queryByRole('button', { name: 'Start import' })).toBeNull();
  });

  it('a kihagyott elemek részletei kinyithatók, az ok mellett az útvonal áll', async () => {
    await elonezetig();
    const reszlet = screen.getByText('Show skipped items').closest('details')!;
    expect(within(reszlet).getByText('.trash')).toBeTruthy();
    expect(within(reszlet).getByText('Shortcut.md')).toBeTruthy();
  });

  it('megszakadt korábbi futás: „Resume import” gomb és magyarázat', async () => {
    const indit = vi.spyOn(importApi, 'obsidianIndit').mockResolvedValue({ id: ID, allapot: 'fut' });
    await elonezetig(elonezet({ allapot: allapot({ allapot: 'hiba', hiba: { kod: 'import.masolas_hiba', uzenet: 'x' } }) }));
    expect(screen.getByText(/stopped before it finished/)).toBeTruthy();
    await fireEvent.click(screen.getByRole('button', { name: 'Resume import' }));
    await waitFor(() => expect(indit).toHaveBeenCalledTimes(1));
  });

  it('már kész import: nem másol újra, visszavonást kínál', async () => {
    await elonezetig(elonezet({ eredmeny: 'kesz' }));
    expect(screen.getByText('This vault was already imported')).toBeTruthy();
    expect(screen.queryByRole('button', { name: 'Start import' })).toBeNull();
    expect(screen.getByRole('button', { name: 'Undo import' })).toBeTruthy();
  });

  it('terv_valtozott (409) az indításnál: hiba ikonnal+szóval, teendővel, az előnézet újra kérhető', async () => {
    const elo = vi.spyOn(importApi, 'obsidianElonezet').mockResolvedValue(elonezet());
    vi.spyOn(importApi, 'obsidianIndit').mockRejectedValue(new ApiHiba(409, 'The folders changed since the preview. Run the preview again.', { kod: 'import.terv_valtozott' }));
    await megnyit();
    await ir(mezo('Obsidian vault folder'), FORRAS);
    await fireEvent.click(screen.getByRole('button', { name: 'Preview import' }));
    await waitFor(() => screen.getByRole('button', { name: 'Start import' }));
    await fireEvent.click(screen.getByRole('button', { name: 'Start import' }));
    await waitFor(() => expect(screen.getByRole('alert').textContent).toContain('The folders changed since the preview'));
    expect(screen.getByText('The folders changed after the preview. Preview the import again, then start it.')).toBeTruthy();
    await fireEvent.click(screen.getByRole('button', { name: 'Preview again' }));
    await waitFor(() => expect(elo).toHaveBeenCalledTimes(2));
  });
});

describe('futás és összegzés', () => {
  async function fut() {
    vi.spyOn(importApi, 'obsidianIndit').mockResolvedValue({ id: ID, allapot: 'fut' });
    const r = await elonezetig();
    await fireEvent.click(screen.getByRole('button', { name: 'Start import' }));
    await waitFor(() => expect(screen.getByRole('heading', { name: 'Importing' })).toBeTruthy());
    return r;
  }

  it('a WS import eseményből mutat haladást (lépés, darabszám, méret, százalék), a más importét figyelmen kívül hagyja', async () => {
    await fut();
    esemeny({ id: 'obs-ffffffffffffffff', lepes: 'masolas', kesz_db: 9, osszes_db: 9, bajt: 1 });
    expect(document.querySelector('[data-haladas]')!.textContent).toContain('Starting the import');
    esemeny({ id: ID, lepes: 'masolas', kesz_db: 5, osszes_db: 10, bajt: 2000 });
    await waitFor(() => expect(document.querySelector('[data-haladas]')!.textContent).toContain('5 of 10 files copied · 2.0 KB · 50 %'));
    expect(screen.getByText('Copying files')).toBeTruthy();
    const folyamat = document.querySelector('progress') as HTMLProgressElement;
    expect(folyamat.value).toBe(50);
    esemeny({ id: ID, lepes: 'munkater' });
    await waitFor(() => expect(screen.getByText('Creating the workspace')).toBeTruthy());
    esemeny({ id: ID, lepes: 'beallitasok' });
    await waitFor(() => expect(screen.getByText('Applying settings')).toBeTruthy());
  });

  it('a „Hide” elrejti a panelt (a futás megy tovább), nem szakítja meg', async () => {
    await fut();
    await fireEvent.click(screen.getByRole('button', { name: 'Hide' }));
    expect(onbezar).toHaveBeenCalledTimes(1);
    expect(screen.getByText(/keeps running and appears in the import history/)).toBeTruthy();
  });

  it('siker: összegzés a számokkal, a forrás érintetlen, a figyelmeztetések, a Done lezár', async () => {
    const eredmeny = { ...allapot().eredmeny!, forras_valtozott: ['Edited.md'] };
    vi.spyOn(importApi, 'allapot').mockResolvedValue(allapot({ eredmeny }));
    await fut();
    esemeny({ id: ID, allapot: 'kesz', eredmeny });
    await waitFor(() => expect(screen.getByRole('heading', { name: /Import complete/ })).toBeTruthy());
    expect(document.querySelector('[data-mezo="masolt_db"]')!.textContent).toBe('12');
    expect(document.querySelector('[data-mezo="cel"]')!.textContent).toBe(CEL);
    expect(screen.getAllByText(/Your original vault is not modified/).length).toBeGreaterThan(0);
    expect(screen.getByText(/changed while they were being copied/)).toBeTruthy();
    expect(screen.getByText('Edited.md')).toBeTruthy();
    expect(screen.getByText(/Settings written:/).textContent).toContain('Tab size');
    expect(screen.queryByRole('button', { name: 'Open workspace chooser' })).toBeNull();   // héj nélkül nincs
    await fireEvent.click(screen.getByRole('button', { name: 'Done' }));
    expect(onkesz).toHaveBeenCalledTimes(1);
    expect(screen.getByRole('textbox', { name: 'Obsidian vault folder' })).toBeTruthy();   // új import kezdhető
  });

  it('a héjban fut: a „Open workspace chooser” a munkatér-választót nyitja', async () => {
    const post = vi.fn();
    (window as unknown as { webkit: unknown }).webkit = { messageHandlers: { manifold: { postMessage: post } } };
    try {
      vi.spyOn(importApi, 'allapot').mockResolvedValue(allapot());
      await fut();
      esemeny({ id: ID, allapot: 'kesz', eredmeny: allapot().eredmeny });
      await fireEvent.click(await screen.findByRole('button', { name: 'Open workspace chooser' }));
      expect(post).toHaveBeenCalledWith({ tipus: 'munkater-valaszto' });
    } finally {
      delete (window as unknown as { webkit?: unknown }).webkit;
    }
  });

  it('hiba a futás közben: ikon + szó + teendő a hibakód szerint, a másolt fájlok megmaradnak; „Review and resume” újra előnézetet kér', async () => {
    const getState = vi.spyOn(importApi, 'allapot').mockResolvedValue(allapot({ allapot: 'hiba', hiba: { kod: 'import.forras_valtozik', uzenet: 'x', param: { ut: 'Busy.md' } } }));
    await fut();
    esemeny({ id: ID, allapot: 'hiba', hiba: { kod: 'import.forras_valtozik', uzenet: 'A source file kept changing during the import: Busy.md. Try again.' } });
    await waitFor(() => expect(screen.getByRole('heading', { name: 'The import stopped' })).toBeTruthy());
    await waitFor(() => expect(getState).toHaveBeenCalled());
    const riado = screen.getByRole('alert');
    expect(riado.textContent).toContain('A source file kept changing during the import');
    expect(screen.getByText('Close the app that is changing the vault, then resume the import.')).toBeTruthy();
    expect(screen.getByText(/Files copied so far are kept/)).toBeTruthy();
    const elo = vi.spyOn(importApi, 'obsidianElonezet').mockResolvedValue(elonezet({ allapot: allapot({ allapot: 'hiba' }) }));
    await fireEvent.click(screen.getByRole('button', { name: 'Review and resume' }));
    await waitFor(() => expect(elo).toHaveBeenCalled());
    await waitFor(() => expect(screen.getByRole('button', { name: 'Resume import' })).toBeTruthy());
  });

  it('ismeretlen hibakódnál a core angol mondata a tartalék; a nyers kód nem jelenik meg', async () => {
    vi.spyOn(importApi, 'allapot').mockResolvedValue(allapot({ allapot: 'hiba' }));
    await fut();
    esemeny({ id: ID, allapot: 'hiba', hiba: { kod: 'import.valami_uj', uzenet: 'Something specific went wrong.' } });
    await waitFor(() => expect(screen.getByRole('alert').textContent).toContain('Something specific went wrong.'));
    expect(screen.getByText('Try again in a moment.')).toBeTruthy();
    expect(document.body.textContent).not.toContain('import.valami_uj');
  });

  it('elveszett lezáró esemény: az újracsatlakozás („hello”) után az állapotból kész lesz', async () => {
    vi.spyOn(importApi, 'allapot').mockResolvedValue(allapot());
    await fut();
    kapcsolat.szetoszt({ tipus: 'hello' });
    await waitFor(() => expect(screen.getByRole('heading', { name: /Import complete/ })).toBeTruthy());
  });

  it('WS nélkül időzítéssel olvassa az állapotot, és lezárás után leáll', async () => {
    vi.useFakeTimers();
    const getState = vi.spyOn(importApi, 'allapot').mockResolvedValueOnce(allapot({ allapot: 'fut', fut: true })).mockResolvedValue(allapot());
    vi.spyOn(importApi, 'obsidianElonezet').mockResolvedValue(elonezet());
    vi.spyOn(importApi, 'obsidianIndit').mockResolvedValue({ id: ID, allapot: 'fut' });
    const tar = new ImportTar('obsidian');
    render(ImportFolyamat, { props: { tar, kapcsolat: null } });
    await ir(mezo('Obsidian vault folder'), FORRAS);
    await fireEvent.click(screen.getByRole('button', { name: 'Preview import' }));
    await vi.advanceTimersByTimeAsync(0);
    await fireEvent.click(screen.getByRole('button', { name: 'Start import' }));
    await vi.advanceTimersByTimeAsync(0);
    expect(tar.fazis).toBe('fut');
    await vi.advanceTimersByTimeAsync(2600);
    expect(tar.fazis).toBe('fut');
    await vi.advanceTimersByTimeAsync(2600);
    expect(tar.fazis).toBe('kesz');
    const hivasok = getState.mock.calls.length;
    await vi.advanceTimersByTimeAsync(10_000);
    expect(getState.mock.calls.length).toBe(hivasok);
  });

  it('a core „már kész” (ismétlés) válasza közvetlenül az összegzésre visz', async () => {
    vi.spyOn(importApi, 'allapot').mockResolvedValue(allapot());
    vi.spyOn(importApi, 'obsidianIndit').mockResolvedValue({ id: ID, allapot: 'kesz', ismetles: true });
    await elonezetig();
    await fireEvent.click(screen.getByRole('button', { name: 'Start import' }));
    await waitFor(() => expect(screen.getByRole('heading', { name: /Import complete/ })).toBeTruthy());
  });
});

describe('Undo import', () => {
  async function keszig() {
    vi.spyOn(importApi, 'allapot').mockResolvedValue(allapot());
    vi.spyOn(importApi, 'obsidianIndit').mockResolvedValue({ id: ID, allapot: 'fut' });
    await elonezetig();
    await fireEvent.click(screen.getByRole('button', { name: 'Start import' }));
    await waitFor(() => screen.getByRole('heading', { name: 'Importing' }));
    esemeny({ id: ID, allapot: 'kesz', eredmeny: allapot().eredmeny });
    await waitFor(() => screen.getByRole('heading', { name: /Import complete/ }));
  }

  it('megerősítést kér, kimondja, hogy a módosított és az idegen fájlok maradnak és az eredeti vault érintetlen; a „Keep import” nem hív semmit', async () => {
    const vissza = vi.spyOn(importApi, 'visszafordit');
    await keszig();
    await fireEvent.click(screen.getByRole('button', { name: 'Undo import' }));
    const panel = document.querySelector('[data-visszaford]') as HTMLElement;
    expect(panel.textContent).toContain('move to the Trash');
    expect(panel.textContent).toContain('Files you changed after the import, and files that were not part of it, stay where they are.');
    expect(panel.textContent).toContain('Your original vault is not modified');
    expect(document.activeElement).toBe(within(panel).getByRole('button', { name: 'Keep import' }));   // a biztonságos válasz kap fókuszt
    expect(vissza).not.toHaveBeenCalled();
    await fireEvent.click(within(panel).getByRole('button', { name: 'Keep import' }));
    expect(document.querySelector('[data-visszaford]')).toBeNull();
    expect(vissza).not.toHaveBeenCalled();
  });

  it('visszavonás: a Kukába tett elemek száma és a megtartott fájlok oka (módosított / idegen)', async () => {
    const vissza = vi.spyOn(importApi, 'visszafordit').mockResolvedValue({
      id: ID, allapot: 'reszben_visszaforditva', kukaba: ['a', 'b', 'c'],
      megtartva: [{ ut: 'Edited.md', ok: 'modositott' }, { ut: 'Mine.txt', ok: 'idegen' }],
    });
    await keszig();
    await fireEvent.click(screen.getByRole('button', { name: 'Undo import' }));
    await fireEvent.click(within(document.querySelector('[data-visszaford]') as HTMLElement).getByRole('button', { name: 'Undo import' }));
    await waitFor(() => expect(vissza).toHaveBeenCalledWith(ID));
    await waitFor(() => expect(screen.getByRole('heading', { name: /Import partly undone/ })).toBeTruthy());
    const panel = document.querySelector('[data-visszaford]') as HTMLElement;
    expect(panel.textContent).toContain('3 items moved to the Trash');
    const lista = within(panel).getByRole('list', { name: 'Files that stayed' });
    expect(lista.textContent).toContain('Edited.md');
    expect(lista.textContent).toContain('changed after the import');
    expect(lista.textContent).toContain('Mine.txt');
    expect(lista.textContent).toContain('not part of the import');
  });

  it('egyetlen elemnél egyes szám; a hiba (munkatér használatban) ikonnal+szóval, teendővel, újrapróbálható', async () => {
    const vissza = vi.spyOn(importApi, 'visszafordit')
      .mockRejectedValueOnce(new ApiHiba(409, 'Close the imported workspace before undoing the import.', { kod: 'import.munkater_hasznalatban' }))
      .mockResolvedValueOnce({ id: ID, allapot: 'visszaforditva', kukaba: ['a'], megtartva: [] });
    await keszig();
    await fireEvent.click(screen.getByRole('button', { name: 'Undo import' }));
    await fireEvent.click(within(document.querySelector('[data-visszaford]') as HTMLElement).getByRole('button', { name: 'Undo import' }));
    await waitFor(() => expect(screen.getByRole('alert').textContent).toContain('Close the imported workspace before undoing the import.'));
    expect(screen.getByText('Open a different workspace, then undo the import.')).toBeTruthy();
    await fireEvent.click(screen.getByRole('button', { name: 'Try again' }));
    await waitFor(() => expect(screen.getByRole('heading', { name: /Import undone/ })).toBeTruthy());
    expect(document.querySelector('[data-visszaford]')!.textContent).toContain('1 item moved to the Trash');
    expect(vissza).toHaveBeenCalledTimes(2);
  });
});
