// A tracker kliense (C27): az események puffere és kötegelt küldése a core-nak (`POST /api/tracker/esemenyek`).
// A felület csak eseményt küld, az aggregálás és a tárolás a core-é; a vaultba semmi nem ír. A gyűjtés a Tracker
// kapcsoló alatt áll (vezérlő): kikapcsolva a kliens nem is gyűjt, a core pedig a kötegeket maga is elveti.
// Küldés: 30 s-onként, a lap elrejtésekor és elhagyásakor azonnal (`keepalive`). Átmeneti hibánál (hálózat,
// időtúllépés, 5xx) a köteg visszakerül a pufferbe (korlátozva); a 4xx tartós hiba (a core elutasította): a köteg
// eldobódik és naplózódik — különben örökké újraküldené, és a munkamenet minden adata elveszne (T029). A gyűjtő soha
// nem dob és nem akaszt.

import { ApiHiba, kerdez } from '../core/api';
import { t } from '../i18n';
import { vezerloKapcsolok } from '../vezerlo/kapcsolok.svelte';
import { Hisztogram, type VedrokKuldes } from './kesleltetes';
import { maiNap } from './megjelenites';
import type { TorlesMit } from './tipusok';
import type { ParancsForras } from '../parancsok/regiszter';

export const KULDES_KOZ_MS = 30_000;
const PUFFER_MAX = 2000; // egy köteg legfeljebb ennyi sor (a core korlátja is ez)

/** Az események `adat`-ja — a core `tracker.ADAT_SEMA` fehérlistájának tükre (2. audit T143): más kulcs a core-ban kiesik,
 *  jegyzettartalom, cím és útvonal nem kerülhet bele (az útvonal az `ut` paraméteré). */
export interface EsemenyAdatok {
  kartya_valasz: { jegy?: number; ms?: number; kartya_id?: string };
  kviz_eredmeny: {
    jo?: number;
    ossz?: number;
    ms?: number;
    kviz?: string;
    mod?: 'teljes' | 'hibasak';
    pont?: number;
    osszes?: number;
    szazalek?: number;
    tudja?: number;
    szerencses?: number;
    tevkepzet?: number;
    hiany?: number;
  };
  integralt_video: { video_s?: number; jegyzet_db?: number; kotes?: 'biztos' | 'valoszinu' | 'nincs' };
  integralt_fuzet: { oldal_db?: number; kep_db?: number };
}
export type EsemenyTipus = keyof EsemenyAdatok;

interface Koteg {
  aktiv: { nap: string; ut: string; mp: number }[];
  karakter: { nap: string; ut: string; beszurt: number; torolt: number }[];
  parancsok: { id: string; forras: ParancsForras; db: number }[];
  kesleltetes: { gepeles?: VedrokKuldes; mentes?: VedrokKuldes };
  esemenyek: { tipus: EsemenyTipus; nap: string; ut?: string; adat?: Record<string, unknown> }[];
}

export class TrackerKliens {
  private aktiv = new Map<string, { nap: string; ut: string; mp: number }>();
  private karakter = new Map<string, { nap: string; ut: string; beszurt: number; torolt: number }>();
  private parancsok = new Map<string, { id: string; forras: ParancsForras; db: number }>();
  private esemenyek: Koteg['esemenyek'] = [];
  private gepeles = new Hisztogram();
  private mentes = new Hisztogram();
  private idozito: ReturnType<typeof setInterval> | null = null;
  /** A még válaszra váró küldések (a törlés megvárja őket). */
  private repuloben = new Set<Promise<void>>();
  /** Törlés közben nem küld (T110); számláló, mert két törlés átfedhet. */
  private felfuggesztve = 0;
  /** Teszt: a kapcsoló felülírása (alap: a vezérlő kapcsolója). */
  kapcsoloFelulir: boolean | null = null;
  /**
   * A core utolsó válasza szerint nem fogadja az eseményeket (`{fogadva: false}`: az adatbázis nem írható, vagy nála a
   * Tracker ki van kapcsolva) — a vezérlő Tracker-szakasza kimondja, különben az adat csendben elveszne (T007). `null`:
   * fogadja (vagy még nem volt köteg). Hálózati hiba nem állít át semmit: a köteg visszakerül a pufferbe.
   */
  nemFogad = $state<string | null>(null);

  /** Gyűjt-e a kliens (a Tracker kapcsoló). */
  get be(): boolean {
    return this.kapcsoloFelulir ?? vezerloKapcsolok.ertek.tracker;
  }

  aktivMp(ut: string, mp: number, nap = maiNap()): void {
    if (!this.be || !ut || mp <= 0) return;
    const k = `${nap}\0${ut}`;
    const e = this.aktiv.get(k) ?? { nap, ut, mp: 0 };
    e.mp += mp;
    this.aktiv.set(k, e);
  }

  szerkesztes(ut: string, beszurt: number, torolt: number, nap = maiNap()): void {
    if (!this.be || !ut || (beszurt <= 0 && torolt <= 0)) return;
    const k = `${nap}\0${ut}`;
    const e = this.karakter.get(k) ?? { nap, ut, beszurt: 0, torolt: 0 };
    e.beszurt += beszurt;
    e.torolt += torolt;
    this.karakter.set(k, e);
  }

  parancs(id: string, forras: ParancsForras): void {
    if (!this.be) return;
    const k = `${id}\0${forras}`;
    const e = this.parancsok.get(k) ?? { id, forras, db: 0 };
    e.db++;
    this.parancsok.set(k, e);
  }

  gepelesMs(ms: number): void {
    if (this.be) this.gepeles.add(ms);
  }

  mentesMs(ms: number): void {
    if (this.be) this.mentes.add(ms);
  }

  /** Kártya-, kvíz- és integrálás-esemény (a C20–C23 gyűjtői hívják; jegyzettartalom nem kerülhet bele). */
  esemeny<T extends EsemenyTipus>(tipus: T, ut?: string, adat?: EsemenyAdatok[T]): void {
    if (!this.be || this.esemenyek.length >= PUFFER_MAX) return;
    this.esemenyek.push({ tipus, nap: maiNap(), ...(ut ? { ut } : {}), ...(adat ? { adat: adat as Record<string, unknown> } : {}) });
  }

  get uresPuffer(): boolean {
    return !this.aktiv.size && !this.karakter.size && !this.parancsok.size && !this.esemenyek.length && this.gepeles.ures && this.mentes.ures;
  }

  /** A puffer kiürítése egy köteggé (vagy null). Kikapcsolt kapcsolónál a puffer eldobódik, nem megy el. */
  private kiurit(): Koteg | null {
    if (!this.be) {
      this.eldob();
      return null;
    }
    if (this.uresPuffer) return null;
    const k: Koteg = {
      aktiv: [...this.aktiv.values()].slice(0, PUFFER_MAX),
      karakter: [...this.karakter.values()].slice(0, PUFFER_MAX),
      parancsok: [...this.parancsok.values()].slice(0, PUFFER_MAX),
      kesleltetes: {},
      esemenyek: this.esemenyek.splice(0, PUFFER_MAX),
    };
    this.aktiv.clear();
    this.karakter.clear();
    this.parancsok.clear();
    const g = this.gepeles.kiurit();
    const m = this.mentes.kiurit();
    if (g) k.kesleltetes.gepeles = g;
    if (m) k.kesleltetes.mentes = m;
    return k;
  }

  /** A puffer eldobása; `mit`: a törlés hatóköre (`tevekenyseg` = `tr_*`: aktív idő, karakter, események; `hasznalat` = `has_*`). */
  private eldob(mit: TorlesMit = 'minden'): void {
    if (mit !== 'hasznalat') {
      this.aktiv.clear();
      this.karakter.clear();
      this.esemenyek = [];
    }
    if (mit !== 'tevekenyseg') {
      this.parancsok.clear();
      this.gepeles.kiurit();
      this.mentes.kiurit();
    }
  }

  private vissza(k: Koteg): void {
    for (const e of k.aktiv) this.aktivMp(e.ut, e.mp, e.nap);
    for (const e of k.karakter) this.szerkesztes(e.ut, e.beszurt, e.torolt, e.nap);
    for (const e of k.parancsok) for (let i = 0; i < e.db; i++) this.parancs(e.id, e.forras);
    if (k.kesleltetes.gepeles) this.gepeles.vissza(k.kesleltetes.gepeles);
    if (k.kesleltetes.mentes) this.mentes.vissza(k.kesleltetes.mentes);
    this.esemenyek.unshift(...k.esemenyek.slice(0, Math.max(0, PUFFER_MAX - this.esemenyek.length)));
  }

  /** A puffer elküldése. Soha nem dob: átmeneti hibánál a köteg visszakerül, a 4xx-et eldobja (T029). */
  async kuld(elhagyas = false): Promise<void> {
    if (this.felfuggesztve) return;
    const k = this.kiurit();
    if (!k) return;
    const p = this.kuldKoteg(k, elhagyas);
    this.repuloben.add(p);
    try {
      await p;
    } finally {
      this.repuloben.delete(p);
    }
  }

  /**
   * A kilépés előtti ürítés (T114): az úton lévő köteg válaszát megvárja, utána a puffer maradékát is elküldi — a héj ezután
   * állítja le a core-t. Soha nem dob; a sikertelen küldés kötege visszakerül a pufferbe. Az időkorlátot a hívó adja
   * (`hid.ts`): a kilépést nem tarthatja fel egy nem válaszoló core.
   */
  async kuldKi(): Promise<void> {
    try {
      await Promise.allSettled([...this.repuloben]);
      await this.kuld();
    } catch {
      // nincs mit tenni: a gyűjtő soha nem akaszt
    }
  }

  private async kuldKoteg(k: Koteg, elhagyas: boolean): Promise<void> {
    try {
      const v = await kerdez<{ fogadva?: boolean; hiba?: string; elvetve?: number; okok?: string[] }>('/api/tracker/esemenyek', {
        metodus: 'POST', torzs: k, idokorlat: 5000, keepalive: elhagyas,
      });
      this.nemFogad = v?.fogadva === false ? (v.hiba ?? t('a core szerint a Tracker ki van kapcsolva')) : null;
      if (v?.fogadva && v.elvetve) console.warn(`[tracker] a core ${v.elvetve} elemet kihagyott a kötegből: ${(v.okok ?? []).join('; ')}`);
    } catch (e) {
      if (e instanceof ApiHiba && e.statusz >= 400 && e.statusz < 500) {
        console.warn(`[tracker] a core elutasította a köteget (HTTP ${e.statusz}: ${e.message}); eldobva, nem küldöm újra`);
        return;
      }
      this.vissza(k);
    }
  }

  /**
   * A tracker-adat törlése előtt (T110): a törlés hatókörébe eső puffer eldobódik, a küldés a `torlesUtan()`-ig áll, és
   * a már úton lévő köteg válaszát megvárja — különben a törlés előtti adat a törlés után beíródna. A sikertelen küldés
   * visszatett kötegét is eldobja. Minden `torlesElott` párja egy `torlesUtan` (siker és hiba esetén is).
   */
  async torlesElott(mit: TorlesMit): Promise<void> {
    this.felfuggesztve++;
    this.eldob(mit);
    await Promise.allSettled([...this.repuloben]);
    this.eldob(mit);
  }

  torlesUtan(): void {
    this.felfuggesztve = Math.max(0, this.felfuggesztve - 1);
  }

  /** Az időzített küldés és a lap elrejtésekor/elhagyásakor való azonnali küldés. */
  indit(): () => void {
    this.idozito = setInterval(() => void this.kuld(), KULDES_KOZ_MS);
    const elrejt = () => {
      if (document.visibilityState === 'hidden') void this.kuld(true);
    };
    const elhagy = () => void this.kuld(true);
    document.addEventListener('visibilitychange', elrejt);
    window.addEventListener('pagehide', elhagy);
    return () => {
      if (this.idozito) clearInterval(this.idozito);
      this.idozito = null;
      document.removeEventListener('visibilitychange', elrejt);
      window.removeEventListener('pagehide', elhagy);
    };
  }
}

export const trackerKliens = new TrackerKliens();
