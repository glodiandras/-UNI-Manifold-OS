// A jegyzet jobb alsó sarkának mentés-jelzése (E12): az állapotgép, és a Dokumentum állapotaival együtt.

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { ChangeSet } from '@codemirror/state';
import type { FajlIras, FajlIrasKeres, FajlOlvasas, VaultApi } from '../src/szerkeszto/dokumentum/api';
import { Dokumentum, MENTES_KESLELTETES, type Csatolt } from '../src/szerkeszto/dokumentum/dokumentum.svelte';
import { ERES_MS, LASSU_MS, mentesJelzes } from '../src/szerkeszto/dokumentum/mentesJelzes';

describe('a „Mentve” állapotgép', () => {
  it('megnyitás után (nincs még mentés) semmi', () => {
    expect(mentesJelzes('tiszta', null, 1000).fajta).toBe('nincs');
  });

  it('gépelés közben (piszkos) halvány pont, szöveg nélkül', () => {
    const j = mentesJelzes('piszkos', null, 0);
    expect(j).toMatchObject({ fajta: 'pont', szoveg: '' });
    expect(j.cimke).not.toBe('');
  });

  it('a gyors mentés nem villog: pont marad; a lassú mentés „Mentés…”', () => {
    expect(mentesJelzes('mentes', null, 1000, 900).fajta).toBe('pont');
    expect(mentesJelzes('mentes', null, 900 + LASSU_MS, 900)).toMatchObject({ fajta: 'mentes', szoveg: 'Mentés…' });
    expect(mentesJelzes('mentes', null, 1000, null).fajta).toBe('pont');
  });

  it('a mentés után ERES_MS-ig erős „Mentve”, utána halvány „Mentve”', () => {
    expect(mentesJelzes('tiszta', 5000, 5000 + ERES_MS - 1)).toMatchObject({ fajta: 'mentve-eros', szoveg: 'Mentve' });
    expect(mentesJelzes('tiszta', 5000, 5000 + ERES_MS)).toMatchObject({ fajta: 'mentve', szoveg: 'Mentve' });
  });

  it('hiba, ütközés, eltűnt, betöltés: itt semmi (a fejléc soha nem rejtett jele áll)', () => {
    for (const a of ['hiba', 'utkozes', 'eltunt', 'betoltes'] as const) expect(mentesJelzes(a, 5000, 5001).fajta).toBe('nincs');
  });
});

describe('a Dokumentum állapotaival', () => {
  class AlCore implements VaultApi {
    lemez = 'abc';
    async olvas(ut: string): Promise<FajlOlvasas> {
      return { ut, tartalom: this.lemez, hash: 'h:' + this.lemez, jel: '', mtime: 0 };
    }
    async ir(k: FajlIrasKeres): Promise<FajlIras> {
      this.lemez = k.tartalom;
      return { ok: true, ut: k.ut, hash: 'h:' + k.tartalom, jel: '', uzenet: 'mentve', pillanat: null, elotte: null, git: true };
    }
  }
  beforeEach(() => vi.useFakeTimers());
  afterEach(() => vi.useRealTimers());

  it('gépelés → pont → mentés → erős „Mentve” → halvány „Mentve”', async () => {
    const core = new AlCore();
    const d = new Dokumentum(core, await core.olvas('a.md'));
    const nezet: Csatolt = { alkalmaz() {} };
    d.csatol(nezet);
    expect(mentesJelzes(d.allapot, d.utolsoMentes?.ido ?? null, Date.now()).fajta).toBe('nincs');
    const cs = ChangeSet.of([{ from: 0, insert: 'x' }], d.szoveg.length);
    d.valtozott(cs, cs.apply(d.szoveg), nezet);
    expect(mentesJelzes(d.allapot, d.utolsoMentes?.ido ?? null, Date.now()).fajta).toBe('pont');
    await vi.advanceTimersByTimeAsync(MENTES_KESLELTETES + 50);
    expect(d.allapot).toBe('tiszta');
    expect(mentesJelzes(d.allapot, d.utolsoMentes?.ido ?? null, Date.now()).fajta).toBe('mentve-eros');
    await vi.advanceTimersByTimeAsync(ERES_MS + 50);
    expect(mentesJelzes(d.allapot, d.utolsoMentes?.ido ?? null, Date.now()).fajta).toBe('mentve');
  });
});
