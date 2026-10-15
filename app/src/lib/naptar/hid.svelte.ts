// A naptár-engedély natív hídja (C29). Az EventKit-engedélyt a Manifold.app GUI-folyamata kéri (a rendszer így a
// Manifoldnak tulajdonítja): a felület `naptar-engedely` üzenetet küld a héjnak, a héj a rendszer ablakát mutatja,
// majd a `window.manifold.naptarEngedely({esemeny, emlekezteto})` függvényt hívja (hibánál `{hiba}`). Héj nélkül
// (böngésző, fejlesztés) az engedély nem kérhető: `elerheto` hamis. A válasz ide kerül, és a figyelők újratöltenek.

import { hejbenFut, hejnek } from '../core/hej';
import type { EngedelyAllapot, NaptarEngedelyValasz } from './tipusok';

const ALLAPOTOK: readonly string[] = ['nincs_dontes', 'korlatozott', 'megtagadva', 'engedelyezve', 'csak_iras', 'ismeretlen'];
/** A rendszer ablakára várva ennyi után újra kérhető a gomb (a héj egy futó kérést úgyis összevon). */
const KERES_IDOKORLAT_MS = 120_000;

const allapot = (v: unknown): EngedelyAllapot | null => (typeof v === 'string' && ALLAPOTOK.includes(v) ? (v as EngedelyAllapot) : null);

export class NaptarHid {
  /** A héj legutóbb jelentett engedélye; `null`, amíg nem jött válasz. */
  engedely = $state<{ esemeny: EngedelyAllapot | null; emlekezteto: EngedelyAllapot | null } | null>(null);
  hiba = $state<string | null>(null);
  kerdesben = $state(false);
  private readonly figyelok = new Set<(v: NaptarEngedelyValasz, kerdesre: boolean) => void>();
  private idozito: ReturnType<typeof setTimeout> | null = null;

  /** Van-e héj, amely az engedélyt kérni tudja. */
  get elerheto(): boolean {
    return hejbenFut();
  }

  /** Az engedély kérése (a rendszer párbeszédablakot mutat). Hamis, ha nincs héj. */
  kerd(esemeny = true, emlekezteto = true): boolean {
    if (!hejbenFut()) return false;
    this.kerdesben = true;
    this.hiba = null;
    if (this.idozito) clearTimeout(this.idozito);
    this.idozito = setTimeout(() => {
      this.idozito = null;
      this.kerdesben = false;
    }, KERES_IDOKORLAT_MS);
    hejnek({ tipus: 'naptar-engedely', esemeny, emlekezteto });
    return true;
  }

  /** Az engedély állapotának lekérése kérés nélkül (a héj `naptarEngedely`-vel válaszol). */
  allapotKer(): void {
    hejnek({ tipus: 'naptar-allapot' });
  }

  /** A héj válasza (`window.manifold.naptarEngedely`). Hibás alakú értéket csendben eldob. */
  fogad(v: unknown): void {
    if (!v || typeof v !== 'object') return;
    const r = v as NaptarEngedelyValasz;
    const kerdesre = this.kerdesben;
    this.engedely = { esemeny: allapot(r.esemeny), emlekezteto: allapot(r.emlekezteto) };
    this.hiba = typeof r.hiba === 'string' && r.hiba ? r.hiba : null;
    this.kerdesben = false;
    if (this.idozito) clearTimeout(this.idozito);
    this.idozito = null;
    for (const f of this.figyelok) {
      try {
        f(r, kerdesre);
      } catch (e) {
        console.error('naptár-híd figyelő hiba', e);
      }
    }
  }

  /** A figyelő a válasz mellett azt is megkapja, hogy kérésre (`kerd`) érkezett-e. */
  figyel(f: (v: NaptarEngedelyValasz, kerdesre: boolean) => void): () => void {
    this.figyelok.add(f);
    return () => this.figyelok.delete(f);
  }
}

export const naptarHid = new NaptarHid();
