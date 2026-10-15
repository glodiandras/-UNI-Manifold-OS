// A szerkesztő közös objektumai: a nyitott dokumentumok, a fülenkénti CodeMirror-állapotok (fülváltás után
// a kurzor, a görgetés és a visszavonás megmarad) és az aktív szerkesztő (a parancsok ezen futnak).

import type { EditorState } from '@codemirror/state';
import type { EditorView } from '@codemirror/view';
import { vaultApi } from './dokumentum/api';
import { Dokumentumok } from './dokumentum/dokumentum.svelte';

export type Mod = 'elo' | 'forras' | 'olvaso';

/** Egy nyitott szerkesztő (a nézet-komponens adja); a parancsregiszter ezen keresztül éri el. */
export interface SzerkesztoPeldany {
  readonly ut: string;
  nezet(): EditorView | null;
  mod(): Mod;
  olvasoValt(): void;
  forrasValt(): void;
  mentes(): Promise<void>;
  pillanatkep(): Promise<void>;
  /** a szerkesztő mező fókuszban van-e (a formázó billentyűk csak ekkor élnek) */
  fokuszban(): boolean;
  /** Ugrás a `sor`-ra (1-től): a kurzor és a görgetés (Olvasóban a blokkhoz görget). */
  ugras(sor: number, oszlop?: number): void;
  /** A jegyzet fejezetei az élő szövegből (a vázlathoz). */
  vazlat(): VazlatElem[];
  /** Nő, ha a szöveg változott (a reaktív származtatások ebből frissülnek). */
  valtozat(): number;
}

export interface VazlatElem {
  szint: number;
  szoveg: string;
  /** a fejezet első sora (1-től) */
  sor: number;
}

interface TaroltAllapot {
  ut: string;
  allapot: EditorState;
  gorgetes: number;
}

const MAX_TAROLT = 10;

/** Az átnevezés alatt álló utak (C10) — mappa átnevezésénél (C11a) a mappa alatti minden út is annak számít. */
export class AtnevezesAlatt {
  private readonly utak = new Set<string>();
  add(ut: string): void {
    this.utak.add(ut);
  }
  delete(ut: string): void {
    this.utak.delete(ut);
  }
  clear(): void {
    this.utak.clear();
  }
  has(ut: string): boolean {
    if (this.utak.has(ut)) return true;
    for (const u of this.utak) if (ut.startsWith(u + '/')) return true;
    return false;
  }
}

export class Szerkesztok {
  readonly dokumentumok = new Dokumentumok(vaultApi());
  aktiv = $state.raw<SzerkesztoPeldany | null>(null);
  /** A nyitott szerkesztők az aktiválás sorrendjében (C16): a PDF- vagy a lejátszó-panel aktívvá válása nem törli
   *  őket, csak a szerkesztő megszűnése. Az utolsó kapja a PDF-idézetet és az időkódot. */
  private nyitott: SzerkesztoPeldany[] = []; // nem reaktív: csak a beszúráskor olvassuk

  get utolso(): SzerkesztoPeldany | null {
    return this.nyitott.at(-1) ?? null;
  }
  /** A nem-CodeMirror nézet (C14: a canvas), amely a „Mentés most” (⌘S) parancsot kapja, amíg ő az aktív fül;
   *  a Markdown-szerkesztő aktiválása (`beallit`) elveszi. */
  masNezet = $state.raw<{ mentes(): Promise<void> } | null>(null);
  private readonly tarolt = new Map<string, TaroltAllapot>();
  /** A most átnevezett/áthelyezett (vagy visszavont) utak: a közbeeső „eltűnt” események nem szólnak (C10). */
  readonly atnevezesAlatt = new AtnevezesAlatt();
  private readonly fuggoUgras = new Map<string, { sor: number; oszlop?: number }>();

  beallit(p: SzerkesztoPeldany | null): void {
    this.aktiv = p;
    if (p) this.nyitott = [...this.nyitott.filter((x) => x !== p), p];
    if (p) this.masNezet = null;
  }

  elenged(p: SzerkesztoPeldany): void {
    if (this.aktiv === p) this.aktiv = null;
  }

  /** A szerkesztő megszűnt (a fül bezárult vagy másik fájlra váltott). */
  megszunt(p: SzerkesztoPeldany): void {
    this.elenged(p);
    this.nyitott = this.nyitott.filter((x) => x !== p);
  }

  /** Ugrás egy jegyzet adott sorára: ha az aktív szerkesztő azé, azonnal; különben a jegyzet nézetének
   *  megnyílásakor/aktiválásakor (`fuggoUgrasKap`). */
  ugras(ut: string, sor: number, oszlop?: number): void {
    const a = this.aktiv;
    if (a && a.ut === ut) a.ugras(sor, oszlop);
    else this.fuggoUgras.set(ut, { sor, oszlop });
  }

  fuggoUgrasKap(ut: string): { sor: number; oszlop?: number } | null {
    const v = this.fuggoUgras.get(ut) ?? null;
    this.fuggoUgras.delete(ut);
    return v;
  }

  /** A fül elmentett CodeMirror-állapota (ha ugyanahhoz a jegyzethez tartozik). */
  allapot(fulId: string, ut: string): TaroltAllapot | null {
    const t = this.tarolt.get(fulId + '\0' + ut);
    if (!t || t.ut !== ut) return null;
    this.tarolt.delete(fulId + '\0' + ut);
    this.tarolt.set(fulId + '\0' + ut, t);
    return t;
  }

  tarol(fulId: string, t: TaroltAllapot): void {
    this.tarolt.delete(fulId + '\0' + t.ut);
    this.tarolt.set(fulId + '\0' + t.ut, t);
    while (this.tarolt.size > MAX_TAROLT) this.tarolt.delete(this.tarolt.keys().next().value as string);
  }
}

export const szerkesztok = new Szerkesztok();
