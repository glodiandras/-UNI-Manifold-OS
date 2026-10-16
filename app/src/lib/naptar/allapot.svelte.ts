// A vezérlő „Naptár és emlékeztetők” szakaszának adata (C29): a core `GET /api/naptar/allapot`-a és a szinkron-,
// kategória- és ütközés-műveletek. Csak látszó szakasznak tölt (`megjelenik()`), a WS-eseményekre összevonva; a
// nem látszó szakasz nem tölt, a következő megjelenéskor úgyis újratölt. A naptárba itt nem írunk: az egyetlen író út a Ma oldal
// javaslat-jóváhagyása.

import { t } from '../i18n';

import { ApiHiba } from '../core/api';
import type { CoreKapcsolat } from '../core/ws.svelte';
import { naptarApi } from './api';
import { naptarHid } from './hid.svelte';
import type { NaptarAllapotValasz } from './tipusok';

const hibaSzoveg = (e: unknown) => (e instanceof ApiHiba ? e.message : e instanceof Error ? e.message : String(e));

/** A szakasz a következő WS-eseményekre töltődik újra. */
export const NAPTAR_ESEMENYEK = ['naptar_valtozas', 'naptar_javaslat', 'emlekezteto_utkozes', 'emlekezteto_valtozas'] as const;

export class NaptarAllapot {
  adat = $state.raw<NaptarAllapotValasz | null>(null);
  hiba = $state<string | null>(null);
  /** A „Szinkron most” fut. */
  foglalt = $state(false);
  /** A művelet (kategória, láttamozás) hibája. */
  muveletHiba = $state<string | null>(null);
  /** A most módosított naptárak azonosítói (a választó addig tiltott). */
  kategoriaFolyamatban = $state<string[]>([]);

  private latszok = 0;
  private idozito: ReturnType<typeof setTimeout> | null = null;
  private sorszam = 0;

  async betolt(frissit = false): Promise<void> {
    const en = ++this.sorszam;
    try {
      const v = await naptarApi.allapot(frissit);
      if (en !== this.sorszam) return;
      this.adat = v;
      this.hiba = null;
    } catch (e) {
      if (en !== this.sorszam) return;
      this.hiba = hibaSzoveg(e);
    }
  }

  /** Egy szakasz-példány megjelent: tölt (a héjban az engedélyt a héjtól is lekérdezi); a visszaadott függvény leiratkozik. */
  megjelenik(): () => void {
    this.latszok++;
    void this.betolt(naptarHid.elerheto);
    if (naptarHid.elerheto) naptarHid.allapotKer();
    let kesz = false;
    return () => {
      if (kesz) return;
      kesz = true;
      this.latszok = Math.max(0, this.latszok - 1);
      if (!this.latszok && this.idozito) {
        clearTimeout(this.idozito);
        this.idozito = null;
      }
    };
  }

  /** Egy változás-esemény: látszó szakasznak összevonva tölt (a nem látszó a megjelenéskor úgyis újratölt). */
  utemez(kesleltet = 400): void {
    if (!this.latszok) return;
    if (this.idozito) clearTimeout(this.idozito);
    this.idozito = setTimeout(() => {
      this.idozito = null;
      void this.betolt();
    }, kesleltet);
  }

  /** „Szinkron most”: egy teljes kör; a válasz maga az új állapot. */
  async szinkron(): Promise<void> {
    if (this.foglalt) return;
    this.foglalt = true;
    this.muveletHiba = null;
    try {
      this.adat = await naptarApi.szinkron();
      this.hiba = null;
    } catch (e) {
      this.muveletHiba = t('A szinkron nem sikerült: {hiba}', { hiba: hibaSzoveg(e) });
    } finally {
      this.foglalt = false;
    }
  }

  async kategoriaAllit(azon: string, kategoria: string): Promise<void> {
    if (this.kategoriaFolyamatban.includes(azon)) return;
    this.kategoriaFolyamatban = [...this.kategoriaFolyamatban, azon];
    this.muveletHiba = null;
    try {
      await naptarApi.kategoria(azon, kategoria);
      await this.betolt();
    } catch (e) {
      this.muveletHiba = t('A kategória nem állítható: {hiba}', { hiba: hibaSzoveg(e) });
    } finally {
      this.kategoriaFolyamatban = this.kategoriaFolyamatban.filter((a) => a !== azon);
    }
  }

  /** Az ütközés(ek) láttamozása; `azonok` nélkül mind. */
  async utkozesLatva(azonok?: number[]): Promise<void> {
    this.muveletHiba = null;
    try {
      await naptarApi.utkozesLatva(azonok);
      await this.betolt();
    } catch (e) {
      this.muveletHiba = t('A láttamozás nem sikerült: {hiba}', { hiba: hibaSzoveg(e) });
    }
  }

  figyel(k: CoreKapcsolat): () => void {
    const le = [...NAPTAR_ESEMENYEK.map((t) => k.figyel(t, () => this.utemez())), k.figyel('hello', () => this.utemez(300))];
    return () => {
      for (const f of le) f();
      if (this.idozito) clearTimeout(this.idozito);
      this.idozito = null;
    };
  }
}

export const naptarVezerlo = new NaptarAllapot();
