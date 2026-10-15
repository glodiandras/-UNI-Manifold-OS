// A WS-kliens (`CoreKapcsolat`) viselkedése kiesésnél (C29.7b, T107): az újracsatlakozás visszalépéses, és a core `kimaradt`
// jelzése (túlcsordult feliratkozói sor: események vesztek el) „bármi változhatott” eseménnyé válik, amelyre a meglévő
// fogyasztók (fájlfa, linkek, Bases, gráf, szerkesztő) maguktól újraolvasnak. `WebSocket`-csonkkal és fake timerekkel.

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { CoreKapcsolat, type CoreEsemeny } from '../src/lib/core/ws.svelte';

class AlWs {
  static OPEN = 1;
  static peldanyok: AlWs[] = [];
  readyState = 0;
  onopen: (() => void) | null = null;
  onmessage: ((m: { data: string }) => void) | null = null;
  onclose: (() => void) | null = null;
  kuldottek: string[] = [];
  constructor(readonly url: string) {
    AlWs.peldanyok.push(this);
  }
  send(s: string) {
    this.kuldottek.push(s);
  }
  close() {
    this.onclose?.();
  }
  nyit() {
    this.readyState = 1;
    this.onopen?.();
  }
  kap(e: CoreEsemeny) {
    this.onmessage?.({ data: JSON.stringify(e) });
  }
}

beforeEach(() => {
  vi.useFakeTimers();
  AlWs.peldanyok = [];
  vi.stubGlobal('WebSocket', AlWs);
});
afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

describe('kimaradt', () => {
  it('a `kimaradt` esemény megy, és vele egy szintetikus tömeges `vault_valtozas` is', () => {
    const k = new CoreKapcsolat('ws://x/ws');
    const kapott: CoreEsemeny[] = [];
    k.figyel('kimaradt', (e) => kapott.push(e));
    k.figyel('vault_valtozas', (e) => kapott.push(e));
    k.indit();
    const ws = AlWs.peldanyok[0];
    ws.nyit();
    ws.kap({ tipus: 'kimaradt', db: 7 });
    expect(kapott.map((e) => e.tipus)).toEqual(['kimaradt', 'vault_valtozas']);
    expect(kapott[0].db).toBe(7);
    expect(kapott[1]).toMatchObject({ tomeges: true, utak: [], torolt: [], kulso: [] });
    k.leallit();
  });

  it('a közönséges események nem váltanak ki szintetikus eseményt', () => {
    const k = new CoreKapcsolat('ws://x/ws');
    const kapott: string[] = [];
    k.figyel('*', (e) => kapott.push(e.tipus));
    k.indit();
    AlWs.peldanyok[0].nyit();
    AlWs.peldanyok[0].kap({ tipus: 'vault_iras' });
    expect(kapott).toEqual(['vault_iras']);
    k.leallit();
  });
});

describe('újracsatlakozás', () => {
  it('a kiesés után 0,5 s-ot vár, majd újra kapcsolódik; a visszalépés 5 s-ig duplázódik', async () => {
    const k = new CoreKapcsolat('ws://x/ws');
    k.indit();
    AlWs.peldanyok[0].nyit();
    expect(k.allapot).toBe('el');
    AlWs.peldanyok[0].close(); // kiesés
    expect(k.allapot).toBe('megszakadt');
    await vi.advanceTimersByTimeAsync(499);
    expect(AlWs.peldanyok).toHaveLength(1);
    await vi.advanceTimersByTimeAsync(2);
    expect(AlWs.peldanyok).toHaveLength(2);
    AlWs.peldanyok[1].close(); // a második próbálkozás sem nyílt meg: 1 s
    await vi.advanceTimersByTimeAsync(999);
    expect(AlWs.peldanyok).toHaveLength(2);
    await vi.advanceTimersByTimeAsync(2);
    expect(AlWs.peldanyok).toHaveLength(3);
    AlWs.peldanyok[2].nyit();
    expect(k.allapot).toBe('el');
    k.leallit();
  });
});
