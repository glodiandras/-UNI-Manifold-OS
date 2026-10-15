// A feladatsor élő nézetének adata (C17): a core `/api/feladatok` listája, amelyet a WS `feladat` eseménye frissít
// (a core a haladást másodpercenként legfeljebb négyszer küldi). Innen számolódik a jelenlét-pont is.
// Nyugalomban semmi nem ütemez: a lista csak betöltéskor és eseményre változik.

import { ApiHiba } from '../core/api';
import type { CoreKapcsolat } from '../core/ws.svelte';
import { vezerloApi } from './api';
import { LEZART, type Feladat } from './tipusok';

const MAX = 40;

export class Feladatsor {
  lista = $state.raw<Feladat[]>([]);
  betoltve = $state(false);
  hiba = $state<string | null>(null);
  readonly futo = $derived(this.lista.filter((f) => f.allapot === 'fut'));
  readonly sorban = $derived(this.lista.filter((f) => f.allapot === 'sorban'));
  readonly legutobbi = $derived(this.lista.filter((f) => LEZART.has(f.allapot)));
  /** Fut-e feladat: a Manifold gomb melletti halvány pont. */
  readonly aktiv = $derived(this.futo.length > 0);

  async betolt(): Promise<void> {
    try {
      const d = await vezerloApi.feladatok();
      this.lista = d.feladatok;
      this.hiba = null;
    } catch (e) {
      this.hiba = e instanceof ApiHiba ? e.message : String(e);
    } finally {
      this.betoltve = true;
    }
  }

  kap(id: string): Feladat | undefined {
    return this.lista.find((f) => f.id === id);
  }

  /** Egy feladat új állapota (WS-esemény vagy a leállítás válasza): a helyén frissül, az új legelöl áll. */
  upsert(f: Feladat): void {
    const i = this.lista.findIndex((x) => x.id === f.id);
    if (i >= 0) {
      const uj = this.lista.slice();
      uj[i] = f;
      this.lista = uj;
    } else {
      this.lista = [f, ...this.lista].slice(0, MAX);
    }
  }

  /**
   * Feliratkozás a core eseményeire. A `vege` a feladat végállapotakor fut (egyszer, élő eseményre; a törölt sorban
   * álló feladatra nem, a betöltött előzményre sem).
   */
  figyel(k: CoreKapcsolat, vege?: (f: Feladat) => void): () => void {
    const le = [
      k.figyel('feladat', (e) => {
        const f = e.feladat as Feladat | undefined;
        if (!f || typeof f.id !== 'string') return;
        const elozo = this.kap(f.id);
        this.upsert(f);
        if (LEZART.has(f.allapot) && f.allapot !== 'torolve' && !(elozo && LEZART.has(elozo.allapot))) vege?.(f);
      }),
      k.figyel('hello', () => void this.betolt()),
    ];
    void this.betolt();
    return () => le.forEach((f) => f());
  }
}

export const feladatsor = new Feladatsor();
