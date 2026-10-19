// S1/U02: a kompakt panel fontos állapota kézi összecsukás és csend közben is elérhető marad.
// Tisztán számoló API + memóriabeli dokumentum; lemezes írás nincs.
import { Text } from '@codemirror/state';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/svelte';
import { flushSync } from 'svelte';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { ApiHiba } from '../src/lib/core/api';
import { csend } from '../src/lib/elrendezes/csend.svelte';
import type { Csere } from '../src/szerkeszto/dokumentum/kulonbseg';
import Tulajdonsagok from '../src/szerkeszto/tulajdonsagok/Tulajdonsagok.svelte';
import { tipusValtozas } from '../src/szerkeszto/tulajdonsagok/modell.svelte';
import type { Elemzes, ModositEredmeny, Sema, TulajdonsagTipusok } from '../src/szerkeszto/tulajdonsagok/tipusok';

const FM = '---\n# Preserve this comment.\nStatus: Draft\nCount: 3\n---\n\n# Árvíztűrő\n\nBody with [[Untouched#Heading|alias]].\n';
const PROBLEMA = { kod: 'ertekkeszlet', szint: 'sertes' as const, kulcs: 'Status', ertek: 'Review', uzenet: 'Review requires explicit confirmation.' };

function fixture(nyitva = true) {
  let doc = Text.of(FM.split('\n'));
  const api = {
    elemez: vi.fn(async (): Promise<Elemzes> => ({ van: true, hiba: null, osztaly: 'normal', kulcsok: ['Status', 'Count'], problemak: [], tulajdonsagok: [
      { kulcs: 'Status', tipus: 'text', ertek: doc.toString().includes('Status: Review') ? 'Review' : 'Draft', ervenyes: true },
      { kulcs: 'Count', tipus: 'number', ertek: 3, ervenyes: true },
    ] })),
    sema: vi.fn(async (): Promise<Sema> => ({ mezosorrend: [], extra_kulcsok: [], tags_ertekkeszlet: [], status_ertekkeszlet: [], status_gazdai: false, osztaly: null })),
    modosit: vi.fn(async (): Promise<ModositEredmeny> => ({ ok: false, fm_uj: null, megerositheto: true, valtozas: true, problemak: [PROBLEMA] })),
    tipusok: vi.fn(async (): Promise<TulajdonsagTipusok> => ({ rev: 's1-rev', types: { Status: 'text', Count: 'number' } })),
    tipusBeallit: vi.fn(async (): Promise<TulajdonsagTipusok> => { throw new ApiHiba(409, 'Conflict'); }),
  };
  const alkalmaz = vi.fn((c: Csere) => { const old = doc.toString(); doc = Text.of((old.slice(0, c.from) + c.insert + old.slice(c.to)).split('\n')); });
  const felallit = () => render(Tulajdonsagok, { props: { ut: 'Synthetic.md', szoveg: () => doc, alkalmaz, valtozat: 0, irhato: true, nyitva, api } });
  return { api, alkalmaz, felallit, szoveg: () => doc.toString() };
}

const kapcsolo = () => document.querySelector<HTMLButtonElement>('button.kapcsolo')!;
const lathato = (el: HTMLElement) => expect(el.closest('[hidden], [inert], [data-csend-rejt]')).toBeNull();
beforeEach(() => { csend.be = true; tipusValtozas.rev = null; });
afterEach(() => { cleanup(); csend.be = false; document.body.textContent = ''; });

describe('S1/U02: a csend megőrzi az állapotot és a döntési lehetőségeket', () => {
  it('a kulcs–érték alapból látható; a csend kapcsolgatása nem csukja össze és nem nyitja ki a kézi állapotot', async () => {
    const f = fixture(); f.felallit();
    expect((await screen.findByLabelText('Status') as HTMLInputElement).value).toBe('Draft');
    expect((screen.getByLabelText('Count') as HTMLInputElement).value).toBe('3');
    expect(kapcsolo().getAttribute('aria-expanded')).toBe('true');
    csend.be = false; flushSync(); csend.be = true; flushSync();
    expect(kapcsolo().getAttribute('aria-expanded')).toBe('true');
    await fireEvent.click(kapcsolo());
    csend.be = false; flushSync(); csend.be = true; flushSync();
    expect(kapcsolo().getAttribute('aria-expanded')).toBe('false');
    expect(screen.queryByRole('combobox', { name: 'Status' })).toBeNull();
    lathato(screen.getByRole('button', { name: 'Új tulajdonság' }));
    expect(f.alkalmaz).not.toHaveBeenCalled();
  });

  it('a betöltési hiba összecsukva is olvasható, ikon és alert szemantika kíséri', async () => {
    const f = fixture(false); f.api.elemez.mockRejectedValue(new ApiHiba(503, 'Synthetic analysis unavailable.')); f.felallit();
    const hiba = await screen.findByRole('alert');
    expect(hiba.textContent).toContain('Synthetic analysis unavailable.');
    expect(hiba.querySelector('svg[aria-hidden="true"]')).toBeTruthy();
    lathato(hiba);
    expect(kapcsolo().getAttribute('aria-expanded')).toBe('false');
    expect(f.alkalmaz).not.toHaveBeenCalled();
  });

  it('az elemzés hibája és az érvénytelen tárolt érték kulccsal együtt megmarad összecsukva', async () => {
    const f = fixture(false);
    f.api.elemez.mockResolvedValue({ van: true, hiba: null, osztaly: 'normal', kulcsok: ['Count'], problemak: [{ ...PROBLEMA, szint: 'hiba', kulcs: 'Count', uzenet: 'Count has an invalid stored value.' }], tulajdonsagok: [{ kulcs: 'Count', tipus: 'number', ertek: 'three', ervenyes: false }] });
    f.felallit();
    const hiba = await screen.findByRole('alert');
    expect(hiba.textContent).toContain('Count has an invalid stored value.'); lathato(hiba);
    const status = screen.getByRole('status');
    expect(status.textContent).toContain('Count:');
    expect(status.textContent).toContain('a forrásban megmaradt'); lathato(status);
    expect(f.szoveg()).toBe(FM); expect(f.alkalmaz).not.toHaveBeenCalled();
  });

  it('a függő megerősítés összecsukva sem tűnik el; csak explicit döntés után változik az egyetlen érték', async () => {
    const f = fixture(); f.felallit();
    await fireEvent.change(await screen.findByLabelText('Status'), { target: { value: 'Review' } });
    await screen.findByRole('button', { name: 'Mégis beírom' });
    expect(f.alkalmaz).not.toHaveBeenCalled(); expect(f.szoveg()).toBe(FM);
    await fireEvent.click(kapcsolo());
    const megerosit = screen.getByRole('button', { name: 'Mégis beírom' }); lathato(megerosit);
    expect(screen.getByRole('alert').textContent).toContain(PROBLEMA.uzenet);
    const uj = FM.replace('Status: Draft', 'Status: Review');
    f.api.modosit.mockResolvedValueOnce({ ok: true, fm_uj: uj.slice(0, uj.indexOf('---\n\n') + 4), megerositheto: false, valtozas: true, problemak: [] });
    await fireEvent.click(megerosit);
    await waitFor(() => expect(f.alkalmaz).toHaveBeenCalledTimes(1));
    expect(f.alkalmaz.mock.calls[0][0].insert).toBe('Review');
    expect(f.szoveg()).toBe(uj);
    expect(f.api.modosit).toHaveBeenNthCalledWith(2, 'Synthetic.md', expect.any(String), { muvelet: 'beallit', kulcs: 'Status', ertek: 'Review', tipus: 'text' }, true);
    expect(kapcsolo().getAttribute('aria-expanded')).toBe('false');
  });

  it('a közben írásvédetté vált panel nem enged megerősíteni, a Mégse továbbra is elveti a függő műveletet', async () => {
    const f = fixture(); const nezet = f.felallit();
    await fireEvent.change(await screen.findByLabelText('Status'), { target: { value: 'Review' } });
    await screen.findByRole('button', { name: 'Mégis beírom' });
    await fireEvent.click(kapcsolo()); await nezet.rerender({ irhato: false });
    const megerosit = screen.getByRole('button', { name: 'Mégis beírom' }) as HTMLButtonElement;
    expect(megerosit.disabled).toBe(true);
    await fireEvent.click(screen.getByRole('button', { name: 'Mégse' }));
    expect(screen.queryByRole('button', { name: 'Mégis beírom' })).toBeNull();
    expect(f.api.modosit).toHaveBeenCalledTimes(1); expect(f.alkalmaz).not.toHaveBeenCalled(); expect(f.szoveg()).toBe(FM);
  });

  it('a 409 típusütközés összecsukva is látszik és onnan frissíthető; automatikus POST-újrapróbálás nincs', async () => {
    const f = fixture(); f.felallit();
    await fireEvent.click(await screen.findByRole('button', { name: 'Count típusa: Szám' }));
    await screen.findByRole('combobox', { name: 'Tulajdonság típusa' });
    await fireEvent.change(screen.getByRole('combobox', { name: 'Tulajdonság típusa' }), { target: { value: 'text' } });
    await fireEvent.click(screen.getByRole('button', { name: 'Típus mentése' }));
    await screen.findByRole('alert'); await fireEvent.click(kapcsolo());
    const hiba = screen.getByRole('alert'); expect(hiba.textContent).toContain('Count:'); expect(hiba.textContent).toContain('közben megváltoztak'); lathato(hiba);
    const ujratolt = screen.getByRole('button', { name: 'Típusok újratöltése' }); lathato(ujratolt);
    await fireEvent.click(ujratolt); await waitFor(() => expect(f.api.tipusok).toHaveBeenCalledTimes(2));
    expect(screen.queryByRole('alert')).toBeNull();
    expect(f.api.tipusBeallit).toHaveBeenCalledTimes(1); expect(f.api.modosit).not.toHaveBeenCalled(); expect(f.alkalmaz).not.toHaveBeenCalled(); expect(f.szoveg()).toBe(FM);
  });
});
