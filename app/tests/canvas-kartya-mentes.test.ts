// A canvas nyitott szövegkártyájának szerkesztése (E12): gépelés közben átkerül a dokumentumba (az automatikus mentés is
// látja), és a core-halál utáni mentetlen-lista, illetve a kilépési ellenőrzés is számol vele.

import { ChangeSet } from '@codemirror/state';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { CanvasForras, KARTYA_ATVETEL_MS } from '../src/canvas/forras';
import { kilepesMentes, mentetlenSzovegek } from '../src/szerkeszto';
import type { FajlIras, FajlIrasKeres, FajlOlvasas, VaultApi } from '../src/szerkeszto/dokumentum/api';
import { Dokumentumok, MENTES_KESLELTETES } from '../src/szerkeszto/dokumentum/dokumentum.svelte';

class AlCore implements VaultApi {
  lemez = '{}';
  async olvas(ut: string): Promise<FajlOlvasas> {
    return { ut, tartalom: this.lemez, hash: 'h:' + this.lemez, jel: '', mtime: 0 };
  }
  async ir(k: FajlIrasKeres): Promise<FajlIras> {
    this.lemez = k.tartalom;
    return { ok: true, ut: k.ut, hash: 'h:' + k.tartalom, jel: '', uzenet: 'mentve', pillanat: null, elotte: null, git: true };
  }
}

describe('a nyitott canvas-kártya szövege a mentésben', () => {
  let core: AlCore;
  let dk: Dokumentumok;
  let forras: CanvasForras;
  /** a nézet szimulált nyitott szerkesztője: a „gépelt” szöveg, amely még nincs a dokumentumban */
  let gepelt: string;
  let atadasok: number;

  beforeEach(async () => {
    vi.useFakeTimers();
    core = new AlCore();
    dk = new Dokumentumok(core);
    forras = await CanvasForras.nyit('t.canvas', dk);
    gepelt = '';
    atadasok = 0;
    forras.fuggoBeallit(() => {
      atadasok++;
      if (!gepelt) return;
      const d = forras.dok;
      const cs = ChangeSet.of([{ from: 0, to: d.szoveg.length, insert: gepelt }], d.szoveg.length);
      if (d.szoveg.toString() !== gepelt) d.valtozott(cs, cs.apply(d.szoveg), null);
    });
    forras.kartyaSzerkesztes(true);
  });
  afterEach(() => vi.useRealTimers());

  it('gépelés után KARTYA_ATVETEL_MS csenddel átkerül a dokumentumba, és az automatikus mentés lemezre írja', async () => {
    gepelt = '{"nodes":[]}';
    forras.kartyaValtozott();
    await vi.advanceTimersByTimeAsync(KARTYA_ATVETEL_MS - 10);
    expect(atadasok).toBe(0);
    await vi.advanceTimersByTimeAsync(20);
    expect(atadasok).toBe(1);
    expect(forras.dok.piszkos).toBe(true);
    await vi.advanceTimersByTimeAsync(MENTES_KESLELTETES + 50);
    expect(core.lemez).toBe('{"nodes":[]}');
  });

  it('folyamatos gépelésnél az átvétel a csend végén jön (nem minden billentyűre)', async () => {
    for (let i = 0; i < 5; i++) {
      forras.kartyaValtozott();
      await vi.advanceTimersByTimeAsync(KARTYA_ATVETEL_MS - 50);
    }
    expect(atadasok).toBe(0);
    await vi.advanceTimersByTimeAsync(100);
    expect(atadasok).toBe(1);
  });

  it('a core-halál utáni mentetlen-lista a még át nem adott kártyaszöveget is tartalmazza', () => {
    gepelt = '{"nodes":[{"id":"a"}]}';
    const lista = mentetlenSzovegek(dk);
    expect(lista).toHaveLength(1);
    expect(lista[0]).toMatchObject({ ut: 't.canvas', szoveg: '{"nodes":[{"id":"a"}]}' });
  });

  it('a kilépési mentés lemezre írja a még át nem adott kártyaszöveget, és a jelentés rendben van', async () => {
    gepelt = '{"nodes":[{"id":"b"}]}';
    const p = kilepesMentes(dk);
    await vi.advanceTimersByTimeAsync(100);
    const j = await p;
    expect(core.lemez).toBe('{"nodes":[{"id":"b"}]}');
    expect(j.ok).toBe(true);
  });

  it('a kártya bezárása (kartyaSzerkesztes(false)) törli a függő átvételt', async () => {
    gepelt = '{"x":1}';
    forras.kartyaValtozott();
    forras.kartyaSzerkesztes(false);
    await vi.advanceTimersByTimeAsync(KARTYA_ATVETEL_MS + 50);
    expect(atadasok).toBe(0);
  });
});
