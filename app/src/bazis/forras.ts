// A `.base` szövegének forrása (C12): a nézet nem tudja, hol él a szöveg. Három forrás:
//   - `fajlForras(ut)`: egy `.base` fájl a `Dokumentum`-án át (automatikus mentés, hash-alapú ütközés, élő frissítés);
//   - `blokkForras(…)`: a jegyzet ```` ```base ```` blokkja (a befoglaló jegyzet tranzakciója; a 7. lépésben, `beagyazas.ts`);
//   - `rogzitettForras(…)`: az Olvasó rögzített szövege (a beállítás csak memóriában változik).
// Az írás **egyetlen úton** megy: a core `modosit` végpontja csak az új szöveget számolja.

import { ChangeSet } from '@codemirror/state';
import type { Csatolt, Dokumentumok } from '../szerkeszto/dokumentum/dokumentum.svelte';
import { csere } from '../szerkeszto/dokumentum/kulonbseg';
import { szerkesztok } from '../szerkeszto/szerkesztok.svelte';
import { t } from '../lib/i18n';

export interface BazisForras {
  /** a `this` fájlja: a `.base` útja (fülön), vagy a befoglaló jegyzeté (blokkban, beágyazva) */
  readonly ez: string | null;
  /** a `.base` jelenlegi szövege (LF-es) */
  szoveg(): string;
  /** miért nem írható (magyar mondat), vagy `null`, ha írható */
  csakOlvashato(): string | null;
  /** a nézet celláit (a sorok jegyzeteit) szerkeszteni lehet-e: az Olvasóban nem (nincs megadva: igen) */
  cellaIras?(): boolean;
  /** az új szöveg beírása; igaz, ha megtörtént (és mentődött) */
  ir(uj: string): Promise<boolean>;
  /** a szöveg megváltozott (más nézetből, külső szerkesztésből): a lekérdezés újra kell */
  figyel(f: () => void): () => void;
  lezar(): Promise<void>;
}

class Figyelok {
  private readonly lista = new Set<() => void>();
  add(f: () => void): () => void {
    this.lista.add(f);
    return () => void this.lista.delete(f);
  }
  jelez(): void {
    for (const f of [...this.lista]) f();
  }
  urit(): void {
    this.lista.clear();
  }
}

/** Egy `.base` fájl a `Dokumentum`-án át. A dokumentum nem Markdown-függő: a mentés, az ütközés és a külső
 *  változás ugyanúgy megy, mint a jegyzetnél; az utolsó nézet lezárása pillanatképet készít. */
export async function fajlForras(
  ut: string,
  o: { ez?: string | null; dk?: Dokumentumok } = {},
): Promise<BazisForras> {
  const dk = o.dk ?? szerkesztok.dokumentumok;
  const dok = await dk.megnyit(ut);
  const figyelok = new Figyelok();
  const csatolt: Csatolt = {
    alkalmaz() {
      figyelok.jelez();
    },
  };
  const le = dok.csatol(csatolt);
  const ok = (): string | null =>
    dok.csakOlvashato ??
    (dok.allapot === 'utkozes'
      ? t('A fájl közben megváltozott a lemezen; az ütközést előbb a szerkesztőben kell feloldani.')
      : dok.allapot === 'eltunt'
        ? t('A fájl közben eltűnt (törölték vagy áthelyezték).')
        : null);
  return {
    ez: o.ez === undefined ? ut : o.ez, // beágyazva: a befoglaló jegyzet a `this`
    szoveg: () => dok.szoveg.toString(),
    csakOlvashato: ok,
    async ir(uj) {
      if (ok()) return false;
      const c = csere(dok.szoveg, uj);
      if (!c) return true;
      const cs = ChangeSet.of([c], dok.szoveg.length);
      dok.valtozott(cs, cs.apply(dok.szoveg), csatolt);
      figyelok.jelez();
      return (await dok.ment()).ok;
    },
    figyel: (f) => figyelok.add(f),
    async lezar() {
      le();
      figyelok.urit();
      await dk.elenged(dok);
    },
  };
}

/** Rögzített szöveg (Olvasó): az írás csak memóriában változtat, a fájlba semmi nem kerül. */
export function rogzitettForras(szoveg: string, ez: string | null): BazisForras {
  let jelenlegi = szoveg;
  const figyelok = new Figyelok();
  return {
    ez,
    szoveg: () => jelenlegi,
    csakOlvashato: () => null,
    cellaIras: () => false,
    async ir(uj) {
      jelenlegi = uj;
      figyelok.jelez();
      return true;
    },
    figyel: (f) => figyelok.add(f),
    async lezar() {
      figyelok.urit();
    },
  };
}

/** A jegyzet ```` ```base ```` blokkjának forrása (Live Preview): az írás a `blokk.csere`-n át a befoglaló jegyzet
 *  **egyetlen tranzakciója**. A blokk kódja nem végződik sortöréssel, ezért az új szöveg záró `\n`-je lekerül. A
 *  `beallit` a widget `updateDOM`-ja hívja, ha a blokk szövege más úton (gépelés a forrásban) változott. Blokk
 *  nélkül (Olvasó) a változás csak memóriában marad. */
export interface BlokkForras extends BazisForras {
  beallit(szoveg: string): void;
}

export function blokkForras(
  ez: string | null,
  szoveg: string,
  blokk?: { csakOlvashato: boolean; csere(uj: string): boolean },
): BlokkForras {
  let jelenlegi = szoveg;
  const figyelok = new Figyelok();
  return {
    ez,
    szoveg: () => jelenlegi,
    csakOlvashato: () => (blokk?.csakOlvashato ? t('A jegyzet csak olvasható.') : null),
    cellaIras: () => !!blokk && !blokk.csakOlvashato,
    async ir(uj) {
      const kod = uj.replace(/\n$/, '');
      if (kod === jelenlegi) return true;
      if (blokk && !blokk.csere(kod)) return false;
      jelenlegi = kod;
      figyelok.jelez();
      return true;
    },
    beallit(uj) {
      if (uj === jelenlegi) return;
      jelenlegi = uj;
      figyelok.jelez();
    },
    figyel: (f) => figyelok.add(f),
    async lezar() {
      figyelok.urit();
    },
  };
}
