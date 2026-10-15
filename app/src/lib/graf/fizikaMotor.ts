// A fizika ütemezője és üzenetkezelője: ugyanez fut a Web Workerben és (ha a Worker nem indul) a fő szálon.
// Nyugalomban (alpha a küszöb alatt) vagy szüneteltetve nincs ütemezett hívás: a gráf nem számol.

import { ALAP_EROK, Fizika, type ErokBeallitas } from './fizika';

export type Be =
  | {
      tipus: 'init';
      n: number;
      elek: ArrayBuffer;
      poz: ArrayBuffer;
      beall?: Partial<ErokBeallitas>;
      alpha?: number;
      aktiv?: ArrayBuffer;
      /** Előmelegítés: legfeljebb ennyi tick, legfeljebb `elore_ms` ideig (az első kép már gráf legyen). */
      elore?: number;
      elore_ms?: number;
    }
  | { tipus: 'aktiv'; maszk: ArrayBuffer; alpha?: number }
  | { tipus: 'beall'; beall: Partial<ErokBeallitas> }
  | { tipus: 'rogzit'; i: number; x: number; y: number; huz?: boolean }
  | { tipus: 'enged'; i: number; marad?: boolean }
  | { tipus: 'melegit'; alpha: number }
  | { tipus: 'szunet' }
  | { tipus: 'folytat' }
  | { tipus: 'uj_helyzet'; poz: ArrayBuffer };

export type Ki =
  | { tipus: 'poz'; poz: Float32Array; alpha: number; fut: boolean }
  | { tipus: 'kesz'; elore: number; ms: number };

export interface Ido {
  keso(f: () => void, ms: number): unknown;
  torol(id: unknown): void;
  most(): number;
}

const VALOS_IDO: Ido = {
  keso: (f, ms) => setTimeout(f, ms),
  torol: (id) => clearTimeout(id as ReturnType<typeof setTimeout>),
  most: () => performance.now(),
};

/** Egy tick ideje legfeljebb ~16 ms-os ütemben: nagy gráfon is nyugodt, látható beállás. */
const TICK_MS = 16;

export class FizikaMotor {
  private f: Fizika | null = null;
  private szunetel = false;
  private idozito: unknown = null;
  /** Hány tick futott összesen (a tesztnek és a méréshez). */
  tickek = 0;

  constructor(
    private readonly kuld: (m: Ki) => void,
    private readonly ido: Ido = VALOS_IDO,
  ) {}

  /** Fut-e ütemezett számolás (nyugalomban hamis: ekkor nincs időzítő sem). */
  get utemezve(): boolean {
    return this.idozito !== null;
  }

  kezel(d: Be): void {
    const f = this.f;
    switch (d.tipus) {
      case 'init': {
        this.leallit();
        const uj = new Fizika(d.n, new Int32Array(d.elek), new Float32Array(d.poz), { ...ALAP_EROK, ...d.beall });
        if (d.aktiv) uj.aktival(new Uint8Array(d.aktiv));
        uj.alpha = d.alpha ?? 1;
        this.f = uj;
        const t0 = this.ido.most();
        let db = 0;
        while (db < (d.elore ?? 0) && this.ido.most() - t0 < (d.elore_ms ?? 600)) {
          uj.tick();
          db++;
        }
        this.tickek += db;
        this.kuldPoz();
        this.kuld({ tipus: 'kesz', elore: db, ms: Math.round(this.ido.most() - t0) });
        this.indit();
        return;
      }
      case 'szunet':
        this.szunetel = true;
        this.leallit();
        return;
      case 'folytat':
        this.szunetel = false;
        this.indit();
        return;
    }
    if (!f) return;
    switch (d.tipus) {
      case 'aktiv':
        f.aktival(new Uint8Array(d.maszk));
        f.alpha = Math.max(f.alpha, d.alpha ?? 0.5);
        break;
      case 'beall':
        f.beallit(d.beall);
        f.alpha = Math.max(f.alpha, 0.4);
        break;
      case 'rogzit':
        f.fx[d.i] = d.x;
        f.fy[d.i] = d.y;
        f.x[d.i] = d.x;
        f.y[d.i] = d.y;
        if (d.huz) f.alphaCel = 0.25;
        f.alpha = Math.max(f.alpha, d.huz ? 0.12 : 0.05);
        break;
      case 'enged':
        if (!d.marad) {
          f.fx[d.i] = NaN;
          f.fy[d.i] = NaN;
        }
        f.alphaCel = 0;
        break;
      case 'melegit':
        f.alpha = Math.max(f.alpha, d.alpha);
        break;
      case 'uj_helyzet': {
        const p = new Float32Array(d.poz);
        for (let i = 0; i < f.n; i++) {
          f.x[i] = p[2 * i];
          f.y[i] = p[2 * i + 1];
          f.vx[i] = 0;
          f.vy[i] = 0;
          f.fx[i] = NaN;
          f.fy[i] = NaN;
        }
        f.alpha = 1;
        break;
      }
    }
    this.indit();
  }

  /** A számolás leállítása és az állapot eldobása (a nézet bezárásakor). */
  leallit(): void {
    if (this.idozito !== null) this.ido.torol(this.idozito);
    this.idozito = null;
  }

  private kuldPoz(): void {
    const f = this.f;
    if (f) this.kuld({ tipus: 'poz', poz: f.helyzetek(), alpha: f.alpha, fut: !f.nyugalomban() });
  }

  private indit(): void {
    if (this.idozito === null && this.f && !this.szunetel && !this.f.nyugalomban()) this.idozito = this.ido.keso(() => this.ciklus(), 0);
  }

  private ciklus(): void {
    this.idozito = null;
    const f = this.f;
    if (!f || this.szunetel) return;
    const t0 = this.ido.most();
    f.tick();
    this.tickek++;
    this.kuldPoz();
    if (f.nyugalomban()) return;
    this.idozito = this.ido.keso(() => this.ciklus(), Math.max(0, TICK_MS - (this.ido.most() - t0)));
  }
}
