// A vault fájllistája a core indexéből (`/api/vault/fa`), a `vault_valtozas` és `index` WS-eseményre frissül.
// A felület nem old fel linket és nem olvas fájlrendszert (ARCHITECTURE 2.): csak ezt a listát mutatja.

import { ApiHiba, kerdez } from '../core/api';
import type { CoreKapcsolat } from '../core/ws.svelte';
import { FuzzyIndex } from '../kereses/fuzzy';

export type FajlTipus = 'md' | 'canvas' | 'base' | 'pdf' | 'kep' | 'video' | 'hang' | 'felirat' | 'egyeb';

export interface FajlInfo {
  ut: string;
  tipus: FajlTipus;
  meret: number;
  mtime: number | null;
  /** Valódi fájllétrehozási idő epoch-másodpercben. Ha a fájlrendszer nem ad születési időt, ismeretlen. */
  ctime?: number | null;
  /** A Beállítások › Files & links › Excluded files listája illeszkedik rá (14-appearance-06): a fán halvány, a keresőből, a gráfból és a gyorsváltóból kimarad. */
  kizart?: boolean;
}

export interface IndexAllapot {
  kesz: boolean;
  elerheto?: boolean;
  fajlok?: number;
  jegyzetek?: number;
  hiba?: string | null;
  /** C25c: a PDF-szöveg kinyerésének állapota (a keresőpanel kimondja, amíg nem kész) */
  pdf_szoveg?: { osszes: number; kesz: number; varakozik?: number; kinyero?: boolean; hiba?: string | null };
}

/** A megjelenített név: jegyzetnél kiterjesztés nélkül (mint az Obsidianban), másnál teljes fájlnév. */
export function fajlNev(ut: string): string {
  const alap = ut.slice(ut.lastIndexOf('/') + 1);
  return alap.toLowerCase().endsWith('.md') ? alap.slice(0, -3) : alap;
}

export function mappa(ut: string): string {
  const i = ut.lastIndexOf('/');
  return i < 0 ? '' : ut.slice(0, i);
}

/** Ennél nagyobb zsugorodás (az eltűnt utak száma és aránya) gyanús: átmenetileg elérhetetlen vault, részleges index. Ilyenkor
 *  a nyitott fülek nem ürülnek ki (és ez nem mentődik a felület-állapotba); a valódi tömeges törlés fülei a fájl
 *  megnyitásakor jelzik, hogy a fájl eltűnt. */
export const GYANUS_ZSUGORODAS = { db: 20, arany: 0.3 } as const;

export class VaultFajlok {
  lista = $state.raw<FajlInfo[]>([]);
  /** A vault mappái (az üresek is): az áthelyezés célválasztójához és az új jegyzet helyéhez. */
  mappak = $state.raw<string[]>([]);
  /** A Markdown-jegyzetek száma a listából (az állapotsornak). */
  jegyzetek = $derived(this.lista.reduce((n, f) => n + (f.tipus === 'md' ? 1 : 0), 0));
  index = $state<IndexAllapot | null>(null);
  hiba = $state<string | null>(null);
  /** Megjött-e már egyszer a lista (addig a hiányzó fájl nem „eltűnt”, csak még nem tudjuk). */
  betoltve = $state(false);
  /** A vault `showUnsupportedFiles` beállítása (07-explorer-12): igaz esetén a nem támogatott kiterjesztések is látszanak a fán. */
  mindenKiterjesztes = $state(false);
  private terkep = new Map<string, FajlInfo>();
  private fuzzy: FuzzyIndex<FajlInfo> | null = null;
  private idobelyegFigyelok = 0;
  private keresSorszam = 0;
  private csakIdobelyeg = false;
  private kesleltetes: ReturnType<typeof setTimeout> | null = null;
  /** A frissítés után eltűnt utak (a nyitott fülek üresre váltanak). */
  eltuntek: ((utak: Set<string>) => void) | null = null;

  info(ut: string): FajlInfo | undefined {
    void this.lista; // reaktív függés: a lista megérkezésekor a hívó $derived újraszámol
    return this.terkep.get(ut);
  }

  kereso(): FuzzyIndex<FajlInfo> {
    this.fuzzy ??= new FuzzyIndex(this.lista.map((f) => ({ ertek: f, nev: fajlNev(f.ut), ut: mappa(f.ut) })));
    return this.fuzzy;
  }

  async frissit(): Promise<void> {
    const keres = ++this.keresSorszam;
    try {
      const index = await kerdez<IndexAllapot>('/api/vault/index', { idokorlat: 5000 });
      if (keres !== this.keresSorszam) return;
      this.index = index;
      if (!index.kesz) return;
      const d = await kerdez<{ fajlok: FajlInfo[]; mappak?: string[]; beallitasok?: { minden_kiterjesztes?: boolean } }>('/api/vault/fa', { idokorlat: 10000 });
      if (keres !== this.keresSorszam) return;
      this.mindenKiterjesztes = d.beallitasok?.minden_kiterjesztes === true;
      this.mappak = d.mappak ?? [];
      this.beallit(d.fajlok);
      this.hiba = null;
    } catch (e) {
      if (keres !== this.keresSorszam) return;
      if (e instanceof ApiHiba && e.statusz === 503) return; // az index még épül: az `index` esemény hoz újra
      this.hiba = e instanceof Error ? e.message : String(e);
    }
  }

  beallit(fajlok: FajlInfo[]): void {
    const regi = this.terkep;
    this.terkep = new Map(fajlok.map((f) => [f.ut, f]));
    this.lista = fajlok;
    this.betoltve = true;
    this.fuzzy = null;
    if (regi.size && this.eltuntek) {
      const eltunt = new Set([...regi.keys()].filter((u) => !this.terkep.has(u)));
      const gyanus =
        this.index?.elerheto === false ||
        (eltunt.size > GYANUS_ZSUGORODAS.db && eltunt.size > regi.size * GYANUS_ZSUGORODAS.arany);
      if (eltunt.size && !gyanus) this.eltuntek(eltunt);
    }
  }

  /** Csak a dátum szerint rendezett fájlfa kér tartalmi eseményre is friss időbélyegeket. */
  idobelyegeketFigyel(): () => void {
    if (++this.idobelyegFigyelok === 1) this.utemez(0, true);
    let el = true;
    return () => {
      if (!el) return;
      el = false;
      this.idobelyegFigyelok--;
      if (this.idobelyegFigyelok === 0 && this.kesleltetes && this.csakIdobelyeg) {
        clearTimeout(this.kesleltetes);
        this.kesleltetes = null;
        this.csakIdobelyeg = false;
      }
    };
  }

  figyel(k: CoreKapcsolat): () => void {
    // A lista csak szerkezeti változásra töltődik újra (új vagy eltűnt fájl, tömeges változás); a meglévő
    // fájl tartalmi változása — a szerkesztő mentése (C08) — nem hozza le újra a teljes listát gépelés közben.
    const le1 = k.figyel('vault_valtozas', (e) => {
      const utak = (e.utak as string[] | undefined) ?? [];
      const torolt = (e.torolt as string[] | undefined) ?? [];
      // C33 (T173): a csak mappát érintő változás (üres mappa kívülről) is szerkezeti: a fa újratölt
      const mappak = (e.mappak as string[] | undefined) ?? [];
      if (e.tomeges || torolt.length || mappak.length || utak.some((u) => !this.terkep.has(u))) this.utemez();
      else if (this.idobelyegFigyelok > 0 && utak.length) this.utemez(300, true);
    });
    const le2 = k.figyel('index', (e) => {
      this.index = e as unknown as IndexAllapot;
      this.utemez(0);
    });
    const le3 = k.figyel('hello', () => this.utemez(0)); // újracsatlakozás után
    return () => {
      le1();
      le2();
      le3();
    };
  }

  private utemez(ms = 300, csakIdobelyeg = false) {
    // Egy kényelmi dátumfrissítés nem késleltetheti és nem mondhatja le a szerkezeti változásét.
    if (csakIdobelyeg && this.kesleltetes && !this.csakIdobelyeg) return;
    if (this.kesleltetes) clearTimeout(this.kesleltetes);
    this.csakIdobelyeg = csakIdobelyeg;
    this.kesleltetes = setTimeout(() => {
      this.kesleltetes = null;
      this.csakIdobelyeg = false;
      if (!csakIdobelyeg || this.idobelyegFigyelok > 0) void this.frissit();
    }, ms);
  }
}
