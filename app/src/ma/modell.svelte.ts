// A „Ma” oldal adata (C15): `GET /api/ma`. A betöltés a nézet megjelenésekor, a WS-eseményre (a vault és az index
// változása), láthatóvá váláskor és éjfélkor történik — de csak látszó nézetnek: nyugalomban és rejtett lapon
// semmi nem ütemez (kivéve az éjfélig tartó egyetlen időzítőt, amely csak látszó nézet mellett él). Ha a nézet
// éppen nem látszik, az adat csak elavultnak jelölődik, és a következő megjelenéskor tölt.

import { kerdez } from '../lib/core/api';
import type { CoreKapcsolat } from '../lib/core/ws.svelte';
import { naptarApi } from '../lib/naptar/api';
import { ejfelig, napKulcs } from './datum';
import type { MaValasz } from './tipusok';

export class MaAdat {
  adat = $state.raw<MaValasz | null>(null);
  hiba = $state<string | null>(null);
  betoltve = $state(false);

  private latszok = 0;
  private elavult = true;
  private idozito: ReturnType<typeof setTimeout> | null = null;
  private ejfelIdozito: ReturnType<typeof setTimeout> | null = null;
  private sorszam = 0;
  private nap = napKulcs(new Date());
  /** Az engedély friss állapotát (a segédtől) egyszer kérjük, ha a core még nem ismeri (a szinkron-kör 60 s késleltetéssel indul). */
  private engedelyProba = false;

  constructor(
    private readonly most: () => Date = () => new Date(),
    private readonly lathato: () => boolean = () => typeof document === 'undefined' || document.visibilityState !== 'hidden',
  ) {}

  /** Egy Ma-nézet megjelent: tölt, ha az adat elavult; a visszaadott függvény jelzi az eltűnését. */
  megjelenik(): () => void {
    this.latszok++;
    if (this.elavult || !this.betoltve || this.nap !== napKulcs(this.most())) void this.frissit();
    this.ejfelUtemez();
    let kesz = false;
    return () => {
      if (kesz) return;
      kesz = true;
      this.latszok = Math.max(0, this.latszok - 1);
      if (!this.latszok) {
        if (this.idozito) clearTimeout(this.idozito);
        if (this.ejfelIdozito) clearTimeout(this.ejfelIdozito);
        this.idozito = this.ejfelIdozito = null;
      }
    };
  }

  async frissit(): Promise<void> {
    const en = ++this.sorszam;
    this.nap = napKulcs(this.most());
    this.elavult = false; // a töltés közben érkező változás újra elavulttá teszi: az nem veszhet el a válasz érkezésekor
    try {
      const v = await kerdez<MaValasz>('/api/ma', { idokorlat: 15000 });
      if (en !== this.sorszam) return;
      this.adat = v;
      this.hiba = null;
      this.betoltve = true;
      this.engedelyEllenorzes(v);
    } catch (e) {
      if (en !== this.sorszam) return;
      this.hiba = e instanceof Error ? e.message : String(e);
      this.betoltve = true;
      this.elavult = true;
    }
  }

  /** Ha a core még nem ismeri a naptár-engedélyt, egyszer rákérdez (`?frissit=1`), majd újratölt; a hiba csendes. */
  private engedelyEllenorzes(v: MaValasz): void {
    const s = v.naptar_allapot;
    // a `naptar_allapot` mindig hordoz `hiba` kulcsot (null), ezért a hibás szakaszt a `seged` hiánya jelzi
    if (this.engedelyProba || !s || !('seged' in s) || s.esemeny_engedely) return;
    this.engedelyProba = true;
    naptarApi
      .allapot(true)
      .then(() => this.utemez(200))
      .catch(() => {});
  }

  /** Egy változás-esemény: látszó nézetnek összevonva tölt, különben elavultnak jelöl. */
  utemez(kesleltet = 600): void {
    this.elavult = true;
    if (!this.latszok || !this.lathato()) return;
    if (this.idozito) clearTimeout(this.idozito);
    this.idozito = setTimeout(() => {
      this.idozito = null;
      void this.frissit();
    }, kesleltet);
  }

  /** A lap láthatóvá vált: ha elavult vagy átfordult a nap, tölt. */
  lathatovaValt(): void {
    if (!this.latszok) return;
    if (this.elavult || this.nap !== napKulcs(this.most())) void this.frissit();
    this.ejfelUtemez();
  }

  private ejfelUtemez(): void {
    if (this.ejfelIdozito) clearTimeout(this.ejfelIdozito);
    this.ejfelIdozito = null;
    if (!this.latszok) return;
    this.ejfelIdozito = setTimeout(() => {
      this.ejfelIdozito = null;
      if (this.latszok) {
        void this.frissit();
        this.ejfelUtemez();
      }
    }, ejfelig(this.most()) + 500);
  }

  figyel(k: CoreKapcsolat): () => void {
    const le = [
      k.figyel('vault_valtozas', () => this.utemez(800)),
      k.figyel('vault_iras', () => this.utemez(400)),
      k.figyel('index', () => this.utemez(500)),
      k.figyel('hello', () => this.utemez(300)),
      // a naptár-szinkron, a javaslatok és az emlékeztetők állapota (C29)
      k.figyel('naptar_valtozas', () => this.utemez(600)),
      k.figyel('naptar_javaslat', () => this.utemez(400)),
      // az Asszisztens új higiénia-tételei (C30a)
      k.figyel('asszisztens_valtozas', () => this.utemez(500)),
    ];
    const lathatoEsemeny = () => {
      if (document.visibilityState !== 'hidden') this.lathatovaValt();
    };
    if (typeof document !== 'undefined') document.addEventListener('visibilitychange', lathatoEsemeny);
    return () => {
      for (const f of le) f();
      if (typeof document !== 'undefined') document.removeEventListener('visibilitychange', lathatoEsemeny);
      if (this.idozito) clearTimeout(this.idozito);
      if (this.ejfelIdozito) clearTimeout(this.ejfelIdozito);
    };
  }
}

export const maAdat = new MaAdat();
