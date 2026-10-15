// Az Asszisztens és a Tracker kapcsolója (10. döntés: alapból mindkettő be). Az állapot a core-é (`kapcsolok.json`),
// mert az asszisztens háttérmunkája (higiénia, linkjavaslat) is olvassa; a felület a WS `kapcsolok` eseményből és a PUT válaszából követi.

import { ApiHiba } from '../core/api';
import type { CoreKapcsolat } from '../core/ws.svelte';
import { vezerloApi } from './api';
import type { Kapcsolok } from './tipusok';

export class VezerloKapcsolok {
  ertek = $state<Kapcsolok>({ asszisztens: true, tracker: true });
  hiba = $state<string | null>(null);

  async betolt(): Promise<void> {
    try {
      this.ertek = (await vezerloApi.kapcsolok()).kapcsolok;
      this.hiba = null;
    } catch (e) {
      this.hiba = e instanceof ApiHiba ? e.message : String(e);
    }
  }

  /** A kapcsoló azonnal vált (a felület nem várakozik), hiba esetén visszaáll és a hiba megjelenik. */
  async allit(nev: keyof Kapcsolok, be: boolean): Promise<void> {
    const regi = this.ertek[nev];
    this.ertek = { ...this.ertek, [nev]: be };
    try {
      this.ertek = (await vezerloApi.kapcsolokIr({ [nev]: be })).kapcsolok;
      this.hiba = null;
    } catch (e) {
      this.ertek = { ...this.ertek, [nev]: regi };
      this.hiba = e instanceof ApiHiba ? e.message : String(e);
    }
  }

  figyel(k: CoreKapcsolat): () => void {
    const le = k.figyel('kapcsolok', (e) => {
      const v = e.kapcsolok as Partial<Kapcsolok> | undefined;
      if (v && typeof v.asszisztens === 'boolean' && typeof v.tracker === 'boolean') this.ertek = { asszisztens: v.asszisztens, tracker: v.tracker };
    });
    // újracsatlakozás (a core újraindult, vagy a kapcsolat megszakadt): a közben váltott állapot újra betöltődik
    const le2 = k.figyel('hello', () => void this.betolt());
    void this.betolt();
    return () => {
      le();
      le2();
    };
  }
}

export const vezerloKapcsolok = new VezerloKapcsolok();
