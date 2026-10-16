// F8 „Import from Manifold v2” (csak Developer módban): előnézet → Apply → újraindítási jelzés → visszavonás; a hibakódok.
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/svelte';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import ImportFolyamat from '../src/import/ImportFolyamat.svelte';
import { ApiHiba } from '../src/lib/core/api';
import { CoreKapcsolat } from '../src/lib/core/ws.svelte';
import { importApi } from '../src/lib/import/api';
import { ImportTar } from '../src/lib/import/allapot.svelte';
import { nyelv } from '../src/lib/i18n';
import { v2Elonezet } from './import-fixture';

const V2ID = 'v2-0123456789abcdef';
const FORRAS = '/synthetic/old-os';
const mezo = (nev: string | RegExp) => screen.getByRole('textbox', { name: nev }) as HTMLInputElement;

beforeEach(() => nyelv.beallit('en'));
afterEach(() => { cleanup(); vi.restoreAllMocks(); nyelv.beallit('hu'); });

async function elonezetig(elo = v2Elonezet()) {
  vi.spyOn(importApi, 'v2Elonezet').mockResolvedValue(elo);
  const onbezar = vi.fn();
  const tar = new ImportTar('v2');
  render(ImportFolyamat, { props: { tar, kapcsolat: new CoreKapcsolat('ws://127.0.0.1/ws'), onbezar } });
  await fireEvent.input(mezo('Manifold-OS folder'), { target: { value: FORRAS } });
  await fireEvent.click(screen.getByRole('button', { name: 'Preview import' }));
  await waitFor(() => expect(screen.getByRole('heading', { name: 'Review before importing' })).toBeTruthy());
  return { tar, onbezar };
}

describe('Import from Manifold v2', () => {
  it('csak a forrás-mappát kéri (nincs cél, nincs Obsidian-opció), és kimondja, hogy a mappa csak olvasott', async () => {
    render(ImportFolyamat, { props: { fajta: 'v2', kapcsolat: null } });
    expect(screen.getByRole('heading', { name: 'Import from Manifold v2' })).toBeTruthy();
    expect(screen.getByText('The Manifold-OS folder is only read. It is never changed.')).toBeTruthy();
    expect(screen.queryByRole('textbox', { name: 'New workspace folder' })).toBeNull();
    expect(screen.queryByRole('switch')).toBeNull();
  });

  it('az előnézet a változtatásokat, ütközéseket (nem íródnak felül), nem átvett elemeket és az újraindítás szükségét mutatja', async () => {
    const elo = await elonezetig();
    expect(importApi.v2Elonezet).toHaveBeenCalledWith(FORRAS);
    const tabla = screen.getByRole('table', { name: 'Settings to write' });
    expect(within(tabla).getByRole('rowheader', { name: 'sema.mod' })).toBeTruthy();
    expect(within(tabla).getByText('szigoru')).toBeTruthy();
    expect(document.querySelector('[data-sema="ir"]')!.textContent).toBe('will be created in the workspace');
    const utkozes = document.querySelector('[data-lista="utkozesek"]')!;
    expect(utkozes.textContent).toContain('beallitasok.x');
    expect(screen.getByText('Your workspace already sets these to another value, so they stay as they are.')).toBeTruthy();
    expect(document.querySelector('[data-lista="nem-atvett"]')!.textContent).toContain('The schema file is not valid');
    expect(screen.getByText('Applying this import needs a restart of Manifold to take effect.')).toBeTruthy();
    expect(screen.getByText('Conflicting settings are skipped and not overwritten.')).toBeTruthy();
    expect(screen.getByText(/Nothing is written until you press Apply import/)).toBeTruthy();
    expect(elo.tar.indithato).toBe(true);
  });

  it('nincs mit írni: az Apply tiltott és a magyarázat látszik', async () => {
    await elonezetig(v2Elonezet({ kulcsok: [], valtozas_db: 0, sema: null, utkozesek: [], nem_atvett: [], figyelmeztetes: [], ujrainditas: false, eredmeny: 'mehet' }));
    expect(screen.getByText('The workspace already matches. There is nothing to import.')).toBeTruthy();
    expect((screen.getByRole('button', { name: 'Apply import' }) as HTMLButtonElement).disabled).toBe(true);
  });

  it('akadály (nincs konfig): hibapanel, nincs Apply', async () => {
    await elonezetig(v2Elonezet({ eredmeny: 'tilos', akadaly: ['v2_nincs_konfig'], terv_hash: null, kulcsok: [], utkozesek: [], nem_atvett: [], sema: null, valtozas_db: 0 }));
    expect(screen.getByText('The import cannot start.')).toBeTruthy();
    expect(screen.getByText(/has no config\/os.toml file/)).toBeTruthy();
    expect(screen.queryByRole('button', { name: 'Apply import' })).toBeNull();
  });

  it('Apply: szinkron válasz, összegzés újraindítási jelzéssel; a visszavonás megerősítéssel és a v2 szövegével', async () => {
    const indit = vi.spyOn(importApi, 'v2Indit').mockResolvedValue({ id: V2ID, allapot: 'kesz', valtozas: 2, irt: ['workspace.toml', 'schema.json'], kulcsok: ['sema.mod'], ujrainditas: true });
    const vissza = vi.spyOn(importApi, 'visszafordit').mockResolvedValue({ id: V2ID, allapot: 'visszaforditva', visszaallitva: ['workspace.toml', 'schema.json'], kukaba: [], megtartva: [], ujrainditas: true });
    await elonezetig();
    expect(indit).not.toHaveBeenCalled();
    await fireEvent.click(screen.getByRole('button', { name: 'Apply import' }));
    await waitFor(() => expect(indit).toHaveBeenCalledWith(FORRAS, 'v2-hash'));
    await waitFor(() => expect(screen.getByRole('heading', { name: /Settings imported/ })).toBeTruthy());
    expect(document.querySelector('[data-mezo="valtozas"]')!.textContent).toBe('2');
    expect(screen.getByText('Restart Manifold for the imported settings to take effect.')).toBeTruthy();
    await fireEvent.click(screen.getByRole('button', { name: 'Undo import' }));
    const panel = document.querySelector('[data-visszaford]') as HTMLElement;
    expect(panel.textContent).toContain('The settings this import changed are restored');
    await fireEvent.click(within(panel).getByRole('button', { name: 'Undo import' }));
    await waitFor(() => expect(vissza).toHaveBeenCalledWith(V2ID));
    await waitFor(() => expect(screen.getByRole('heading', { name: /Import undone/ })).toBeTruthy());
    expect(document.querySelector('[data-visszaford]')!.textContent).toContain('2 settings files restored');
  });

  it('a v2-visszavonás ütközése (módosult fájl): hiba ikonnal+szóval, a fájl nevével; semmi nem változott', async () => {
    vi.spyOn(importApi, 'v2Indit').mockResolvedValue({ id: V2ID, allapot: 'kesz', valtozas: 1, irt: ['workspace.toml'], ujrainditas: true });
    vi.spyOn(importApi, 'visszafordit').mockRejectedValue(new ApiHiba(409, 'The file workspace.toml changed after the import. Nothing was undone.', { kod: 'import.visszafordit_utkozes', param: { ut: 'workspace.toml' } }));
    await elonezetig();
    await fireEvent.click(screen.getByRole('button', { name: 'Apply import' }));
    await waitFor(() => screen.getByRole('button', { name: 'Undo import' }));
    await fireEvent.click(screen.getByRole('button', { name: 'Undo import' }));
    await fireEvent.click(within(document.querySelector('[data-visszaford]') as HTMLElement).getByRole('button', { name: 'Undo import' }));
    await waitFor(() => expect(screen.getByRole('alert').textContent).toContain('The import cannot be undone because of workspace.toml. Nothing was changed.'));
    expect(screen.getByText('Nothing was changed. Check the file named above, then try again.')).toBeTruthy();
  });

  it('403 import.fejleszto_mod és 409 import.terv_valtozott az indításnál: a hibakód szerinti mondat és teendő', async () => {
    const indit = vi.spyOn(importApi, 'v2Indit')
      .mockRejectedValueOnce(new ApiHiba(403, 'This import is available in Developer mode only.', { kod: 'import.fejleszto_mod' }))
      .mockRejectedValueOnce(new ApiHiba(409, 'x', { kod: 'import.terv_valtozott' }));
    await elonezetig();
    await fireEvent.click(screen.getByRole('button', { name: 'Apply import' }));
    await waitFor(() => expect(screen.getByRole('alert').textContent).toContain('available in Developer mode only'));
    expect(screen.getByText('Turn on Developer mode in Settings > About to use this import.')).toBeTruthy();
    await fireEvent.click(screen.getByRole('button', { name: 'Apply import' }));
    await waitFor(() => expect(screen.getByText('The folders changed after the preview. Preview the import again, then start it.')).toBeTruthy());
    expect(indit).toHaveBeenCalledTimes(2);
  });
});
