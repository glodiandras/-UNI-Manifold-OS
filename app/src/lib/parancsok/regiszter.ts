// A parancsregiszter (C07): minden funkció ide regisztrál, és innen fut — a ⌘P palettából, a
// gyorsbillentyűről és a gombokról egyaránt. A későbbi modulok (C08–C30) ugyanezt az API-t használják:
//
//   const le = regiszter.regisztral({ id: 'kartya.ebbol', nev: 'Kártyák ebből', kategoria: 'Tanulás',
//                                     futtat: () => … });
//   …
//   le(); // leiratkozás (pl. a nézet bezárásakor)

import type { IconNode } from 'lucide';
import { hibaSzoveg } from '../core/api';
import { ertesitesek } from '../ertesites/ertesites.svelte';
import { normalizalLeiras } from './billentyuk';

export interface Parancs {
  /** Egyedi, pontokkal tagolt azonosító: `<modul>.<művelet>`. */
  id: string;
  /** A palettában megjelenő név (magyarul, igével vagy főnévvel kezdve). */
  nev: string;
  kategoria?: string;
  /** Pl. „Mod+Shift+M”; ütközés esetén a regisztráció hibát dob. */
  billentyu?: string;
  ikon?: IconNode;
  /** Ha hamisat ad, a parancs nem látszik a palettában és a billentyűje sem fut. */
  elerheto?: () => boolean;
  /** Megjelenjen-e a palettában (alap: igen). */
  palettaban?: boolean;
  /** Nyitott modális átfedés (paletta, váltó) alatt is fusson-e a billentyűje. */
  atfedesben?: boolean;
  /** A billentyűje a szerkesztőben (CodeMirror) nem fut: ott a CM azonos akkordja nyer (pl. ⌥⌘↓ = kurzor lefelé); a
   *  palettából és a szerkesztőn kívül a parancs fut. */
  szerkesztoNyer?: boolean;
  futtat: () => void | Promise<void>;
}

type Figyelo = () => void;

/** Honnan indult a parancs (a tracker használati mérése, C27): a mérés csak az azonosítót és ezt a forrást látja. */
export type ParancsForras = 'billentyu' | 'paletta' | 'menu' | 'gomb' | 'hej' | 'egyeb';
type Megfigyelo = (id: string, forras: ParancsForras) => void;

export class Regiszter {
  private readonly parancsok = new Map<string, Parancs>();
  private readonly akkordok = new Map<string, string>();
  private readonly figyelok = new Set<Figyelo>();
  /** Minden sikeres futás után (a legutóbbiak listájához). */
  futasUtan: ((id: string) => void) | null = null;
  private readonly megfigyelok = new Set<Megfigyelo>();

  /** Megfigyelő minden sikeres futásra (az azonosítóval és a forrással); a `futasUtan` mellett él. */
  megfigyel(f: Megfigyelo): () => void {
    this.megfigyelok.add(f);
    return () => this.megfigyelok.delete(f);
  }

  regisztral(p: Parancs): () => void {
    if (!/^[a-z0-9-]+(\.[a-z0-9-]+)+$/.test(p.id)) throw new Error(`hibás parancsazonosító: ${p.id}`);
    if (this.parancsok.has(p.id)) throw new Error(`már regisztrált parancs: ${p.id}`);
    let akkord: string | undefined;
    if (p.billentyu) {
      akkord = normalizalLeiras(p.billentyu);
      const masik = this.akkordok.get(akkord);
      if (masik) throw new Error(`a(z) ${p.billentyu} billentyű már foglalt: ${masik}`);
    }
    const tarolt: Parancs = akkord ? { ...p, billentyu: akkord } : { ...p };
    this.parancsok.set(p.id, tarolt);
    if (akkord) this.akkordok.set(akkord, p.id);
    this.jelez();
    return () => {
      if (this.parancsok.get(p.id) !== tarolt) return;
      this.parancsok.delete(p.id);
      if (akkord) this.akkordok.delete(akkord);
      this.jelez();
    };
  }

  /** Több parancs egyszerre; egy leiratkozó mindegyikre. */
  regisztralMind(lista: Parancs[]): () => void {
    const le = lista.map((p) => this.regisztral(p));
    return () => le.forEach((f) => f());
  }

  kap(id: string): Parancs | undefined {
    return this.parancsok.get(id);
  }

  elerheto(p: Parancs): boolean {
    try {
      return p.elerheto ? p.elerheto() : true;
    } catch {
      return false;
    }
  }

  /** A palettában látható, épp elérhető parancsok. */
  lista(): Parancs[] {
    return [...this.parancsok.values()].filter((p) => p.palettaban !== false && this.elerheto(p));
  }

  akkordhoz(kanonikusAkkord: string): Parancs | undefined {
    const id = this.akkordok.get(kanonikusAkkord);
    return id ? this.parancsok.get(id) : undefined;
  }

  /** Futtatás azonosító szerint; hamis, ha nincs ilyen vagy nem elérhető. */
  futtat(id: string, forras: ParancsForras = 'egyeb'): boolean {
    const p = this.parancsok.get(id);
    if (!p || !this.elerheto(p)) return false;
    // a parancs hibája (szinkron vagy aszinkron) a felhasználónak is látszik, nem csak a konzolon
    const hibaJelez = (e: unknown) => {
      console.error(`parancs hiba: ${id}`, e);
      ertesitesek.ertesit({ szint: 'hiba', cim: `A parancs nem sikerült: ${p.nev}`, szoveg: hibaSzoveg(e) });
    };
    try {
      const r = p.futtat();
      if (r instanceof Promise) r.catch(hibaJelez);
    } catch (e) {
      hibaJelez(e);
    }
    this.futasUtan?.(id);
    for (const f of this.megfigyelok) {
      try {
        f(id, forras);
      } catch (e) {
        console.error('parancs-megfigyelő hiba', e); // a megfigyelő hibája nem akasztja a parancsot
      }
    }
    return true;
  }

  feliratkoz(f: Figyelo): () => void {
    this.figyelok.add(f);
    return () => this.figyelok.delete(f);
  }

  private jelez() {
    for (const f of this.figyelok) f();
  }
}

export const regiszter = new Regiszter();
