// Az Asszisztens (C30a) felületi állapota: a jegyzet higiénia-tételei (jobb panel), a „Ma” oldal összegzése és a heti
// szokásminta-javaslat, a vezérlő statisztikája. Mindhárom csak a core gyorsítótárát/lekérdezését kéri; a számítás a core
// háttérszálában fut, aktív használat alatt szünetel — a felület nem pollingol, a WS `asszisztens_valtozas` eseményre frissít.

import { ApiHiba } from '../core/api';
import type { CoreKapcsolat } from '../core/ws.svelte';
import { asszisztensApi } from './api';
import type { HigieniaOsszegzes, HigieniaTetel, Statisztika, SzokasJavaslat } from './tipusok';

const hibaSzoveg = (e: unknown) => (e instanceof ApiHiba ? e.message : e instanceof Error ? e.message : String(e));
/** Az index még épül (503) vagy nincs ilyen jegyzet (404): nem hiba, csak nincs tétel. */
const csendes = (e: unknown) => e instanceof ApiHiba && (e.statusz === 404 || e.statusz === 503);

/** Egy jegyzet higiénia-tételei: az aktív fülre és a változásokra (gépelés után 1,5 s-os csenddel) frissül. */
export class JegyzetHigienia {
  tetelek = $state.raw<HigieniaTetel[]>([]);
  hiba = $state<string | null>(null);
  private sorszam = 0;
  private idozito: ReturnType<typeof setTimeout> | null = null;

  async frissit(ut: string | null): Promise<void> {
    const en = ++this.sorszam;
    if (!ut || !ut.toLowerCase().endsWith('.md')) {
      this.tetelek = [];
      this.hiba = null;
      return;
    }
    try {
      const d = await asszisztensApi.jegyzetHigienia(ut);
      if (en !== this.sorszam) return;
      this.tetelek = d.tetelek;
      this.hiba = null;
    } catch (e) {
      if (en !== this.sorszam) return;
      this.tetelek = [];
      this.hiba = csendes(e) ? null : hibaSzoveg(e);
    }
  }

  figyel(k: CoreKapcsolat, aktivUt: () => string | null, kesleltetes = 1500): () => void {
    const utemez = () => {
      if (this.idozito) clearTimeout(this.idozito);
      this.idozito = setTimeout(() => void this.frissit(aktivUt()), kesleltetes);
    };
    const le = [
      k.figyel('vault_iras', utemez),
      k.figyel('vault_valtozas', utemez),
      k.figyel('vault_atnevezes', utemez),
      k.figyel('index', utemez),
      k.figyel('asszisztens_valtozas', utemez),
    ];
    return () => {
      le.forEach((f) => f());
      if (this.idozito) clearTimeout(this.idozito);
    };
  }
}

/** A „Ma” oldal Asszisztens-szakasza: a higiénia új tételei és a heti szokásminta-javaslat. */
export class AsszisztensMa {
  osszegzes = $state.raw<HigieniaOsszegzes | null>(null);
  szokas = $state.raw<SzokasJavaslat | null>(null);
  hiba = $state<string | null>(null);
  foglalt = $state(false);

  async betoltOsszegzes(): Promise<void> {
    try {
      this.osszegzes = await asszisztensApi.osszegzes();
      this.hiba = null;
    } catch (e) {
      if (!csendes(e)) this.hiba = hibaSzoveg(e);
    }
  }

  async betoltSzokas(): Promise<void> {
    try {
      this.szokas = (await asszisztensApi.szokas()).javaslat;
    } catch {
      this.szokas = null;
    }
  }

  /** Az „új” nullázása („Láttam”). */
  async latva(): Promise<void> {
    this.foglalt = true;
    try {
      this.osszegzes = await asszisztensApi.latva();
      this.hiba = null;
    } catch (e) {
      this.hiba = hibaSzoveg(e);
    } finally {
      this.foglalt = false;
    }
  }

  async szokasDontes(dontes: 'elfogad' | 'elutasit'): Promise<void> {
    const j = this.szokas;
    if (!j) return;
    this.foglalt = true;
    try {
      await asszisztensApi.szokasDontes(j.azon, dontes);
      this.szokas = null;
      this.hiba = null;
    } catch (e) {
      this.hiba = hibaSzoveg(e);
      void this.betoltSzokas();
    } finally {
      this.foglalt = false;
    }
  }

  figyel(k: CoreKapcsolat): () => void {
    return k.figyel('asszisztens_valtozas', () => void this.betoltOsszegzes());
  }
}

/** A vezérlő Asszisztens-szakasza: a javaslatok statisztikája és az egy gombos törlés. */
export class AsszisztensStatisztika {
  adat = $state.raw<Statisztika | null>(null);
  hiba = $state<string | null>(null);
  foglalt = $state(false);

  async betolt(): Promise<void> {
    try {
      this.adat = await asszisztensApi.statisztika();
      this.hiba = null;
    } catch (e) {
      this.hiba = hibaSzoveg(e);
    }
  }

  /** `true`, ha a törlés sikerült. */
  async torol(): Promise<boolean> {
    this.foglalt = true;
    try {
      await asszisztensApi.statisztikaTorol();
      await this.betolt();
      return true;
    } catch (e) {
      this.hiba = hibaSzoveg(e);
      return false;
    } finally {
      this.foglalt = false;
    }
  }
}

export const asszisztensMa = new AsszisztensMa();
export const asszisztensStatisztika = new AsszisztensStatisztika();
