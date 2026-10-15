// A ⌘O gyorsváltó és a ⌘P paletta billentyűzetről: nyit, gépel, ↑↓, Enter fut, Esc zár, a fókusz
// visszatér a megnyitóra, és az ARIA-szerkezet (combobox + listbox) helyes.
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/svelte';
import { flushSync } from 'svelte';
import { afterEach, describe, expect, it, vi } from 'vitest';
import Paletta from '../src/atfedes/Paletta.svelte';
import Valto from '../src/atfedes/Valto.svelte';
import { CoreKapcsolat } from '../src/lib/core/ws.svelte';
import { Felulet } from '../src/lib/elrendezes/felulet.svelte';
import { modalisNyitva } from '../src/lib/fokusz/hatokor';
import { KORNYEZET_KULCS } from '../src/lib/kornyezet';
import { regiszter } from '../src/lib/parancsok/regiszter';
import { VaultFajlok, type FajlInfo } from '../src/lib/vault/fajlok.svelte';

const FAJLOK: FajlInfo[] = [
  { ut: 'Matek/Sorozatok/04 - Mértani sorozat.md', tipus: 'md', meret: 3300, mtime: 100 },
  { ut: 'Matek/Sorozatok/03 - Számtani sorozat.md', tipus: 'md', meret: 2000, mtime: 300 },
  { ut: 'Matek/Geometria/Geometriai transzformációk.pdf', tipus: 'pdf', meret: 9e5, mtime: 200 },
  { ut: 'Napló/2026-10-01.md', tipus: 'md', meret: 100, mtime: 400 },
];

function kornyezet(allapot: unknown = {}) {
  const felulet = new Felulet(allapot);
  const fajlok = new VaultFajlok();
  fajlok.beallit(FAJLOK);
  const context = new Map<unknown, unknown>([[KORNYEZET_KULCS, { felulet, fajlok, kapcsolat: new CoreKapcsolat('ws://x') }]]);
  return { felulet, fajlok, context };
}

const opciok = () => screen.getAllByRole('option').map((o) => o.textContent?.replace(/\s+/g, ' ').trim());

afterEach(() => cleanup());

describe('gyorsváltó (⌘O)', () => {
  it('combobox + listbox, a fókusz a mezőben; üresen a legutóbbiak, aztán módosítás szerint', () => {
    const { context } = kornyezet({ legutobbiFajlok: ['Matek/Sorozatok/04 - Mértani sorozat.md'] });
    render(Valto, { context });
    const mezo = screen.getByRole('combobox', { name: 'Fájl keresése' });
    expect(document.activeElement).toBe(mezo);
    expect(mezo.getAttribute('aria-controls')).toBe(screen.getByRole('listbox').id);
    expect(screen.getByRole('dialog', { name: 'Gyorsváltó' }).getAttribute('aria-modal')).toBe('true');
    expect(opciok()[0]).toContain('04 - Mértani sorozat');
    expect(opciok()[1]).toContain('2026-10-01'); // a legfrissebb módosítás
    expect(modalisNyitva()).toBe(true);
  });

  it('ékezet nélkül, elírással is talál; ↑↓ és Enter megnyit az aktív fülben', async () => {
    const { felulet, context } = kornyezet();
    felulet.atfedes = 'valto';
    render(Valto, { context });
    const mezo = screen.getByRole('combobox');
    await fireEvent.input(mezo, { target: { value: 'mrtani' } });
    expect(opciok()[0]).toContain('04 - Mértani sorozat');
    const elso = screen.getAllByRole('option')[0];
    expect(elso.getAttribute('aria-selected')).toBe('true');
    expect(mezo.getAttribute('aria-activedescendant')).toBe(elso.id);
    await fireEvent.input(mezo, { target: { value: 'sorozat' } });
    await fireEvent.keyDown(mezo, { key: 'ArrowDown' });
    const masodik = screen.getAllByRole('option')[1];
    expect(masodik.getAttribute('aria-selected')).toBe('true');
    const cel = masodik.textContent ?? '';
    await fireEvent.keyDown(mezo, { key: 'Enter' });
    expect(felulet.atfedes).toBeNull();
    expect(cel).toContain(felulet.munkaterulet.aktivFul?.ut?.split('/').pop()?.replace('.md', ''));
    expect(felulet.legutobbiFajlok[0]).toBe(felulet.munkaterulet.aktivFul?.ut);
  });

  it('⌘Enter új fülben, ⌥⌘Enter osztásban nyit', async () => {
    const { felulet, context } = kornyezet();
    felulet.munkaterulet.megnyit('Napló/2026-10-01.md');
    render(Valto, { context });
    const mezo = screen.getByRole('combobox');
    await fireEvent.input(mezo, { target: { value: 'mertani' } });
    await fireEvent.keyDown(mezo, { key: 'Enter', metaKey: true });
    expect(felulet.munkaterulet.aktivPanel.fulek.map((f) => f.ut)).toEqual([
      'Napló/2026-10-01.md',
      'Matek/Sorozatok/04 - Mértani sorozat.md',
    ]);
    cleanup();
    render(Valto, { context });
    const mezo2 = screen.getByRole('combobox');
    await fireEvent.input(mezo2, { target: { value: 'szamtani' } });
    await fireEvent.keyDown(mezo2, { key: 'Enter', metaKey: true, altKey: true });
    expect(felulet.munkaterulet.panelek()).toHaveLength(2);
    expect(felulet.munkaterulet.aktivFul?.ut).toBe('Matek/Sorozatok/03 - Számtani sorozat.md');
  });

  it('nincs találat: élő régió szól; Esc zár, és a fókusz visszatér a megnyitóra', async () => {
    const nyito = document.createElement('button');
    document.body.append(nyito);
    nyito.focus();
    const { felulet, context } = kornyezet();
    felulet.atfedes = 'valto';
    const { unmount } = render(Valto, { context });
    const mezo = screen.getByRole('combobox');
    await fireEvent.input(mezo, { target: { value: 'qqqzzz' } });
    expect(screen.getByRole('status').textContent).toContain('Nincs találat');
    await fireEvent.keyDown(mezo, { key: 'Escape' });
    expect(felulet.atfedes).toBeNull();
    unmount();
    flushSync();
    await waitFor(() => expect(document.activeElement).toBe(nyito));
    expect(modalisNyitva()).toBe(false);
    nyito.remove();
  });
});

describe('parancspaletta (⌘P)', () => {
  it('a regiszter parancsai, gyorsbillentyűvel; a választott parancs a bezárás után fut', async () => {
    const futott = vi.fn();
    const le = regiszter.regisztral({ id: 'proba.mertani', nev: 'Mértani próba', kategoria: 'Próba', billentyu: 'Mod+Shift+9', futtat: futott });
    const le2 = regiszter.regisztral({ id: 'proba.rejtett', nev: 'Rejtett', palettaban: false, futtat: () => {} });
    try {
      const { felulet, context } = kornyezet();
      felulet.atfedes = 'paletta';
      render(Paletta, { context });
      expect(opciok().some((o) => o?.includes('Rejtett'))).toBe(false);
      const mezo = screen.getByRole('combobox', { name: 'Parancs keresése' });
      await fireEvent.input(mezo, { target: { value: 'mertni proba' } });
      expect(opciok()[0]).toContain('Mértani próba');
      expect(screen.getAllByRole('option')[0].querySelector('kbd')?.textContent).toBe('⇧⌘9');
      await fireEvent.keyDown(mezo, { key: 'Enter' });
      expect(felulet.atfedes).toBeNull();
      await waitFor(() => expect(futott).toHaveBeenCalledOnce());
    } finally {
      le();
      le2();
    }
  });

  it('a megnyitó fókuszát kívánó parancs (pl. Félkövér) fut: a fókusz a futtatás előtt visszakerül', async () => {
    const szerkeszto = document.createElement('textarea');
    document.body.append(szerkeszto);
    szerkeszto.focus();
    const futott = vi.fn();
    const le = regiszter.regisztral({
      id: 'proba.fokuszos',
      nev: 'Fókuszos próba',
      elerheto: () => document.activeElement === szerkeszto,
      futtat: futott,
    });
    try {
      const { felulet, context } = kornyezet();
      felulet.atfedes = 'paletta';
      render(Paletta, { context });
      const mezo = screen.getByRole('combobox', { name: 'Parancs keresése' });
      expect(document.activeElement).toBe(mezo);
      await fireEvent.input(mezo, { target: { value: 'fokuszos proba' } });
      expect(opciok()[0]).toContain('Fókuszos próba');
      await fireEvent.keyDown(mezo, { key: 'Enter' });
      await waitFor(() => expect(futott).toHaveBeenCalledOnce());
      expect(document.activeElement).toBe(szerkeszto);
    } finally {
      le();
      szerkeszto.remove();
    }
  });

  it('üresen a legutóbb futtatott parancs áll elöl', () => {
    const le = regiszter.regisztral({ id: 'proba.zzz', nev: 'Zzz utolsó betű', kategoria: 'Zzz', futtat: () => {} });
    try {
      const { context } = kornyezet({ legutobbiParancsok: ['proba.zzz'] });
      render(Paletta, { context });
      expect(opciok()[0]).toContain('Zzz utolsó betű');
    } finally {
      le();
    }
  });
});
