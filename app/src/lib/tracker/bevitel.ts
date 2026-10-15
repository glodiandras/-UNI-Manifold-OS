// Az aktív idő mérése (C27, 38. döntés): egy másodperc „aktív”, ha az ablak elöl van (látható és fókuszban), az utolsó bevitel
// (billentyű, kattintás, egér, görgetés — és a lejátszó játszása, mert az előadásvideó nézése tanulás) 60 mp-en belül volt, és
// van számító fül (minden fájl-fül és a gráf: `aktivFul.ts`). A másodpercet az aktív fül útjára írja. Az ütemenkénti időugrás
// plafonos (2 s): az alvó gép vagy a kifagyó ütem ideje nem számít.

export const BEVITEL_ABLAK_MS = 60_000;
export const UTEM_MS = 1000;
export const UGRAS_PLAFON_MS = 2000;

export interface AktivIdoFuggosegek {
  most: () => number;
  aktivUt: () => string | null;
  lathato: () => boolean;
  fokuszban: () => boolean;
  /** Az aktív fülön lejátszó játszik: ez bevitelnek számít (38. döntés). Elhagyható (alap: nem). */
  jatszik?: () => boolean;
  /** A kész másodpercek: (út, másodperc, nap). */
  jelent: (ut: string, mp: number, nap: string) => void;
  nap: () => string;
}

export class AktivIdo {
  private utolsoBevitel = Number.NEGATIVE_INFINITY;
  private utolsoUtem: number | null = null;
  private tort = 0; // a le nem könyvelt ezredmásodpercek
  private tortUt: string | null = null;

  constructor(private readonly f: AktivIdoFuggosegek) {}

  bevitel(): void {
    this.utolsoBevitel = this.f.most();
  }

  /** Egy ütem: a két ütem közti idő aktív, ha a feltételek az ütem pillanatában teljesülnek. */
  utem(): void {
    const most = this.f.most();
    const dt = this.utolsoUtem === null ? 0 : Math.min(Math.max(0, most - this.utolsoUtem), UGRAS_PLAFON_MS);
    this.utolsoUtem = most;
    const ut = this.f.aktivUt();
    if (this.f.jatszik?.()) this.utolsoBevitel = most; // a lejátszás bevitel: a bevitel nélküli videónézés sem szakad meg
    const aktiv = !!ut && this.f.lathato() && this.f.fokuszban() && most - this.utolsoBevitel <= BEVITEL_ABLAK_MS;
    if (!aktiv || !ut) return;
    if (this.tortUt !== ut) {
      this.tort = 0; // fülváltás: a törtrész (< 1 s) nem viszi át az időt másik jegyzetre
      this.tortUt = ut;
    }
    this.tort += dt;
    const mp = Math.floor(this.tort / 1000);
    if (mp > 0) {
      this.f.jelent(ut, mp, this.f.nap());
      this.tort -= mp * 1000;
    }
  }
}

/** Az éles bekötés: bevitel-figyelők (capture, passzív) és az 1 s-os ütem. A visszaadott függvény leszed mindent. */
export function aktivIdoFigyelo(f: AktivIdoFuggosegek): () => void {
  const ido = new AktivIdo(f);
  const jel = () => ido.bevitel();
  const esemenyek = ['keydown', 'pointerdown', 'pointermove', 'wheel'] as const;
  for (const e of esemenyek) window.addEventListener(e, jel, { passive: true, capture: true });
  const t = setInterval(() => ido.utem(), UTEM_MS);
  return () => {
    clearInterval(t);
    for (const e of esemenyek) window.removeEventListener(e, jel, { capture: true });
  };
}
