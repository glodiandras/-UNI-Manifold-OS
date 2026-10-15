// A dolgozat-oldal adata (C28a): a lista (`GET /api/felkeszultseg`) és a kiválasztott dolgozat részlete
// (`GET /api/felkeszultseg/dolgozat?azon=`). A „Ma” oldal store-jának mintája: töltés a nézet megjelenésekor, a
// WS-eseményre (vault, index, naptár, javaslat — összevonva), láthatóvá váláskor és éjfélkor, **de csak látszó
// nézetnek**; nyugalomban és rejtett lapon semmi nem ütemez. Az elavult választ a sorszám dobja el.

import { ApiHiba, kerdez } from '../lib/core/api';
import type { CoreKapcsolat } from '../lib/core/ws.svelte';
import { ejfelig, napKulcs } from '../ma/datum';
import type { DolgozatSor, Ertekeles, Kalibracio, ListaValasz, Reszlet } from './tipusok';

/** Az alapértelmezett dolgozat: az első még le nem zárt, különben az első. */
export function alapertelmezett(dolgozatok: DolgozatSor[]): string | null {
  return (dolgozatok.find((d) => !d.lezart) ?? dolgozatok[0])?.azon ?? null;
}

export class DolgozatAdat {
  lista = $state.raw<ListaValasz | null>(null);
  reszlet = $state.raw<Reszlet | null>(null);
  valasztott = $state<string | null>(null);
  hiba = $state<string | null>(null);
  reszletHiba = $state<string | null>(null);
  betoltve = $state(false);

  // C28b: a szöveges értékelés (a modell kattintásra fut) és az önkalibráció jelentése (a „Hogyan számolódik” megnyitásakor tölt)
  ertekeles = $state.raw<(Ertekeles & { azon: string }) | null>(null);
  ertekelesFut = $state(false);
  ertekelesHiba = $state<string | null>(null);
  kalibracio = $state.raw<Kalibracio | null>(null);
  kalibracioHiba = $state<string | null>(null);
  kalibracioTolt = $state(false);

  private kalibracioElavult = true;
  private latszok = 0;
  private elavult = true;
  private idozito: ReturnType<typeof setTimeout> | null = null;
  private ejfelIdozito: ReturnType<typeof setTimeout> | null = null;
  private sorszam = 0;
  private nap = napKulcs(new Date());

  constructor(
    private readonly most: () => Date = () => new Date(),
    private readonly lathato: () => boolean = () => typeof document === 'undefined' || document.visibilityState !== 'hidden',
  ) {}

  /** Egy dolgozat-nézet megjelent: tölt, ha az adat elavult; a visszaadott függvény jelzi az eltűnését. */
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

  /** A kiválasztott dolgozat (a fül állapotából): a részletet újratölti, ha más lett. */
  async valaszt(azon: string | null): Promise<void> {
    if (azon === this.valasztott && this.reszlet) return;
    this.valasztott = azon;
    await this.reszletTolt();
  }

  /** Szöveges értékelés kérése a helyi modelltől (C28b). A modell lassú lehet (az első betöltés percekig tarthat), ezért hosszú
   *  időkorlát; egyszerre egy kérés fut. A hiba (nincs kalibrált modell: 503) a `ertekelesHiba`-ba kerül. */
  async ertekelesKer(azon: string): Promise<void> {
    if (this.ertekelesFut) return;
    this.ertekelesFut = true;
    this.ertekelesHiba = null;
    try {
      const v = await kerdez<Ertekeles>('/api/felkeszultseg/ertekeles', { metodus: 'POST', torzs: { azon }, idokorlat: 300_000 });
      this.ertekeles = { ...v, azon };
    } catch (e) {
      this.ertekelesHiba = e instanceof ApiHiba && e.statusz === 0 && e.message === 'időtúllépés'
        ? 'A modell nem válaszolt időben.'
        : e instanceof Error ? e.message : String(e);
    } finally {
      this.ertekelesFut = false;
    }
  }

  /** Az önkalibráció jelentése (C28b): megnyitáskor tölt, ha még nincs vagy az adat azóta elavult. A számítás rekonstrukciót végez
   *  lezárt dolgozatonként, ezért nem fut magától, csak a „Hogyan számolódik” részlet megnyitásakor. */
  async kalibracioBetolt(): Promise<void> {
    if (this.kalibracioTolt || (this.kalibracio && !this.kalibracioElavult)) return;
    this.kalibracioTolt = true;
    this.kalibracioElavult = false;
    try {
      this.kalibracio = await kerdez<Kalibracio>('/api/felkeszultseg/kalibracio', { idokorlat: 60_000 });
      this.kalibracioHiba = null;
    } catch (e) {
      this.kalibracioHiba = e instanceof Error ? e.message : String(e);
      this.kalibracioElavult = true;
    } finally {
      this.kalibracioTolt = false;
    }
  }

  async frissit(): Promise<void> {
    const en = ++this.sorszam;
    this.nap = napKulcs(this.most());
    this.elavult = false; // a töltés közben érkező változás újra elavulttá teszi: az nem veszhet el a válasz érkezésekor
    try {
      const l = await kerdez<ListaValasz>('/api/felkeszultseg', { idokorlat: 20000 });
      if (en !== this.sorszam) return;
      this.lista = l;
      this.hiba = null;
      this.betoltve = true;
      if (!this.valasztott || !l.dolgozatok.some((d) => d.azon === this.valasztott)) this.valasztott = alapertelmezett(l.dolgozatok);
      await this.reszletTolt(en);
    } catch (e) {
      if (en !== this.sorszam) return;
      this.hiba = e instanceof Error ? e.message : String(e);
      this.betoltve = true;
      this.elavult = true;
    }
  }

  private async reszletTolt(en = this.sorszam): Promise<void> {
    const azon = this.valasztott;
    if (!azon) {
      this.reszlet = null;
      this.reszletHiba = null;
      return;
    }
    try {
      const r = await kerdez<Reszlet>(`/api/felkeszultseg/dolgozat?azon=${encodeURIComponent(azon)}`, { idokorlat: 20000 });
      if (en !== this.sorszam || azon !== this.valasztott) return;
      this.reszlet = r;
      this.reszletHiba = null;
    } catch (e) {
      if (en !== this.sorszam || azon !== this.valasztott) return;
      this.reszlet = null;
      this.reszletHiba = e instanceof Error ? e.message : String(e);
    }
  }

  /** Egy változás-esemény: látszó nézetnek összevonva tölt, különben elavultnak jelöl. */
  utemez(kesleltet = 800): void {
    this.elavult = true;
    this.kalibracioElavult = true;
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
      k.figyel('vault_valtozas', () => this.utemez(900)),
      k.figyel('vault_iras', () => this.utemez(500)),
      k.figyel('index', () => this.utemez(600)),
      k.figyel('hello', () => this.utemez(300)),
      k.figyel('naptar_valtozas', () => this.utemez(700)),
      k.figyel('naptar_javaslat', () => this.utemez(500)),
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

export const dolgozatAdat = new DolgozatAdat();
