// A „leáll” réteg (C29.7b, T121): kilépésre várás alatt a felület NEM szerkeszthető (a mentés után begépelt szöveg elveszne),
// az ok látszik, és a „Kényszerített kilépés” a héjnak szól. A mögötte lévő felület `inert` (minden szerkesztő egységesen).

import { cleanup, render, screen } from '@testing-library/svelte';
import { createRawSnippet, tick } from 'svelte';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { leall } from '../src/lib/core/leall.svelte';
import LeallVedelem from '../src/hej/LeallVedelem.svelte';

const tartalom = createRawSnippet(() => ({ render: () => '<div id="munka"><button>Szerkesztés</button></div>' }));

let uzenetek: unknown[];
beforeEach(() => {
  leall.ki();
  uzenetek = [];
  (window as unknown as { webkit: unknown }).webkit = { messageHandlers: { manifold: { postMessage: (u: unknown) => uzenetek.push(u) } } };
});
afterEach(() => {
  cleanup();
  leall.ki();
  delete (window as unknown as { webkit?: unknown }).webkit;
  vi.restoreAllMocks();
});

describe('LeallVedelem', () => {
  it('alapból semmi nem inert és nincs jelző', () => {
    const { container } = render(LeallVedelem, { props: { children: tartalom } });
    expect(container.querySelector('[inert]')).toBeNull();
    expect(screen.queryByRole('alertdialog')).toBeNull();
    expect(screen.getByText('Szerkesztés')).toBeTruthy();
  });

  it('leáll állapotban a munkafelület inert, a jelző látszik a szöveggel, a fókusz a gombján áll', async () => {
    const { container } = render(LeallVedelem, { props: { children: tartalom } });
    leall.be('Mentés a kilépés előtt…');
    await tick();
    const inert = container.querySelector('[inert]');
    expect(inert).not.toBeNull();
    expect(inert!.querySelector('#munka')).not.toBeNull();
    const jelzo = screen.getByRole('alertdialog');
    expect(jelzo.textContent).toContain('A Manifold leáll');
    expect(jelzo.textContent).toContain('Mentés a kilépés előtt…');
    expect(inert!.contains(jelzo)).toBe(false);
    expect(document.activeElement).toBe(screen.getByRole('button', { name: 'Kényszerített kilépés' }));
  });

  it('a szöveg élőben frissül, a visszavonás (ki) mindent visszaad', async () => {
    const { container } = render(LeallVedelem, { props: { children: tartalom } });
    leall.be('Mentés…');
    await tick();
    leall.be('Leállítás a futó feladat végén…');
    await tick();
    expect(screen.getByRole('alertdialog').textContent).toContain('Leállítás a futó feladat végén…');
    leall.ki();
    await tick();
    expect(container.querySelector('[inert]')).toBeNull();
    expect(screen.queryByRole('alertdialog')).toBeNull();
  });

  it('a „Kényszerített kilépés” a héjnak szól', async () => {
    render(LeallVedelem, { props: { children: tartalom } });
    leall.be('Mentés…');
    await tick();
    screen.getByRole('button', { name: 'Kényszerített kilépés' }).click();
    expect(uzenetek).toEqual([{ tipus: 'kenyszeritett-kilepes' }]);
  });
});
