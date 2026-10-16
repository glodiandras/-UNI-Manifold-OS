// Hasonló jegyzetek a jobb panelnek (C25c): a core `GET /api/kereses/hasonlo` válasza — a vektortárból, modell nélkül (a
// jegyzet darabvektorainak átlaga → a többi jegyzet legközelebbi darabja). Ha a jegyzetnek még nincs vektora, a core ezt
// mondja ki (`nincs_vektor`), és modellt nem tölt. Csak a látható, kinyitott szakasz tölt (C38: csend); a vault változására
// 1 s csend után frissül, gépelés közben nem.

import { t } from '../i18n';

import { ApiHiba, kerdez } from '../core/api';
import type { CoreKapcsolat } from '../core/ws.svelte';

export type HasonloAllapot = 'ok' | 'nincs_tar' | 'nincs_vektor' | 'nem_jegyzet';

export interface HasonloJegyzet {
  ut: string;
  /** koszinusz-hasonlóság (−1…1) */
  pont: number;
  /** a jegyzet már linkeli */
  kimeno: boolean;
  /** ez linkeli a jegyzetet */
  bejovo: boolean;
}

export interface HasonloValasz {
  ut: string;
  allapot: HasonloAllapot;
  /** a vektor a jegyzet egy korábbi változatáé (a vektorindex még nem frissítette) */
  elavult: boolean;
  talalatok: HasonloJegyzet[];
}

export const HASONLO_N = 12;

/** Az állapot magyar mondata (az `ok` üres). */
export function allapotSzoveg(a: HasonloAllapot): string {
  switch (a) {
    case 'nincs_tar':
      return t('Még nincs vektorindex: a hasonló jegyzetekhez a vektorindex automatikus építése kell (tétlenségben fut).');
    case 'nincs_vektor':
      return t('Ennek a jegyzetnek még nincs vektora — a vektorindex a következő tétlen időszakban feldolgozza.');
    case 'nem_jegyzet':
      return t('Hasonló jegyzetek csak Markdown-jegyzethez vannak.');
    default:
      return '';
  }
}

/** A pont olvasható alakja (százalék, egész). */
export function pontSzazalek(p: number): string {
  return `${Math.round(Math.max(0, Math.min(1, p)) * 100)}%`;
}

export class HasonloJegyzetek {
  ut = $state<string | null>(null);
  valasz = $state.raw<HasonloValasz | null>(null);
  betolt = $state(false);
  hiba = $state<string | null>(null);
  private sorszam = 0;
  private idozito: ReturnType<typeof setTimeout> | null = null;

  async frissit(ut: string | null): Promise<void> {
    const en = ++this.sorszam;
    if (ut !== this.ut) this.valasz = null;
    this.ut = ut;
    if (!ut) {
      this.betolt = false;
      this.hiba = null;
      return;
    }
    this.betolt = true;
    try {
      const v = await kerdez<HasonloValasz>(`/api/kereses/hasonlo?ut=${encodeURIComponent(ut)}&n=${HASONLO_N}`, { idokorlat: 10000 });
      if (en !== this.sorszam) return;
      this.valasz = v;
      this.hiba = null;
    } catch (e) {
      if (en !== this.sorszam) return;
      this.valasz = null;
      // a fájl még nincs az indexben (új), vagy az index épül: nem hiba, a következő esemény újratölt
      this.hiba = e instanceof ApiHiba && (e.statusz === 404 || e.statusz === 503) ? null : e instanceof Error ? e.message : String(e);
    } finally {
      if (en === this.sorszam) this.betolt = false;
    }
  }

  /** WS-figyelés: a vault változására (1 s összevonással) újratölt; `aktivUt` `undefined`: most nem kell tölteni. */
  figyel(k: CoreKapcsolat, aktivUt: () => string | null | undefined): () => void {
    const utemez = () => {
      if (this.idozito) clearTimeout(this.idozito);
      this.idozito = setTimeout(() => {
        this.idozito = null;
        const ut = aktivUt();
        if (ut !== undefined) void this.frissit(ut);
      }, 1000);
    };
    const le = k.figyel('vault_valtozas', utemez);
    return () => {
      le();
      if (this.idozito) clearTimeout(this.idozito);
    };
  }
}
