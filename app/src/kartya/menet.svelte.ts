// Egy ismétlés menete (C23b; docs/C23-TERV.md 7.): a beágyazott pakli (egy kísérőjegyzet esedékes kártyái) és a „Mai
// ismétlés” (az összes esedékes, utánuk az újak a napi limitig) ugyanezt a menetet használja.
//
// Billentyűk (az Ankiéi): szóköz vagy Enter a kérdés oldalán fordít; 1–4 értékel (Újra · Nehéz · Jó · Könnyű);
// ⌘Z / Ctrl+Z az utolsó értékelést vonja vissza (a kártya visszakerül a sor elejére). A válaszidő a fordításig mért ms.

import { kartyaApi, type Kartya, type KartyaApi } from './api';

export type Fazis = 'betolt' | 'kerdes' | 'valasz' | 'kesz' | 'ures' | 'hiba';
export type Forras = { tipus: 'pakli'; ut: string } | { tipus: 'mai' };

export interface MenetFuggosegek {
  api?: KartyaApi;
  tracker?: (ut: string | null, adat: { jegy: number; kartya_id: string; ms?: number }) => void;
  most?: () => number;
}

export class IsmetlesMenet {
  fazis = $state<Fazis>('betolt');
  hiba = $state<string | null>(null);
  lista = $state<Kartya[]>([]);
  i = $state(0);
  kuld = $state(false);
  /** a menet elején esedékes (nem új) és új kártyák száma, és amennyit ebben a menetben értékelt */
  esedekes = $state(0);
  uj = $state(0);
  kesz = $state(0);
  /** a pakli összes kártyája (a „ma nincs esedékes” felirathoz) */
  osszes = $state(0);

  private readonly api: KartyaApi;
  private readonly tracker: NonNullable<MenetFuggosegek['tracker']>;
  private readonly most: () => number;
  private tKerdes = 0;
  private ms: number | null = null;
  private veremben: { kartya: Kartya; i: number }[] = [];

  constructor(
    readonly forras: Forras,
    f: MenetFuggosegek = {},
  ) {
    this.api = f.api ?? kartyaApi;
    this.tracker = f.tracker ?? (() => {});
    this.most = f.most ?? (() => performance.now());
  }

  get aktualis(): Kartya | null {
    return this.lista[this.i] ?? null;
  }

  get hatra(): number {
    return Math.max(0, this.lista.length - this.i);
  }

  async betolt(): Promise<void> {
    this.fazis = 'betolt';
    this.hiba = null;
    try {
      if (this.forras.tipus === 'pakli') {
        const p = await this.api.jegyzet(this.forras.ut);
        this.lista = p.kartyak.filter((k) => k.esedekes_most);
        this.osszes = p.osszes;
        this.esedekes = p.esedekes;
        this.uj = p.uj;
      } else {
        const e = await this.api.esedekes();
        this.lista = e.kartyak;
        this.osszes = e.osszes ?? e.kartyak.length;
        this.esedekes = e.esedekes;
        this.uj = e.uj;
      }
      this.i = 0;
      this.kesz = 0;
      this.veremben = [];
      this.kezd();
    } catch (e) {
      this.hiba = e instanceof Error ? e.message : String(e);
      this.fazis = 'hiba';
    }
  }

  private kezd(): void {
    this.fazis = this.lista.length === 0 ? (this.kesz ? 'kesz' : 'ures') : this.i >= this.lista.length ? 'kesz' : 'kerdes';
    this.tKerdes = this.most();
    this.ms = null;
  }

  fordit(): void {
    if (this.fazis !== 'kerdes') return;
    this.ms = Math.max(0, Math.round(this.most() - this.tKerdes));
    this.fazis = 'valasz';
  }

  async ertekel(jegy: number): Promise<void> {
    const k = this.aktualis;
    if (this.fazis !== 'valasz' || !k || this.kuld || ![1, 2, 3, 4].includes(jegy)) return;
    this.kuld = true;
    try {
      const v = await this.api.valasz(k.azon, jegy, this.ms);
      this.tracker(v.tracker.ut, v.tracker.adat);
      this.veremben.push({ kartya: k, i: this.i });
      this.kesz += 1;
      // az „Újra” kártya a menet végén még egyszer jön (az Anki tanulási lépése a perceken belül esedékes)
      if (jegy === 1) this.lista = [...this.lista, { ...k, uj: false, elorejelzes: null }];
      this.i += 1;
      this.kezd();
    } catch (e) {
      this.hiba = e instanceof Error ? e.message : String(e);
    } finally {
      this.kuld = false;
    }
  }

  /** Az utolsó értékelés visszavonása (⌘Z): a core visszaállítja az előtte-állapotot, a kártya újra a kérdés oldalán áll. */
  async visszavon(): Promise<boolean> {
    const utolso = this.veremben.at(-1);
    if (!utolso || this.kuld) return false;
    this.kuld = true;
    try {
      const v = await this.api.visszavon(utolso.kartya.azon);
      if (!v.visszavonva) return false;
      this.veremben.pop();
      this.kesz = Math.max(0, this.kesz - 1);
      // az „Újra” miatt a sor végére tett másolat kikerül
      const vege = this.lista.length - 1;
      if (vege > utolso.i && this.lista[vege].azon === utolso.kartya.azon) this.lista = this.lista.slice(0, vege);
      this.i = utolso.i;
      this.hiba = null;
      this.kezd();
      return true;
    } catch (e) {
      this.hiba = e instanceof Error ? e.message : String(e);
      return false;
    } finally {
      this.kuld = false;
    }
  }

  /** A blokk billentyűi; → igaz, ha a menet kezelte (a hívó megállítja az eseményt). */
  billentyu(e: KeyboardEvent): boolean {
    if ((e.metaKey || e.ctrlKey) && !e.shiftKey && !e.altKey && e.key.toLowerCase() === 'z') {
      if (!this.veremben.length) return false;
      void this.visszavon();
      return true;
    }
    if (e.metaKey || e.ctrlKey || e.altKey) return false;
    if ((e.key === ' ' || e.key === 'Enter') && this.fazis === 'kerdes') {
      this.fordit();
      return true;
    }
    if (this.fazis === 'valasz' && /^[1-4]$/.test(e.key)) {
      void this.ertekel(Number(e.key));
      return true;
    }
    return false;
  }
}
