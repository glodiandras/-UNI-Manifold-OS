// Az aktív canvas-nézet (C14): a ⌘P canvas-parancsai ezen futnak (a CodeMirror-szerkesztő `szerkesztok.aktiv`-jának
// párja). Egyszerre egy: az, amelyik fül utoljára lett aktív.

export type CanvasParancs =
  | 'uj-szoveg'
  | 'uj-fajl'
  | 'uj-link'
  | 'uj-csoport'
  | 'mindent-mutat'
  | 'nagyitas-100'
  | 'nagyit'
  | 'kicsinyit'
  | 'racs'
  | 'visszavon'
  | 'ujra'
  | 'torol'
  | 'duplikal'
  | 'mind'
  | 'masol'
  | 'kivag'
  | 'beillesztes'
  | 'kijeloles-mutat'
  | 'objektum-igazitas'
  | 'jegyzette'
  | 'alcel'
  | 'helyi-menu';

export interface VaszonPeldany {
  readonly ut: string;
  parancs(p: CanvasParancs): void;
  irhato(): boolean;
  vanKijeloles(): boolean;
}

class Canvasok {
  aktiv = $state.raw<VaszonPeldany | null>(null);

  beallit(p: VaszonPeldany): void {
    this.aktiv = p;
  }

  elenged(p: VaszonPeldany): void {
    if (this.aktiv === p) this.aktiv = null;
  }
}

export const canvasok = new Canvasok();
