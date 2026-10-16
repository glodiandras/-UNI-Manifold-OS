// F8 Import history (GET /api/import): állapot ikonnal+szóval, napló, folytatás, visszavonás, frissülés a WS eseményre, fajta-szűrés.
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/svelte';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import ImportLista from '../src/import/ImportLista.svelte';
import { ApiHiba } from '../src/lib/core/api';
import { CoreKapcsolat } from '../src/lib/core/ws.svelte';
import { importApi } from '../src/lib/import/api';
import { nyelv } from '../src/lib/i18n';
import { ID, allapot } from './import-fixture';

let kapcsolat: CoreKapcsolat;
beforeEach(() => { nyelv.beallit('en'); kapcsolat = new CoreKapcsolat('ws://127.0.0.1/ws'); });
afterEach(() => { cleanup(); vi.restoreAllMocks(); nyelv.beallit('hu'); });

const sor = (id: string) => document.querySelector<HTMLElement>(`[data-import="${id}"]`)!;
const ID2 = 'obs-aaaaaaaaaaaaaaaa';
const ID3 = 'obs-bbbbbbbbbbbbbbbb';
const ID4 = 'obs-cccccccccccccccc';
const V2 = 'v2-0123456789abcdef';

describe('Import history', () => {
  it('állapotonként ikon + szó, időpontok, eredmény; a v2-import normál fajtánál nem látszik', async () => {
    vi.spyOn(importApi, 'lista').mockResolvedValue({ importok: [
      allapot(),
      allapot({ id: ID2, allapot: 'hiba', hiba: { kod: 'import.masolas_hiba', uzenet: 'The import stopped: disk is full. Run the import again to continue, or undo it.' }, eredmeny: null }),
      allapot({ id: ID3, allapot: 'fut', fut: false, eredmeny: null }),
      allapot({ id: ID4, allapot: 'fut', fut: true, eredmeny: null }),
      allapot({ id: V2, fajta: 'v2', cel: undefined }),
    ] });
    render(ImportLista, { props: { kapcsolat } });
    await waitFor(() => expect(sor(ID)).toBeTruthy());
    expect(document.querySelector(`[data-import="${V2}"]`)).toBeNull();
    expect(sor(ID).textContent).toContain('Completed');
    expect(sor(ID).textContent).toContain('12 files copied · 34.6 KB');
    expect(sor(ID).textContent).toContain('/synthetic/Vault (Manifold)');
    expect(sor(ID).querySelector('svg')).toBeTruthy();                       // az állapot ikonnal is jön
    expect(sor(ID2).textContent).toContain('Failed');
    expect(within(sor(ID2)).getByRole('alert').textContent).toContain('The import stopped: disk is full.');
    expect(sor(ID2).textContent).toContain('Files copied so far are kept. Review and resume the import, or undo it.');
    expect(sor(ID3).textContent).toContain('Interrupted');
    expect(sor(ID4).textContent).toContain('Running');
    expect(within(sor(ID4)).queryByRole('button', { name: 'Undo import' })).toBeNull();      // futó import nem vonható vissza
    expect(within(sor(ID4)).queryByRole('button', { name: 'Review and resume' })).toBeNull();
  });

  it('a részletek a naplómappát és az opciókat mutatják', async () => {
    vi.spyOn(importApi, 'lista').mockResolvedValue({ importok: [allapot()] });
    render(ImportLista, { props: { kapcsolat } });
    await waitFor(() => expect(sor(ID)).toBeTruthy());
    expect(sor(ID).querySelector('[data-naplo]')).toBeNull();
    await fireEvent.click(within(sor(ID)).getByRole('button', { name: 'Show details' }));
    const naplo = sor(ID).querySelector('[data-naplo]')!;
    expect(naplo.textContent).toContain('/synthetic/install/imports/obs-0123456789abcdef');
    expect(naplo.textContent).toContain('Copy Obsidian settings');
    expect(naplo.textContent).toContain(ID);
    await fireEvent.click(within(sor(ID)).getByRole('button', { name: 'Hide details' }));
    expect(sor(ID).querySelector('[data-naplo]')).toBeNull();
  });

  it('a v2 fajta csak kérésre: a v2-importok a Developer-listán, módosítás-számmal', async () => {
    vi.spyOn(importApi, 'lista').mockResolvedValue({ importok: [allapot(), allapot({ id: V2, fajta: 'v2', cel: undefined, eredmeny: { id: V2, allapot: 'kesz', valtozas: 3, irt: ['workspace.toml'], naplo: '/synthetic/state/import/x' } })] });
    render(ImportLista, { props: { fajta: 'v2', kapcsolat } });
    await waitFor(() => expect(sor(V2)).toBeTruthy());
    expect(document.querySelector(`[data-import="${ID}"]`)).toBeNull();
    expect(sor(V2).textContent).toContain('3 settings changed');
    expect(sor(V2).textContent).toContain('Manifold v2 import');
  });

  it('üres állapot magyarázattal; betöltési hiba hibapanelben újrapróbálással', async () => {
    const lista = vi.spyOn(importApi, 'lista').mockRejectedValueOnce(new ApiHiba(503, 'Unavailable')).mockResolvedValueOnce({ importok: [] });
    render(ImportLista, { props: { kapcsolat } });
    await waitFor(() => expect(screen.getByRole('alert').textContent).toContain('Unavailable'));
    await fireEvent.click(screen.getByRole('button', { name: 'Try again' }));
    await waitFor(() => expect(screen.getByText('No imports yet')).toBeTruthy());
    expect(screen.getByText(/appear here with their status/)).toBeTruthy();
    expect(lista).toHaveBeenCalledTimes(2);
  });

  it('a megszakadt/hibás importnál a „Review and resume” az onfolytat-ot hívja a napló-állapottal', async () => {
    const a = allapot({ id: ID3, allapot: 'fut', fut: false, eredmeny: null });
    vi.spyOn(importApi, 'lista').mockResolvedValue({ importok: [a] });
    const onfolytat = vi.fn();
    render(ImportLista, { props: { kapcsolat, onfolytat } });
    await waitFor(() => expect(sor(ID3)).toBeTruthy());
    await fireEvent.click(within(sor(ID3)).getByRole('button', { name: 'Review and resume' }));
    expect(onfolytat).toHaveBeenCalledWith(expect.objectContaining({ id: ID3, forras: a.forras, cel: a.cel }));
  });

  it('a kész import sorából visszavonható (megerősítéssel), utána a lista újratölt', async () => {
    const lista = vi.spyOn(importApi, 'lista')
      .mockResolvedValueOnce({ importok: [allapot()] })
      .mockResolvedValue({ importok: [allapot({ allapot: 'visszaforditva', visszaforditas: { id: ID, allapot: 'visszaforditva', kukaba: ['a'], megtartva: [] } })] });
    const vissza = vi.spyOn(importApi, 'visszafordit').mockResolvedValue({ id: ID, allapot: 'visszaforditva', kukaba: ['a', 'b'], megtartva: [] });
    render(ImportLista, { props: { kapcsolat } });
    await waitFor(() => expect(sor(ID)).toBeTruthy());
    await fireEvent.click(within(sor(ID)).getByRole('button', { name: 'Undo import' }));
    expect(vissza).not.toHaveBeenCalled();
    await fireEvent.click(within(sor(ID).querySelector('[data-visszaford]') as HTMLElement).getByRole('button', { name: 'Undo import' }));
    await waitFor(() => expect(vissza).toHaveBeenCalledWith(ID));
    await waitFor(() => expect(lista).toHaveBeenCalledTimes(2));
    await waitFor(() => expect(sor(ID).textContent).toContain('Undone'));
  });

  it('a WS import lezáró eseményére újratölt, a haladás-eseményre nem', async () => {
    const lista = vi.spyOn(importApi, 'lista').mockResolvedValue({ importok: [] });
    render(ImportLista, { props: { kapcsolat } });
    await waitFor(() => expect(lista).toHaveBeenCalledTimes(1));
    kapcsolat.szetoszt({ tipus: 'import', id: ID, lepes: 'masolas', kesz_db: 1, osszes_db: 5, bajt: 1 });
    await Promise.resolve();
    expect(lista).toHaveBeenCalledTimes(1);
    kapcsolat.szetoszt({ tipus: 'import', id: ID, allapot: 'kesz', eredmeny: {} });
    await waitFor(() => expect(lista).toHaveBeenCalledTimes(2));
  });
});
