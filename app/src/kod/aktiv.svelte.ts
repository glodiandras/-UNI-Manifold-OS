// A nyitott `.cpp` fülek (C36a-UI): az aktív fül a parancsok célja (⌘R, ⇧⌥F), a többi a jegyzetből indított ⌘R-nél
// számít (a már nyitott `.cpp` fül kerül elő, nem nyílik újabb). A `.cpp` fül nem `SzerkesztoPeldany`: a Markdown-
// parancsok (⌘B, ⌘I, ⌘⇧H …) nem érik el.

import type { EditorView } from '@codemirror/view';

export interface KodPeldany {
  readonly ut: string;
  nezet(): EditorView | null;
  /** kivárja/elindítja a mentést; hamis, ha a fájl mentetlen maradt (ütközés, hiba, csak olvasható) */
  mentes(): Promise<boolean>;
  /** írható-e most (nem csak olvasható, nincs ütközés, nem tűnt el) */
  irhato(): boolean;
  ugras(sor: number, oszlop?: number): void;
}

export class KodFulok {
  aktiv = $state.raw<KodPeldany | null>(null);
  private readonly nyitott = new Set<KodPeldany>();

  beallit(p: KodPeldany): void {
    this.nyitott.add(p);
    this.aktiv = p;
  }

  elenged(p: KodPeldany): void {
    if (this.aktiv === p) this.aktiv = null;
  }

  megszunt(p: KodPeldany): void {
    this.elenged(p);
    this.nyitott.delete(p);
  }

  /** egy nyitott `.cpp` fül az úton (aktív vagy háttérben) */
  kap(ut: string): KodPeldany | undefined {
    for (const p of this.nyitott) if (p.ut === ut) return p;
    return undefined;
  }
}

export const kodFulok = new KodFulok();
