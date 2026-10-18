// Recovery must preview literal, read-only text and never let a stale response describe another file.
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/svelte';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const api = vi.hoisted(() => ({ kerdez: vi.fn() }));
vi.mock('../src/lib/core/api', async (eredeti) => ({ ...(await eredeti<typeof import('../src/lib/core/api')>()), kerdez: api.kerdez }));

import ToroltVisszahozas from '../src/atfedes/ToroltVisszahozas.svelte';
import { ApiHiba } from '../src/lib/core/api';
import { Felulet } from '../src/lib/elrendezes/felulet.svelte';
import { ertesitesek } from '../src/lib/ertesites/ertesites.svelte';
import { nyelv } from '../src/lib/i18n';
import { KORNYEZET_KULCS } from '../src/lib/kornyezet';

const SHA = 'a'.repeat(40);
const ELEMEK = ['Old.md', 'Other.md'].map((ut) => ({ ut, sha: SHA, datum: '2026-10-01T12:00:00Z', targy: '', tipus: 'kezi', cimke: '', ut_van: false }));
const szoveg = (ut: string, tartalom: string) => ({ sha: SHA, ut_akkor: ut, szoveg: tartalom, szoveg_ok: null, elozo: null, elozo_ok: null });

function nyit() {
  const felulet = new Felulet({ atfedes: 'torolt', csend: { be: false } });
  felulet.atfedes = 'torolt';
  render(ToroltVisszahozas, { context: new Map([[KORNYEZET_KULCS, { felulet }]]) });
  return felulet;
}

async function valaszt(nev = 'Old') {
  await fireEvent.click(await screen.findByRole('option', { name: new RegExp(nev) }));
}

beforeEach(() => {
  nyelv.beallit('en');
  api.kerdez.mockImplementation(async (ut: string) => {
    if (ut.startsWith('/api/vault/elozmeny/torolt/valtozat')) return szoveg('Old.md', '<script>unsafe()</script>\n# Original');
    if (ut.startsWith('/api/vault/elozmeny/torolt?')) return { torolt: ELEMEK, lap: 100, lap_max: 100 };
    throw new Error('Unexpected request: ' + ut);
  });
});

afterEach(() => {
  cleanup();
  api.kerdez.mockReset();
  ertesitesek.mindElvet();
  nyelv.beallit('hu');
});

describe('S0 deleted-note recovery', () => {
  it('provides keyboard-accessible literal read-only text without executing or saving it', async () => {
    nyit();
    await valaszt();
    const mezo = screen.getByRole('textbox', { name: 'Text before deletion' }) as HTMLTextAreaElement;
    await waitFor(() => expect(mezo.value).toBe('<script>unsafe()</script>\n# Original'));
    expect(mezo.readOnly).toBe(true);
    mezo.focus();
    expect(document.activeElement).toBe(mezo);
    expect(document.querySelector('script')).toBeNull();
    expect(api.kerdez.mock.calls.every(([, o]) => !o?.metodus || o.metodus === 'GET')).toBe(true);
  });

  it('keeps the dialog open after a restore collision and retries under a new name', async () => {
    const felulet = nyit();
    const megnyit = vi.spyOn(felulet.munkaterulet, 'megnyit');
    let probak = 0;
    const alap = api.kerdez.getMockImplementation()!;
    api.kerdez.mockImplementation(async (ut, o) => {
      if (ut !== '/api/vault/elozmeny/visszahoz') return alap(ut, o);
      if (++probak === 1) throw new ApiHiba(409, 'A file already exists.', { kod: 'elozmeny.visszahoz_utkozes' });
      return { ok: true, ut: 'Recovered.md', sha: 'b'.repeat(40) };
    });
    await valaszt();
    await waitFor(() => expect((screen.getByRole('button', { name: 'Recover to the original location' }) as HTMLButtonElement).disabled).toBe(false));
    await fireEvent.click(screen.getByRole('button', { name: 'Recover to the original location' }));
    expect((await screen.findByRole('alert')).textContent?.trim()).toBe('A file already exists.');
    expect((screen.getByRole('button', { name: 'Recover to the original location' }) as HTMLButtonElement).disabled).toBe(true);
    expect(megnyit).not.toHaveBeenCalled();
    await fireEvent.input(screen.getByRole('textbox', { name: 'New name' }), { target: { value: 'Recovered' } });
    await fireEvent.click(screen.getByRole('button', { name: 'Recover under a new name' }));
    await waitFor(() => expect(megnyit).toHaveBeenCalledWith('Recovered.md', 'ujful'));
    expect(api.kerdez.mock.calls.filter(([ut]) => ut === '/api/vault/elozmeny/visszahoz').map(([, o]) => o.torzs)).toEqual([
      { ut: 'Old.md', sha: SHA, mod: 'eredeti' },
      { ut: 'Old.md', sha: SHA, mod: 'uj', nev: 'Recovered.md' },
    ]);
    expect(felulet.atfedes).toBeNull();
    expect(ertesitesek.lista.at(-1)?.muvelet?.nev).toBe('Undo');
  });

  it('ignores an earlier preview after another deleted note is selected', async () => {
    let elozoKesz!: (v: ReturnType<typeof szoveg>) => void;
    const elozo = new Promise<ReturnType<typeof szoveg>>((kesz) => { elozoKesz = kesz; });
    const alap = api.kerdez.getMockImplementation()!;
    api.kerdez.mockImplementation(async (ut, o) => {
      if (ut.includes('/torolt/valtozat?ut=Old.md')) return elozo;
      if (ut.includes('/torolt/valtozat?ut=Other.md')) return szoveg('Other.md', 'Second note');
      return alap(ut, o);
    });
    nyit();
    await valaszt('Old');
    await fireEvent.click(screen.getByRole('button', { name: 'Back to list' }));
    await valaszt('Other');
    const mezo = screen.getByRole('textbox', { name: 'Text before deletion' }) as HTMLTextAreaElement;
    await waitFor(() => expect(mezo.value).toBe('Second note'));
    elozoKesz(szoveg('Old.md', 'Stale first note'));
    await Promise.resolve();
    await Promise.resolve();
    expect(mezo.value).toBe('Second note');
  });

  it.each(['siker', 'hiba'])('a late recovery result (%s) does not close a different overlay or navigate', async (eredmeny) => {
    let kesz!: (v: unknown) => void;
    let elutasit!: (e: Error) => void;
    const fuggo = new Promise((resolve, reject) => { kesz = resolve; elutasit = reject; });
    const alap = api.kerdez.getMockImplementation()!;
    api.kerdez.mockImplementation((ut, o) => ut === '/api/vault/elozmeny/visszahoz' ? fuggo : alap(ut, o));
    const felulet = nyit();
    const megnyit = vi.spyOn(felulet.munkaterulet, 'megnyit');
    await valaszt();
    const gomb = screen.getByRole('button', { name: 'Recover to the original location' }) as HTMLButtonElement;
    await waitFor(() => expect(gomb.disabled).toBe(false));
    await fireEvent.click(gomb);
    felulet.atfedes = 'paletta';
    if (eredmeny === 'siker') kesz({ ok: true, ut: 'Old.md', sha: 'b'.repeat(40) });
    else elutasit(new Error('Recovery failed'));
    await waitFor(() => expect(ertesitesek.lista.at(-1)?.szint).toBe(eredmeny));
    expect(felulet.atfedes).toBe('paletta');
    expect(megnyit).not.toHaveBeenCalled();
    if (eredmeny === 'hiba') expect(ertesitesek.lista.at(-1)?.idotartam).toBe(0);
  });
});
