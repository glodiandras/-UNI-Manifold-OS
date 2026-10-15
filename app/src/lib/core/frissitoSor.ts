// A `vault_valtozas` utáni újralekérdezések közös ütemezője (C33, T070, A2-teljesitmeny-2).
//
// Egy mentés után a látszó panelek egyszerre kértek a core-tól (kapcsolatok 3 kérés, Bases 1, gráf 2): a core-ban a
// párhuzamos index-olvasók egymást 5–25-szörösen lassították. Itt a panelek a frissítésüket egy kulcs alatt kérik; a
// késleltetés (a panel saját csendje) után a feladatok **sorban**, egyszerre egy fut, és a kulcsonként legutóbbi kérés
// számít (ugyanaz a panel nem áll kétszer a sorban). A felhasználói műveletre (fülváltás, szűrő, nézetváltás) a panel
// továbbra is azonnal kér; ez csak a vault változására induló háttér-frissítés útja.

type Feladat = () => Promise<unknown> | unknown;

/** Egy tétel legfeljebb ennyi ideig tartja a sort: a sosem válaszoló kérés után a sor továbbmegy (a tétel a háttérben
 *  befejeződhet, de a többi panel frissítése nem vár rá). */
export const TETEL_KORLAT = 30_000;

export class FrissitoSor {
  private readonly varakozo = new Map<string, Feladat>();
  private readonly idozitok = new Map<string, ReturnType<typeof setTimeout>>();
  private fut = false;
  /** Hány feladat futott le (a teszt és a mérés olvassa). */
  lefutott = 0;
  /** A legtöbb egyszerre futó feladat (a sor egyesével futtat: 1). */
  csucs = 0;
  private aktiv = 0;

  constructor(private readonly tetelKorlat = TETEL_KORLAT) {}

  /** A `kulcs` frissítése `kesleltetes` ms csend után, a sorban (a kulcs korábbi, még nem indult kérését felváltja). */
  ker(kulcs: string, feladat: Feladat, kesleltetes = 0): void {
    const regi = this.idozitok.get(kulcs);
    if (regi) clearTimeout(regi);
    this.idozitok.set(
      kulcs,
      setTimeout(() => {
        this.idozitok.delete(kulcs);
        this.varakozo.delete(kulcs); // a Map sorrendje: a friss kérés a sor végére kerül
        this.varakozo.set(kulcs, feladat);
        void this.pumpa();
      }, kesleltetes),
    );
  }

  /** A `kulcs` függő kérésének elvetése (a panel bezárult). */
  elvet(kulcs: string): void {
    const t = this.idozitok.get(kulcs);
    if (t) clearTimeout(t);
    this.idozitok.delete(kulcs);
    this.varakozo.delete(kulcs);
  }

  /** Függő (időzített vagy sorban álló) kérések száma. */
  get fuggo(): number {
    return this.idozitok.size + this.varakozo.size;
  }

  private async pumpa(): Promise<void> {
    if (this.fut) return;
    this.fut = true;
    try {
      while (this.varakozo.size) {
        const [kulcs, feladat] = this.varakozo.entries().next().value as [string, Feladat];
        this.varakozo.delete(kulcs);
        this.aktiv++;
        this.csucs = Math.max(this.csucs, this.aktiv);
        let ido: ReturnType<typeof setTimeout> | null = null;
        try {
          await Promise.race([
            Promise.resolve().then(feladat),
            new Promise<void>((r) => (ido = setTimeout(r, this.tetelKorlat))),
          ]);
        } catch {
          // a panel maga kezeli és mutatja a hibáját; a sor megy tovább
        } finally {
          if (ido) clearTimeout(ido);
          this.aktiv--;
          this.lefutott++;
        }
      }
    } finally {
      this.fut = false;
    }
  }
}

export const frissitoSor = new FrissitoSor();
