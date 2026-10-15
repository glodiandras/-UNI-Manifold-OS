// A Rendszer szakasz adata (C17): memória, modellzár, betöltött modell, SSD, utolsó mentés. A core-lekérdezés olcsó
// (modellt nem tölt, workert nem indít), de nyugalomban sem kérdezünk: csak amíg a lap nyitva és az ablak látszik.

import { ApiHiba } from '../core/api';
import { vezerloApi } from './api';
import type { Rendszer } from './tipusok';

export const FRISSITES_MS = 5000;

export class RendszerAllapot {
  adat = $state.raw<Rendszer | null>(null);
  hiba = $state<string | null>(null);
  private idozito: ReturnType<typeof setInterval> | null = null;
  private sorszam = 0;

  async frissit(): Promise<void> {
    const s = ++this.sorszam;
    try {
      const d = await vezerloApi.rendszer();
      if (s !== this.sorszam) return;
      this.adat = d;
      this.hiba = null;
    } catch (e) {
      if (s === this.sorszam) this.hiba = e instanceof ApiHiba ? e.message : String(e);
    }
  }

  /** Időzített frissítés: azonnal egyszer, utána `FRISSITES_MS`-onként, de csak látszó ablakban. */
  indit(): () => void {
    void this.frissit();
    this.leallit();
    this.idozito = setInterval(() => {
      if (document.visibilityState === 'visible') void this.frissit();
    }, FRISSITES_MS);
    const lathato = () => document.visibilityState === 'visible' && void this.frissit();
    document.addEventListener('visibilitychange', lathato);
    return () => {
      document.removeEventListener('visibilitychange', lathato);
      this.leallit();
    };
  }

  private leallit(): void {
    if (this.idozito) clearInterval(this.idozito);
    this.idozito = null;
  }
}

export const rendszerAllapot = new RendszerAllapot();
