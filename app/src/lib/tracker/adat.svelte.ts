// A Statisztika és a Használat nézet adata (C27): a core lekérdezései, tartomány-lapozással. Csak látszó nézetnél
// frissül (`megjelenik()` visszaadja a leállítót), előtte a kliens puffere elmegy, hogy a mai szám friss legyen.

import { ApiHiba } from '../core/api';
import { trackerApi } from './api';
import { trackerKliens } from './kliens.svelte';
import { maiNap, napEltol } from './megjelenites';
import type { Hasznalat, Statisztika } from './tipusok';

const FRISSITES_MS = 30_000;

function megjelenikKozos(frissit: () => Promise<void>): () => void {
  void frissit();
  const t = setInterval(() => {
    if (document.visibilityState === 'visible') void frissit();
  }, FRISSITES_MS);
  return () => clearInterval(t);
}

const hibaSzoveg = (e: unknown) => (e instanceof ApiHiba ? e.message : String(e));

export class StatisztikaAdat {
  adat = $state.raw<Statisztika | null>(null);
  hiba = $state<string | null>(null);
  bontas = $state<'nap' | 'het'>('nap');
  /** Hány lappal vagyunk a mai tartomány előtt (a lap 7 nap, heti bontásnál 8 hét). */
  lap = $state(0);

  get tartomany(): { tol: string; ig: string } {
    const nap = this.bontas === 'nap' ? 7 : 56;
    const ig = napEltol(maiNap(), -this.lap * nap);
    return { tol: napEltol(ig, -(nap - 1)), ig };
  }

  /** A legutóbbi kérés sorszáma: a régebbi (pl. gyors Nap/Hét váltásnál lassabban érkező) válasz nem írja felül az újabbat. */
  private sorszam = 0;

  async frissit(): Promise<void> {
    const n = ++this.sorszam;
    const { tol, ig } = this.tartomany;
    const bontas = this.bontas;
    await trackerKliens.kuld();
    try {
      const adat = await trackerApi.statisztika(tol, ig, bontas);
      if (n !== this.sorszam) return;
      this.adat = adat;
      this.hiba = null;
    } catch (e) {
      if (n === this.sorszam) this.hiba = hibaSzoveg(e);
    }
  }

  valt(bontas: 'nap' | 'het'): void {
    this.bontas = bontas;
    this.lap = 0;
    void this.frissit();
  }

  lapoz(n: number): void {
    this.lap = Math.max(0, this.lap + n);
    void this.frissit();
  }

  megjelenik(): () => void {
    return megjelenikKozos(() => this.frissit());
  }
}

export class HasznalatAdat {
  adat = $state.raw<Hasznalat | null>(null);
  hiba = $state<string | null>(null);
  /** A tartomány napjai (a használati mérés alapból az utolsó 30 nap). */
  napok = $state(30);

  private sorszam = 0;

  async frissit(): Promise<void> {
    const n = ++this.sorszam;
    const ig = maiNap();
    const napok = this.napok;
    await trackerKliens.kuld();
    try {
      const adat = await trackerApi.hasznalat(napEltol(ig, -(napok - 1)), ig);
      if (n !== this.sorszam) return;
      this.adat = adat;
      this.hiba = null;
    } catch (e) {
      if (n === this.sorszam) this.hiba = hibaSzoveg(e);
    }
  }

  valt(napok: number): void {
    this.napok = napok;
    void this.frissit();
  }

  megjelenik(): () => void {
    return megjelenikKozos(() => this.frissit());
  }
}

/** A vezérlő kompakt szakaszainak közös példánya (a részletes nézeteknek saját példányuk van: külön tartomány). */
export const statisztikaVezerlo = new StatisztikaAdat();
export const hasznalatVezerlo = new HasznalatAdat();
