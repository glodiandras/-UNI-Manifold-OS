import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/svelte';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { flushSync } from 'svelte';
import Fa from '../src/hej/Fa.svelte';
import { beallitasok } from '../src/lib/beallitasok/allapot.svelte';
import { alapBeallitasok } from '../src/lib/beallitasok/tipusok';
import { CoreKapcsolat } from '../src/lib/core/ws.svelte';
import { Felulet } from '../src/lib/elrendezes/felulet.svelte';
import { KORNYEZET_KULCS } from '../src/lib/kornyezet';
import { VaultFajlok } from '../src/lib/vault/fajlok.svelte';

const json = (adat: unknown, status = 200) => new Response(JSON.stringify(adat), { status, headers: { 'Content-Type': 'application/json' } });
let kerelmek: Record<string, unknown>[];
let utkozes: boolean;
beforeEach(() => {
  kerelmek = []; utkozes = false;
  beallitasok.fogad({ verzio: 1, rev: 'synthetic', ertek: alapBeallitasok(), munkater: { id: 'synthetic', nev: 'Synthetic', vault: '/synthetic' }, setup_szukseges: false, ujrainditas: [] });
  vi.stubGlobal('fetch', async (url: string, o?: { body?: string }) => {
    if (url === '/api/vault/uj') {
      const torzs = JSON.parse(o?.body ?? '{}'); kerelmek.push(torzs);
      if (utkozes) return json({ hiba: 'Synthetic name conflict' }, 400);
      return json({ ut: [torzs.mappa, torzs.nev + '.md'].filter(Boolean).join('/'), kurzor: 4 });
    }
    return json({});
  });
});
afterEach(() => { cleanup(); document.body.textContent = ''; beallitasok.adat = null; vi.restoreAllMocks(); vi.unstubAllGlobals(); });
function nyit() {
  const felulet = new Felulet(), fajlok = new VaultFajlok();
  fajlok.beallit([{ ut: 'Current/Note.md', tipus: 'md', meret: 1, mtime: 1 }]);
  felulet.munkaterulet.megnyit('Current/Note.md');
  const context = new Map([[KORNYEZET_KULCS, { felulet, fajlok, kapcsolat: new CoreKapcsolat('ws://x') }]]);
  render(Fa, { context }); return felulet;
}

describe('F11 gyorsváltó → fájlfa létrehozás', () => {
  it('megvárja a bezáruló átfedést és az explicit mappába hoz létre, a kért osztásban', async () => {
    beallitasok.ertek.fajlok.uj_mappa = 'Default';
    const f = nyit();
    const fatyol = document.createElement('div'); fatyol.className = 'fatyol'; document.body.append(fatyol);
    f.faUjNev = { nev: 'From switcher', mappa: 'Explicit/New folder', mod: 'osztas' }; f.faUjJegyzet = true; flushSync();
    await new Promise(r => setTimeout(r, 40)); expect(kerelmek).toEqual([]);
    fatyol.remove();
    await waitFor(() => expect(kerelmek).toEqual([{ nev: 'From switcher', mappa: 'Explicit/New folder', mappa_keszit: true }]));
    await waitFor(() => expect(f.munkaterulet.aktivFul?.ut).toBe('Explicit/New folder/From switcher.md'));
    expect(f.munkaterulet.panelek()).toHaveLength(2);
    expect(f.faUjNev).toBe(null); expect(f.faUjJegyzet).toBe(false);
  });

  it('az alapértelmezett helyet tiszteli, a névütközésnél a név és hiba megmarad blur után is', async () => {
    beallitasok.ertek.fajlok.uj_mappa = '.'; utkozes = true;
    const f = nyit();
    f.faUjNev = { nev: 'Taken', mod: 'ujful' }; f.faUjJegyzet = true;
    await waitFor(() => expect(kerelmek).toEqual([{ nev: 'Taken', mappa: 'Current', mappa_keszit: true }]));
    const mezo = await screen.findByRole('textbox', { name: 'Az új jegyzet neve' });
    await fireEvent.blur(mezo);
    expect((mezo as HTMLInputElement).value).toBe('Taken');
    expect(screen.getByRole('alert').textContent).toContain('Synthetic name conflict');
    expect(f.munkaterulet.aktivFul?.ut).toBe('Current/Note.md');
    utkozes = false;
    await fireEvent.input(mezo, { target: { value: 'Available' } }); await fireEvent.keyDown(mezo, { key: 'Enter' });
    await waitFor(() => expect(f.munkaterulet.aktivFul?.ut).toBe('Current/Available.md'));
    expect(f.munkaterulet.aktivPanel.fulek).toHaveLength(2);
    expect(kerelmek).toHaveLength(2);
  });

  it('a sima Cmd+N kérés csak a névmezőt nyitja; üres név nem ír fájlt', async () => {
    beallitasok.ertek.fajlok.uj_mappa = 'Default';
    const f = nyit(); f.faUjJegyzet = true;
    const mezo = await screen.findByRole('textbox', { name: 'Az új jegyzet neve' });
    expect(kerelmek).toEqual([]);
    await fireEvent.keyDown(mezo, { key: 'Escape' }); expect(kerelmek).toEqual([]);
  });
});
