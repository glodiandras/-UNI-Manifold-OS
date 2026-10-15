// Az aktív PDF- vagy lejátszó-nézet (C16): a ⌘P parancsai ezen futnak (a `szerkesztok.aktiv` párja). Az `utolso`
// az utoljára aktív, még nyitott nézet: a jegyzet mellett osztásban futó videó időkódja a jegyzetből is beszúrható
// (⇧⌘I), mert a fókusz ilyenkor a szerkesztőben áll.

export type MediaParancs =
  | 'beszur'
  | 'kereses'
  | 'kov-oldal'
  | 'elozo-oldal'
  | 'ugras'
  | 'belyegek'
  | 'nagyit'
  | 'kicsinyit'
  | 'oldalszelesseg'
  | 'egesz-oldal'
  | 'lejatszas'
  | 'elore'
  | 'hatra'
  | 'gyorsabb'
  | 'lassabb'
  | 'felirat'
  | 'atirat';

export interface MediaPeldany {
  readonly ut: string;
  readonly tipus: 'pdf' | 'lejatszo';
  parancs(p: MediaParancs): void;
}

class MediaNezetek {
  aktiv = $state.raw<MediaPeldany | null>(null);
  /** a nyitott nézetek az aktiválás sorrendjében (az utolsó a legutóbbi) */
  private nyitott: MediaPeldany[] = []; // nem reaktív: csak parancsfutáskor olvassuk
  /** a játszó lejátszók (38. döntés, T074: a lejátszás az aktív idő bevitele); nem reaktív: az ütem másodpercenként olvassa */
  private jatszok = new Set<MediaPeldany>();

  get utolso(): MediaPeldany | null {
    return this.nyitott.at(-1) ?? null;
  }

  /** Megnyílt (még nem aktív panelben is): a lista elejére, hogy a később aktivált nézet előtte maradjon. */
  bejegyez(p: MediaPeldany): void {
    if (!this.nyitott.includes(p)) this.nyitott = [p, ...this.nyitott];
  }

  beallit(p: MediaPeldany): void {
    this.aktiv = p;
    this.nyitott = [...this.nyitott.filter((x) => x !== p), p];
  }

  elenged(p: MediaPeldany): void {
    if (this.aktiv === p) this.aktiv = null;
  }

  megszunt(p: MediaPeldany): void {
    this.elenged(p);
    this.nyitott = this.nyitott.filter((x) => x !== p);
    this.jatszok.delete(p);
  }

  /** A lejátszó játszik-e (play/pause eseményre). */
  jatszik(p: MediaPeldany, be: boolean): void {
    if (be) this.jatszok.add(p);
    else this.jatszok.delete(p);
  }

  /** Játszik-e lejátszó ezen az úton (az aktív fül útjára kérdezve). */
  jatszikUt(ut: string): boolean {
    for (const p of this.jatszok) if (p.ut === ut) return true;
    return false;
  }

  /** A parancs célja: az aktív nézet, különben (a beszúrásnál) az utoljára aktív, még nyitott. */
  cel(tipus?: MediaPeldany['tipus'], utolsoIs = false): MediaPeldany | null {
    const p = this.aktiv ?? (utolsoIs ? this.utolso : null);
    return p && (!tipus || p.tipus === tipus) ? p : null;
  }
}

export const mediaNezetek = new MediaNezetek();
