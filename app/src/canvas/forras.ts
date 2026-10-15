// A canvas szövegének forrása (C14): a fájl a `Dokumentum`-án át él (automatikus mentés, hash-alapú ütközés,
// külső változás, kilépési mentés — ugyanaz az egy írási út, mint a jegyzeté). A nézet modellt kap és modellt ad
// vissza; a szöveg felé csak a bájthű író (`iro.foltoz`) visz, így a nem érintett bájtok maradnak.

import { ChangeSet } from '@codemirror/state';
import type { Csatolt, Dokumentum, Dokumentumok } from '../szerkeszto/dokumentum/dokumentum.svelte';
import { csere } from '../szerkeszto/dokumentum/kulonbseg';
import { foltoz, IroHiba } from './iro';
import { beolvas, type Beolvasas, type Vaszon } from './modell';

/** A nyitott szövegkártya gépelése után ennyi csenddel kerül a szöveg a dokumentumba (az automatikus mentés 1 s-a előtt). */
export const KARTYA_ATVETEL_MS = 400;

export type IrasEredmeny = { ok: true; valtozott: boolean } | { ok: false; hiba: string };

export class CanvasForras {
  private beolvasas: Beolvasas;
  private readonly figyelok = new Set<() => void>();
  private readonly le: () => void;
  private readonly csatolt: Csatolt;
  /** a nézet átadója: a lezárás/kilépés/⌘S előtt a nyitott szövegkártya szövegét a dokumentumba írja (T004) */
  private fuggo: (() => void) | null = null;
  /** nyitott szövegkártya-szerkesztő van: a szöveg még nincs a dokumentumban, a core felé mégis mentetlen (28(c)) */
  private kartyaNyitva = false;
  /** a nyitott kártya szövegének késleltetett átvétele a dokumentumba (E12): így az automatikus mentés is látja */
  private atvetelIdozito: ReturnType<typeof setTimeout> | null = null;

  private constructor(
    readonly dok: Dokumentum,
    private readonly dk: Dokumentumok,
  ) {
    this.beolvasas = beolvas(this.szoveg());
    this.csatolt = {
      alkalmaz: () => {
        // más nézetből, a lemezről (külső változás) vagy az ütközés feloldásából jött szöveg
        this.beolvasas = beolvas(this.szoveg());
        for (const f of [...this.figyelok]) f();
      },
      mentesElott: () => this.fuggo?.(),
      mentetlen: () => this.kartyaNyitva,
    };
    this.le = dok.csatol(this.csatolt);
  }

  static async nyit(ut: string, dk: Dokumentumok): Promise<CanvasForras> {
    return new CanvasForras(await dk.megnyit(ut), dk);
  }

  get ut(): string {
    return this.dok.ut;
  }

  /** a jelenlegi szöveg (LF-es, ahogy a `Dokumentum` tartja) */
  szoveg(): string {
    return this.dok.szoveg.toString();
  }

  /** a jelenlegi modell és az olvasás hibái */
  get allapot(): Beolvasas {
    return this.beolvasas;
  }

  /** miért nem írható (magyar mondat), vagy `null` */
  csakOlvashato(): string | null {
    if (this.dok.csakOlvashato) return this.dok.csakOlvashato;
    if (this.beolvasas.hiba) return `${this.beolvasas.hiba} A canvas javításáig csak olvasható.`;
    if (this.dok.allapot === 'eltunt') return 'A fájl közben eltűnt (törölték vagy áthelyezték).';
    return null;
  }

  /** Az új modell beírása a dokumentumba (a mentés a dokumentum ütemezésével megy). A szöveg csak a
   *  megváltozott részében íródik át; ha a foltozás nem a várt JSON-t adná, semmi nem változik. */
  ir(uj: Vaszon): IrasEredmeny {
    const ok = this.csakOlvashato();
    if (ok) return { ok: false, hiba: ok };
    if (this.dok.allapot === 'utkozes')
      return { ok: false, hiba: 'A canvas közben megváltozott a lemezen; előbb az ütközést kell feloldani.' };
    const regi = this.szoveg();
    let szoveg: string;
    try {
      szoveg = foltoz(regi, uj);
    } catch (e) {
      return { ok: false, hiba: e instanceof IroHiba || e instanceof Error ? e.message : String(e) };
    }
    if (szoveg === regi) return { ok: true, valtozott: false };
    const c = csere(this.dok.szoveg, szoveg);
    if (c) {
      const cs = ChangeSet.of([c], this.dok.szoveg.length);
      this.dok.valtozott(cs, cs.apply(this.dok.szoveg), this.csatolt);
    }
    this.beolvasas = { vaszon: uj, hiba: null, hely: null, figyelmeztetesek: this.beolvasas.figyelmeztetesek };
    return { ok: true, valtozott: true };
  }

  /** A nézet függő tartalmának átadója (a nyitott szövegkártya-szerkesztő): a `Dokumentum` lezárás és kilépés előtt hívja. */
  fuggoBeallit(f: (() => void) | null): void {
    this.fuggo = f;
  }

  /** A szövegkártya-szerkesztő nyílik/zárul (C29.7b): a nyitott kártya szövege a kommitig „mentetlen” a core felé, hogy a gép
   *  ne írhasson a fájlra (és a kommit ne a gép átírt modelljére épüljön). */
  kartyaSzerkesztes(nyitva: boolean): void {
    if (this.kartyaNyitva === nyitva) return;
    this.kartyaNyitva = nyitva;
    if (!nyitva && this.atvetelIdozito) {
      clearTimeout(this.atvetelIdozito);
      this.atvetelIdozito = null;
    }
    this.dok.mentetlenValtozott();
  }

  /** A nyitott szövegkártya szövege változott (gépelés): `KARTYA_ATVETEL_MS` csend után átkerül a dokumentumba, és onnan az
   *  automatikus mentésbe (E12) — nem csak a kártya bezárásakor. */
  kartyaValtozott(): void {
    if (this.atvetelIdozito) clearTimeout(this.atvetelIdozito);
    this.atvetelIdozito = setTimeout(() => {
      this.atvetelIdozito = null;
      this.fuggo?.();
    }, KARTYA_ATVETEL_MS);
  }

  /** a szöveg kívülről változott: a nézet újraolvassa a modellt */
  figyel(f: () => void): () => void {
    this.figyelok.add(f);
    return () => void this.figyelok.delete(f);
  }

  async lezar(): Promise<void> {
    if (this.atvetelIdozito) clearTimeout(this.atvetelIdozito);
    this.atvetelIdozito = null;
    this.le();
    this.figyelok.clear();
    await this.dk.elenged(this.dok);
  }
}
