// A gráf rajzolója és bemenet-kezelője (C13): Canvas 2D, kötegelt rajz (színenként és alakonként egy útvonal, egy
// `stroke` az összes élre), HiDPI. A legacy `graf.js` canvas-rajzolójának átdolgozása, Svelte nélkül.
//
// Nyugalmi állapotban nem fut semmi: a `requestAnimationFrame` csak akkor ütemez, ha a fizika fut, animáció van
// (repülés, kifutás, kiemelés áttűnése) vagy a felhasználó húz/nagyít; különben a rajz áll, és a CPU nulla.

import type { Be } from './fizikaMotor';
import type { GrafAdat } from './modell';

export interface Szinek {
  jegyzet: string;
  canvas: string;
  melleklet: string;
  el: string;
  elKiemelt: string;
  kijelolt: string;
  felulet: string;
  szoveg: string;
  halo: string;
  talalat: string;
}

export type MegnyitasMod = 'aktiv' | 'ujful' | 'osztas';

export interface Esemenyek {
  megnyit(i: number, mod: MegnyitasMod): void;
  fizika(m: Be): void;
  /** A kurzor alatti csúcs változott (tooltiphoz): -1 = nincs. Az x, y a vászon koordinátája. */
  hover?(i: number, x: number, y: number): void;
  /** A kijelölt csúcs változott (Esc, kattintás a semmire). */
  kijeloles?(i: number): void;
}

export interface Bemenet {
  adat: GrafAdat;
  lathato: Uint8Array;
  /** Csúcsonként a színcsoport indexe (-1 = nincs). */
  csoport: Int16Array;
  csoportSzinek: readonly string[];
  nyil: boolean;
  meretSzorzo: number;
  vonalSzorzo: number;
}

export interface Meres {
  /** Az utolsó képkockák rajzolási ideje (ms), körpuffer. */
  rajzMs: number[];
  kepek: number;
  /** Hány `requestAnimationFrame` ütemezés volt összesen (nyugalomban nem nő). */
  utemezesek: number;
}

const K_MAX = 10;
const K_MIN_ALAP = 0.02;
const CELLA = 32;
const CIMKE_CELLA = 24;
const KATTINTAS_KUSZOB = 4;

// alakok
const KOR = 0;
const NEGYZET = 1;
const HAROMSZOG = 2;
const ROMBUSZ = 3;
const GYURU = 4;

function alak(tipus: string): number {
  switch (tipus) {
    case 'md':
      return KOR;
    case 'pdf':
    case 'kep':
      return NEGYZET;
    case 'video':
    case 'hang':
      return HAROMSZOG;
    case 'canvas':
    case 'base':
      return ROMBUSZ;
    default:
      return GYURU;
  }
}

const korlat = (x: number, a: number, b: number) => Math.min(b, Math.max(a, x));
const simitas = (a: number, b: number, x: number) => {
  const t = korlat((x - a) / (b - a), 0, 1);
  return t * t * (3 - 2 * t);
};

/** Van Wijk–Nuij-féle sima repülés (a d3.interpolateZoom mintájára): (x, y, w) → (x, y, w), t ∈ [0, 1]. */
export function repulesInterpolator(
  [ux0, uy0, w0]: readonly [number, number, number],
  [ux1, uy1, w1]: readonly [number, number, number],
  rho = Math.SQRT2,
): { f: (t: number) => [number, number, number]; ido: number } {
  const dx = ux1 - ux0;
  const dy = uy1 - uy0;
  const d2 = dx * dx + dy * dy;
  if (d2 < 1e-12) {
    const S = Math.log(w1 / w0) / rho;
    return { f: (t) => [ux0 + t * dx, uy0 + t * dy, w0 * Math.exp(rho * t * S)], ido: Math.abs(S) * 1000 };
  }
  const d1 = Math.sqrt(d2);
  const b0 = (w1 * w1 - w0 * w0 + rho ** 4 * d2) / (2 * w0 * rho * rho * d1);
  const b1 = (w1 * w1 - w0 * w0 - rho ** 4 * d2) / (2 * w1 * rho * rho * d1);
  const r0 = Math.log(Math.sqrt(b0 * b0 + 1) - b0);
  const r1 = Math.log(Math.sqrt(b1 * b1 + 1) - b1);
  const S = (r1 - r0) / rho;
  return {
    f: (t) => {
      const s = t * S;
      const cr0 = Math.cosh(r0);
      const u = (w0 / (rho * rho * d1)) * (cr0 * Math.tanh(rho * s + r0) - Math.sinh(r0));
      return [ux0 + u * dx, uy0 + u * dy, (w0 * cr0) / Math.cosh(rho * s + r0)];
    },
    ido: (S * 1000 * rho) / Math.SQRT2,
  };
}

export class GrafRajzolo {
  // nézet: képernyő = világ · k + t
  k = 1;
  tx = 0;
  ty = 0;
  kijelolt = -1;
  hover = -1;
  /** A felhasználó mozgatta vagy nagyította a nézetet (az automatikus illesztés ekkor nem írja felül). */
  nezetModositva = false;
  readonly meres: Meres = { rajzMs: [], kepek: 0, utemezesek: 0 };

  private readonly ctx: CanvasRenderingContext2D;
  private w = 0;
  private h = 0;
  private dpr = 1;
  private szinek: Szinek | null = null;
  private betu = '12px sans-serif';
  private be: Bemenet | null = null;
  private poz: Float32Array = new Float32Array(0);
  private fizikaFut = false;
  private szunetel = false;
  private csokkentett = false;

  // csúcs-attribútumok
  private r0 = new Float32Array(0);
  private szinId = new Int16Array(0);
  private alakok = new Uint8Array(0);
  private palettaSzinek: string[] = [];
  private rendezett = new Int32Array(0);
  private vedoKezd = new Int32Array(0); // vödrönként a rendezett lista kezdete
  private vedoKulcs: number[] = [];

  // képkockánkénti puffer
  private sx = new Float32Array(0);
  private sy = new Float32Array(0);
  private sr = new Float32Array(0);
  private kepen = new Uint8Array(0);
  private racsFej = new Int32Array(0);
  private racsKov = new Int32Array(0);
  private racsW = 0;
  private racsH = 0;

  // fókusz és kiemelés
  private fokusz = -1;
  private szomsz = new Uint8Array(0);
  private kiemeles = 0;
  private talalatok = new Set<number>();

  // időzítés és animáció
  private raf = 0;
  private utolso = 0;
  private repules: { t0: number; ido: number; f: (t: number) => [number, number, number]; } | null = null;
  private kifutas: { vx: number; vy: number } | null = null;
  private cimkeFoglalt = new Uint8Array(0);

  // bemenet
  private huz: { id: number; i: number; x0: number; y0: number; sx: number; sy: number; mozdult: boolean; wx: number; wy: number; mod: MegnyitasMod } | null = null;
  private mintak: { t: number; x: number; y: number }[] = [];
  private gesztus: { k0: number; cx: number; cy: number } | null = null;
  private leiratkoz: (() => void)[] = [];

  constructor(
    private readonly canvas: HTMLCanvasElement,
    private readonly e: Esemenyek,
  ) {
    const ctx = canvas.getContext('2d', { alpha: true });
    if (!ctx) throw new Error('nincs 2D vászon');
    this.ctx = ctx;
    this.csokkentett = typeof matchMedia === 'function' && matchMedia('(prefers-reduced-motion: reduce)').matches;
    this.bemenetTelepit();
  }

  // ------------------------------------------------------------------ nyilvános API

  szinBeallit(s: Szinek, betu?: string): void {
    this.szinek = s;
    if (betu) this.betu = betu;
    this.palettaEpit();
    this.kerKeret();
  }

  bemenet(b: Bemenet): void {
    const regiN = this.be?.adat.n ?? -1;
    this.be = b;
    const n = b.adat.n;
    if (n !== regiN) {
      this.sx = new Float32Array(n);
      this.sy = new Float32Array(n);
      this.sr = new Float32Array(n);
      this.kepen = new Uint8Array(n);
      this.racsKov = new Int32Array(n);
      this.szomsz = new Uint8Array(n);
      if (this.poz.length !== 2 * n) this.poz = new Float32Array(2 * n);
      if (this.kijelolt >= n) this.kijelolt = -1;
      this.fokusz = -1;
      this.hover = -1;
      this.talalatok.clear();
    }
    this.r0 = new Float32Array(n);
    this.alakok = new Uint8Array(n);
    const ms = korlat(b.meretSzorzo, 0.5, 2);
    for (let i = 0; i < n; i++) {
      this.r0[i] = Math.min(18, 3.4 + Math.sqrt(b.adat.fok[i]) * 1.3) * ms;
      this.alakok[i] = alak(b.adat.tipus[i]);
    }
    this.palettaEpit();
    this.fokuszSzomszedok();
    this.kerKeret();
  }

  /** Új helyzetek a fizikától (a húzott csúcs a kurzor alatt marad). */
  pozBe(p: Float32Array, fut: boolean): void {
    if (this.huz?.mozdult) {
      p[2 * this.huz.i] = this.huz.wx;
      p[2 * this.huz.i + 1] = this.huz.wy;
    }
    this.poz = p;
    this.fizikaFut = fut;
    this.kerKeret();
  }

  pozicio(i: number): [number, number] {
    return [this.poz[2 * i], this.poz[2 * i + 1]];
  }

  meretValtozas(): void {
    const r = this.canvas.getBoundingClientRect();
    const dpr = Math.min(3, window.devicePixelRatio || 1);
    const w = Math.max(1, Math.round(r.width));
    const h = Math.max(1, Math.round(r.height));
    if (w === this.w && h === this.h && dpr === this.dpr) return;
    this.w = w;
    this.h = h;
    this.dpr = dpr;
    this.canvas.width = Math.round(w * dpr);
    this.canvas.height = Math.round(h * dpr);
    this.cimkeFoglalt = new Uint8Array(Math.ceil(w / CIMKE_CELLA) * Math.ceil(h / CIMKE_CELLA));
    this.kerKeret();
  }

  kijeloles(i: number): void {
    if (this.kijelolt === i) return;
    this.kijelolt = i;
    this.fokuszSzomszedok();
    this.kerKeret();
  }

  talalatBeallit(ids: readonly number[]): void {
    this.talalatok = new Set(ids);
    this.kerKeret();
  }

  szunet(b: boolean): void {
    this.szunetel = b;
    if (b && this.raf) {
      cancelAnimationFrame(this.raf);
      this.raf = 0;
    }
    if (!b) this.kerKeret();
  }

  /** A kép újrarajzolása a következő keretben (és csak azután, ha kell, a következőben is). */
  kerKeret(): void {
    if (this.raf || this.szunetel || !this.be) return;
    this.meres.utemezesek++;
    this.raf = requestAnimationFrame((t) => this.keret(t));
  }

  /** A nézet visszaállítása (a nézet-váltáskor mentett állapotból). */
  nezetBeallit(k: number, tx: number, ty: number): void {
    this.k = korlat(k, this.kMin(), K_MAX);
    this.tx = tx;
    this.ty = ty;
    this.nezetModositva = true;
    this.kerKeret();
  }

  /** A látható csúcsok befoglalója (az 1–99 percentilis: a kilógó csúcs nem zsugorítja a nézetet). */
  teljesNezet(animalt = true): void {
    const b = this.be;
    if (!b || !this.w) return;
    const xs: number[] = [];
    const ys: number[] = [];
    for (let i = 0; i < b.adat.n; i++)
      if (b.lathato[i]) {
        xs.push(this.poz[2 * i]);
        ys.push(this.poz[2 * i + 1]);
      }
    if (!xs.length) return;
    xs.sort((a, c) => a - c);
    ys.sort((a, c) => a - c);
    const lo = Math.floor(xs.length * 0.01);
    const hi = Math.max(lo, Math.ceil(xs.length * 0.99) - 1);
    const x0 = xs[lo];
    const x1 = xs[hi];
    const y0 = ys[lo];
    const y1 = ys[hi];
    const szel = Math.max(x1 - x0, 40);
    const mag = Math.max(y1 - y0, 40);
    const k = korlat(Math.min((this.w * 0.9) / szel, (this.h * 0.9) / mag), this.kMin(), 3);
    this.nezetre([(x0 + x1) / 2, (y0 + y1) / 2], k, animalt);
  }

  /** Repülés egy csúcshoz (keresés, ugrás): a csúcs a vászon közepére kerül, legalább ekkora nagyítással. */
  repul(i: number, minK = 1.6): void {
    const k = Math.max(this.k, minK);
    this.nezetre(this.pozicio(i), Math.min(K_MAX, k), true);
  }

  leallit(): void {
    if (this.raf) cancelAnimationFrame(this.raf);
    this.raf = 0;
    this.szunetel = true;
    this.leiratkoz.forEach((f) => f());
    this.leiratkoz = [];
  }

  /** A képernyő-koordináta (a vászonhoz képest) alatti csúcs a legutóbbi képkocka rácsán, vagy -1. */
  csucsAlatt(x: number, y: number): number {
    if (!this.be || !this.racsFej.length) return -1;
    const cx = Math.floor(x / CELLA);
    const cy = Math.floor(y / CELLA);
    let legjobb = -1;
    let legkozelebb = Infinity;
    for (let gy = cy - 1; gy <= cy + 1; gy++)
      for (let gx = cx - 1; gx <= cx + 1; gx++) {
        if (gx < 0 || gy < 0 || gx >= this.racsW || gy >= this.racsH) continue;
        for (let i = this.racsFej[gy * this.racsW + gx]; i >= 0; i = this.racsKov[i]) {
          const d = Math.hypot(this.sx[i] - x, this.sy[i] - y);
          const hatar = Math.max(12, this.sr[i] + 5);
          if (d <= hatar && d < legkozelebb) {
            legkozelebb = d;
            legjobb = i;
          }
        }
      }
    return legjobb;
  }

  // ------------------------------------------------------------------ nézet-átalakítás

  private kMin(): number {
    return K_MIN_ALAP;
  }

  private nezetre([wx, wy]: readonly [number, number], k: number, animalt: boolean): void {
    this.nezetModositva = false;
    if (!animalt || this.csokkentett || !this.w) {
      this.repules = null;
      this.k = k;
      this.tx = this.w / 2 - wx * k;
      this.ty = this.h / 2 - wy * k;
      this.kerKeret();
      return;
    }
    const cx0 = (this.w / 2 - this.tx) / this.k;
    const cy0 = (this.h / 2 - this.ty) / this.k;
    const { f, ido } = repulesInterpolator([cx0, cy0, this.w / this.k], [wx, wy, this.w / k]);
    this.kifutas = null;
    this.repules = { t0: performance.now(), ido: korlat(ido, 220, 900), f };
    this.kerKeret();
  }

  private nagyit(tenyezo: number, ax: number, ay: number): void {
    const uj = korlat(this.k * tenyezo, this.kMin(), K_MAX);
    const r = uj / this.k;
    this.tx = ax - (ax - this.tx) * r;
    this.ty = ay - (ay - this.ty) * r;
    this.k = uj;
    this.repules = null;
    this.nezetModositva = true;
    this.kerKeret();
  }

  private vilag(x: number, y: number): [number, number] {
    return [(x - this.tx) / this.k, (y - this.ty) / this.k];
  }

  // ------------------------------------------------------------------ paletta és kiemelés

  private palettaEpit(): void {
    const b = this.be;
    const s = this.szinek;
    if (!b || !s) return;
    this.palettaSzinek = [s.jegyzet, s.canvas, s.melleklet, ...b.csoportSzinek];
    const n = b.adat.n;
    this.szinId = new Int16Array(n);
    for (let i = 0; i < n; i++) {
      const cs = b.csoport[i];
      this.szinId[i] = cs >= 0 ? 3 + cs : b.adat.tipus[i] === 'md' ? 0 : b.adat.tipus[i] === 'canvas' || b.adat.tipus[i] === 'base' ? 1 : 2;
    }
    // csúcsok vödrökbe (szín × alak) rendezve: a képkockánként nincs csoportosítás
    const kulcs = (i: number) => this.szinId[i] * 5 + this.alakok[i];
    const db = new Map<number, number>();
    for (let i = 0; i < n; i++) db.set(kulcs(i), (db.get(kulcs(i)) ?? 0) + 1);
    this.vedoKulcs = [...db.keys()].sort((a, c) => a - c);
    const kezd = new Map<number, number>();
    this.vedoKezd = new Int32Array(this.vedoKulcs.length + 1);
    let o = 0;
    this.vedoKulcs.forEach((k, j) => {
      kezd.set(k, o);
      this.vedoKezd[j] = o;
      o += db.get(k)!;
    });
    this.vedoKezd[this.vedoKulcs.length] = o;
    this.rendezett = new Int32Array(n);
    for (let i = 0; i < n; i++) {
      const k = kulcs(i);
      this.rendezett[kezd.get(k)!] = i;
      kezd.set(k, kezd.get(k)! + 1);
    }
  }

  private fokuszSzomszedok(): void {
    const b = this.be;
    if (!b) return;
    const f = this.hover >= 0 ? this.hover : this.kijelolt;
    this.fokusz = f;
    this.szomsz.fill(0);
    if (f < 0) return;
    this.szomsz[f] = 1;
    for (const j of b.adat.szomszedok(f)) this.szomsz[j] = 1;
  }

  // ------------------------------------------------------------------ rajzolás

  private keret(most: number): void {
    this.raf = 0;
    const b = this.be;
    const s = this.szinek;
    if (!b || !s || !this.w || this.szunetel) return;
    const t0 = performance.now();
    const dt = this.utolso ? Math.min(100, most - this.utolso) : 16;
    this.utolso = most;
    let animal = false;

    // repülés
    if (this.repules) {
      const t = korlat((performance.now() - this.repules.t0) / this.repules.ido, 0, 1);
      const e = t < 0.5 ? 2 * t * t : 1 - Math.pow(-2 * t + 2, 2) / 2;
      const [wx, wy, ww] = this.repules.f(e);
      this.k = korlat(this.w / ww, this.kMin(), K_MAX);
      this.tx = this.w / 2 - wx * this.k;
      this.ty = this.h / 2 - wy * this.k;
      if (t >= 1) this.repules = null;
      else animal = true;
    }
    // kifutás a pásztázás után
    if (this.kifutas && !this.huz) {
      const f = Math.pow(0.998, dt);
      this.tx += this.kifutas.vx * dt;
      this.ty += this.kifutas.vy * dt;
      this.kifutas.vx *= f;
      this.kifutas.vy *= f;
      if (Math.hypot(this.kifutas.vx, this.kifutas.vy) < 0.01) this.kifutas = null;
      else animal = true;
    }
    // kiemelés áttűnése
    const cel = this.fokusz >= 0 ? 1 : 0;
    if (Math.abs(cel - this.kiemeles) > 0.004) {
      this.kiemeles += (cel - this.kiemeles) * (1 - Math.exp(-dt / 90));
      if (Math.abs(cel - this.kiemeles) > 0.01) animal = true;
      else this.kiemeles = cel;
    }
    if (this.csokkentett) this.kiemeles = cel;

    this.rajzol(b, s);

    this.meres.kepek++;
    const ms = performance.now() - t0;
    this.meres.rajzMs.push(ms);
    if (this.meres.rajzMs.length > 240) this.meres.rajzMs.shift();
    if (animal || this.fizikaFut || this.huz) this.kerKeret();
    else this.utolso = 0;
  }

  private kepSugar(i: number): number {
    const k = this.k;
    const n = k <= 1 ? k : 1 + 0.38 * (k - 1);
    return korlat(this.r0[i] * n, k < 0.35 ? 1.6 : 2.4, 17);
  }

  private rajzol(b: Bemenet, s: Szinek): void {
    const { ctx, w, h, k, tx, ty } = this;
    const g = b.adat;
    const n = g.n;
    ctx.setTransform(this.dpr, 0, 0, this.dpr, 0, 0);
    ctx.clearRect(0, 0, w, h);

    // képernyő-koordináták, láthatóság, találati rács
    this.racsW = Math.ceil(w / CELLA);
    this.racsH = Math.ceil(h / CELLA);
    if (this.racsFej.length !== this.racsW * this.racsH) this.racsFej = new Int32Array(this.racsW * this.racsH);
    this.racsFej.fill(-1);
    const m = 40;
    for (let i = 0; i < n; i++) {
      if (!b.lathato[i]) {
        this.kepen[i] = 0;
        continue;
      }
      const x = this.poz[2 * i] * k + tx;
      const y = this.poz[2 * i + 1] * k + ty;
      this.sx[i] = x;
      this.sy[i] = y;
      const r = this.kepSugar(i);
      this.sr[i] = r;
      const be = x >= -m && x <= w + m && y >= -m && y <= h + m;
      this.kepen[i] = be ? 1 : 0;
      if (x >= 0 && x < w && y >= 0 && y < h) {
        const c = Math.floor(y / CELLA) * this.racsW + Math.floor(x / CELLA);
        this.racsKov[i] = this.racsFej[c];
        this.racsFej[c] = i;
      }
    }

    const kie = this.fokusz >= 0 ? this.kiemeles : 0;
    this.elek(b, s, kie);
    if (kie > 0.001) {
      this.csucsok(b, 1, 1 - 0.86 * kie);
      this.csucsok(b, 2, 1);
    } else this.csucsok(b, 0, 1);
    this.jelolesek(b, s);
    this.cimkek(b, s);
  }

  private elek(b: Bemenet, s: Szinek, kie: number): void {
    const { ctx, k, w, h } = this;
    const g = b.adat;
    const E = g.elek;
    const m = 40;
    const vonal = korlat(0.35 + 0.55 * k, 0.55, 1.3) * korlat(b.vonalSzorzo, 0.3, 3);
    // sűrűségi tényező: sok látszó él halványabb
    let latszo = 0;
    for (let e = 0; e < E.length; e += 2) {
      const a = E[e];
      const c = E[e + 1];
      if (this.kepen[a] && this.kepen[c]) latszo++;
    }
    const suruseg = korlat(1.45 - Math.log10(Math.max(1, latszo)) / 4, 0.55, 1);
    const alfa = korlat(0.2 + 0.16 * k, 0.2, 0.42) * suruseg;

    ctx.lineCap = 'round';
    for (const kiemelt of kie > 0.001 ? [false, true] : [false]) {
      ctx.beginPath();
      for (let e = 0; e < E.length; e += 2) {
        const a = E[e];
        const c = E[e + 1];
        if (!b.lathato[a] || !b.lathato[c]) continue;
        const ax = this.sx[a];
        const ay = this.sy[a];
        const cx = this.sx[c];
        const cy = this.sy[c];
        if (
          (ax < -m && cx < -m) || (ax > w + m && cx > w + m) || (ay < -m && cy < -m) || (ay > h + m && cy > h + m)
        )
          continue;
        const erint = kie > 0.001 && (a === this.fokusz || c === this.fokusz);
        if (kie > 0.001 && erint !== kiemelt) continue;
        ctx.moveTo(ax, ay);
        ctx.lineTo(cx, cy);
      }
      if (kiemelt) {
        ctx.globalAlpha = Math.min(1, 0.55 + 0.4 * kie);
        ctx.strokeStyle = s.elKiemelt;
        ctx.lineWidth = vonal * 1.8;
      } else {
        ctx.globalAlpha = kie > 0.001 ? alfa * (1 - 0.7 * kie) : alfa;
        ctx.strokeStyle = s.el;
        ctx.lineWidth = vonal;
      }
      ctx.stroke();
    }
    ctx.globalAlpha = 1;

    // irányító nyilak: közelítve, a céloldalon
    if (b.nyil && k > 0.9) {
      ctx.beginPath();
      for (let e = 0; e < E.length; e += 2) {
        const a = E[e];
        const c = E[e + 1];
        if (!b.lathato[a] || !b.lathato[c] || !this.kepen[a] || !this.kepen[c]) continue;
        if (kie > 0.001 && a !== this.fokusz && c !== this.fokusz) continue;
        const ir = g.irany[e >> 1];
        if (ir & 1) this.nyil(a, c);
        if (ir & 2) this.nyil(c, a);
      }
      ctx.globalAlpha = kie > 0.001 ? 0.9 : Math.min(0.7, alfa * 1.6);
      ctx.fillStyle = kie > 0.001 ? s.elKiemelt : s.el;
      ctx.fill();
      ctx.globalAlpha = 1;
    }
  }

  /** Nyílhegy az `a`-ból a `c` felé mutató élhez, a `c` pereménél (útvonal-építés; a hívó tölti ki). */
  private nyil(a: number, c: number): void {
    const dx = this.sx[c] - this.sx[a];
    const dy = this.sy[c] - this.sy[a];
    const l = Math.hypot(dx, dy);
    const meret = korlat(2.5 + this.k * 1.5, 3, 6);
    if (l < this.sr[c] + this.sr[a] + meret * 2) return;
    const ux = dx / l;
    const uy = dy / l;
    const bx = this.sx[c] - ux * (this.sr[c] + 1);
    const by = this.sy[c] - uy * (this.sr[c] + 1);
    const ctx = this.ctx;
    ctx.moveTo(bx, by);
    ctx.lineTo(bx - ux * meret * 1.6 - uy * meret, by - uy * meret * 1.6 + ux * meret);
    ctx.lineTo(bx - ux * meret * 1.6 + uy * meret, by - uy * meret * 1.6 - ux * meret);
    ctx.closePath();
  }

  /** `mod`: 0 = minden látható csúcs, 1 = a fókusz környékén kívüliek, 2 = a fókusz és a szomszédai. */
  private csucsok(b: Bemenet, mod: 0 | 1 | 2, alfa: number): void {
    const { ctx } = this;
    const s = this.szinek!;
    ctx.globalAlpha = alfa;
    const gyuru = this.k * 3.4 >= 2.6;
    for (let v = 0; v < this.vedoKulcs.length; v++) {
      const kulcs = this.vedoKulcs[v];
      const alakId = kulcs % 5;
      const szin = this.palettaSzinek[(kulcs - alakId) / 5] ?? s.melleklet;
      ctx.beginPath();
      let van = false;
      for (let q = this.vedoKezd[v]; q < this.vedoKezd[v + 1]; q++) {
        const i = this.rendezett[q];
        if (!b.lathato[i] || !this.kepen[i]) continue;
        if (mod === 1 && this.szomsz[i]) continue;
        if (mod === 2 && !this.szomsz[i]) continue;
        van = true;
        this.alakUt(alakId, this.sx[i], this.sy[i], this.sr[i]);
      }
      if (!van) continue;
      if (alakId === GYURU) {
        ctx.fillStyle = s.felulet;
        ctx.fill();
        ctx.strokeStyle = szin;
        ctx.lineWidth = 1.6;
        ctx.stroke();
      } else {
        ctx.fillStyle = szin;
        ctx.fill();
        if (gyuru) {
          ctx.strokeStyle = s.felulet;
          ctx.lineWidth = 0.8;
          ctx.stroke();
        }
      }
    }
    ctx.globalAlpha = 1;
  }

  private alakUt(a: number, x: number, y: number, r: number): void {
    const ctx = this.ctx;
    switch (a) {
      case NEGYZET:
        ctx.rect(x - r * 0.9, y - r * 0.9, r * 1.8, r * 1.8);
        break;
      case HAROMSZOG:
        ctx.moveTo(x, y - r * 1.15);
        ctx.lineTo(x + r * 1.05, y + r * 0.85);
        ctx.lineTo(x - r * 1.05, y + r * 0.85);
        ctx.closePath();
        break;
      case ROMBUSZ:
        ctx.moveTo(x, y - r * 1.2);
        ctx.lineTo(x + r * 1.2, y);
        ctx.lineTo(x, y + r * 1.2);
        ctx.lineTo(x - r * 1.2, y);
        ctx.closePath();
        break;
      default:
        ctx.moveTo(x + r, y);
        ctx.arc(x, y, r, 0, Math.PI * 2);
    }
  }

  private jelolesek(b: Bemenet, s: Szinek): void {
    const { ctx } = this;
    const gyuru = (i: number, szin: string, extra: number, szel: number) => {
      if (i < 0 || !b.lathato[i] || !this.kepen[i]) return;
      ctx.beginPath();
      ctx.arc(this.sx[i], this.sy[i], this.sr[i] + extra, 0, Math.PI * 2);
      ctx.strokeStyle = szin;
      ctx.lineWidth = szel;
      ctx.stroke();
    };
    for (const i of this.talalatok) gyuru(i, s.talalat, 3, 2);
    gyuru(this.kijelolt, s.kijelolt, 3.5, 2);
    if (this.hover >= 0 && this.hover !== this.kijelolt) gyuru(this.hover, s.elKiemelt, 3, 1.5);
  }

  private cimkek(b: Bemenet, s: Szinek): void {
    const { ctx, w, h } = this;
    const g = b.adat;
    const kie = this.fokusz >= 0 ? this.kiemeles : 0;
    const fontos = new Set<number>(this.talalatok);
    if (this.kijelolt >= 0) fontos.add(this.kijelolt);
    if (this.hover >= 0) fontos.add(this.hover);
    if (this.huz) fontos.add(this.huz.i);

    // jelöltek: elég nagy csúcsok (nagy fokszámúak hamarabb)
    const jeloltek: { i: number; alfa: number; fontossag: number }[] = [];
    for (let i = 0; i < g.n; i++) {
      if (!b.lathato[i] || !this.kepen[i]) continue;
      const x = this.sx[i];
      const y = this.sy[i];
      if (x < 0 || x > w || y < 0 || y > h) continue;
      if (fontos.has(i)) {
        jeloltek.push({ i, alfa: 1, fontossag: 1e9 });
        continue;
      }
      const alfa = simitas(6.5, 10, this.sr[i]) * (kie > 0 && !this.szomsz[i] ? 1 - 0.86 * kie : 1);
      if (alfa > 0.02) jeloltek.push({ i, alfa, fontossag: g.fok[i] });
    }
    if (!jeloltek.length) return;
    jeloltek.sort((a, c) => c.fontossag - a.fontossag);
    const max = this.k > 2 ? 420 : 260;

    const cw = Math.ceil(w / CIMKE_CELLA);
    this.cimkeFoglalt.fill(0);
    ctx.font = this.betu;
    ctx.textBaseline = 'middle';
    ctx.textAlign = 'center';
    ctx.lineJoin = 'round';
    ctx.lineWidth = 3;
    let db = 0;
    for (const j of jeloltek) {
      if (db >= max) break;
      let nev = g.nev[j.i];
      if (nev.length > 42) nev = nev.slice(0, 41) + '…';
      const sz = ctx.measureText(nev).width;
      const x = this.sx[j.i];
      const y = this.sy[j.i] + this.sr[j.i] + 8;
      const c0 = Math.max(0, Math.floor((x - sz / 2) / CIMKE_CELLA));
      const c1 = Math.min(cw - 1, Math.floor((x + sz / 2) / CIMKE_CELLA));
      const r0 = Math.max(0, Math.floor((y - 7) / CIMKE_CELLA));
      const r1 = Math.min(Math.ceil(h / CIMKE_CELLA) - 1, Math.floor((y + 7) / CIMKE_CELLA));
      let szabad = true;
      for (let r = r0; r <= r1 && szabad; r++) for (let c = c0; c <= c1; c++) if (this.cimkeFoglalt[r * cw + c]) szabad = false;
      if (!szabad && j.fontossag < 1e9) continue;
      for (let r = r0; r <= r1; r++) for (let c = c0; c <= c1; c++) this.cimkeFoglalt[r * cw + c] = 1;
      ctx.globalAlpha = j.alfa;
      ctx.strokeStyle = s.halo;
      ctx.strokeText(nev, x, y);
      ctx.fillStyle = s.szoveg;
      ctx.fillText(nev, x, y);
      db++;
    }
    ctx.globalAlpha = 1;
  }

  // ------------------------------------------------------------------ bemenet

  private bemenetTelepit(): void {
    const c = this.canvas;
    const figyel = <K extends keyof HTMLElementEventMap>(tipus: K, f: (e: HTMLElementEventMap[K]) => void, opt?: AddEventListenerOptions) => {
      c.addEventListener(tipus, f as EventListener, opt);
      this.leiratkoz.push(() => c.removeEventListener(tipus, f as EventListener));
    };
    const hely = (e: MouseEvent): [number, number] => {
      const r = c.getBoundingClientRect();
      return [e.clientX - r.left, e.clientY - r.top];
    };

    figyel('pointerdown', (e) => {
      if (e.button !== 0) return;
      c.focus({ preventScroll: true });
      const [x, y] = hely(e);
      const i = this.csucsAlatt(x, y);
      const [wx, wy] = this.vilag(x, y);
      this.kifutas = null;
      this.repules = null;
      this.mintak = [{ t: e.timeStamp, x, y }];
      this.huz = {
        id: e.pointerId,
        i,
        x0: x,
        y0: y,
        sx: x,
        sy: y,
        mozdult: false,
        wx,
        wy,
        mod: e.metaKey && e.altKey ? 'osztas' : e.metaKey || e.ctrlKey ? 'ujful' : 'aktiv',
      };
      c.setPointerCapture(e.pointerId);
    });

    figyel('pointermove', (e) => {
      const [x, y] = hely(e);
      const d = this.huz;
      if (d && d.id === e.pointerId) {
        if (!d.mozdult && Math.hypot(x - d.x0, y - d.y0) > KATTINTAS_KUSZOB) {
          d.mozdult = true;
          c.style.cursor = 'grabbing';
        }
        if (d.mozdult) {
          if (d.i >= 0) {
            [d.wx, d.wy] = this.vilag(x, y);
            this.poz[2 * d.i] = d.wx;
            this.poz[2 * d.i + 1] = d.wy;
            this.e.fizika({ tipus: 'rogzit', i: d.i, x: d.wx, y: d.wy, huz: true });
          } else {
            this.tx += x - d.sx;
            this.ty += y - d.sy;
            this.nezetModositva = true;
            this.mintak.push({ t: e.timeStamp, x, y });
            if (this.mintak.length > 8) this.mintak.shift();
          }
          this.kerKeret();
        }
        d.sx = x;
        d.sy = y;
        return;
      }
      this.hoverFrissit(x, y);
    });

    const vege = (e: PointerEvent) => {
      const d = this.huz;
      if (!d || d.id !== e.pointerId) return;
      this.huz = null;
      c.style.cursor = '';
      if (c.hasPointerCapture(e.pointerId)) c.releasePointerCapture(e.pointerId);
      if (e.type === 'pointercancel') return;
      if (!d.mozdult) {
        // kattintás: a csúcs megnyitása, vagy (üres helyre) a kijelölés törlése
        if (d.i >= 0) {
          this.e.megnyit(d.i, d.mod);
          this.kijeloles(d.i);
          this.e.kijeloles?.(d.i);
        } else if (this.kijelolt >= 0) {
          this.kijeloles(-1);
          this.e.kijeloles?.(-1);
        }
        return;
      }
      if (d.i >= 0) {
        this.e.fizika({ tipus: 'enged', i: d.i, marad: e.altKey });
      } else if (!this.csokkentett) {
        // lendületes kifutás az utolsó ~90 ms mintájából
        const most = e.timeStamp;
        const m = this.mintak.filter((p) => most - p.t < 90);
        if (m.length >= 2) {
          const a = m[0];
          const z = m[m.length - 1];
          const dt = Math.max(1, z.t - a.t);
          const vx = (z.x - a.x) / dt;
          const vy = (z.y - a.y) / dt;
          if (Math.hypot(vx, vy) > 0.15) {
            this.kifutas = { vx, vy };
            this.kerKeret();
          }
        }
      }
    };
    figyel('pointerup', vege);
    figyel('pointercancel', vege);
    figyel('pointerleave', () => {
      if (!this.huz) this.hoverBeallit(-1, 0, 0);
    });

    figyel(
      'wheel',
      (e) => {
        e.preventDefault();
        const [x, y] = hely(e);
        // csípés (ctrl) érzékenyebb, a kerék és a trackpad két ujjal: egyenletes nagyítás
        const hatas = e.deltaMode === 1 ? e.deltaY * 16 : e.deltaMode === 2 ? e.deltaY * 100 : e.deltaY;
        const erzekenyseg = e.ctrlKey ? 0.01 : 0.0018;
        this.nagyit(Math.exp(-korlat(hatas, -240, 240) * erzekenyseg), x, y);
        this.hoverFrissit(x, y);
      },
      { passive: false },
    );

    // Safari és WKWebView: a csípés `gesture*` eseményekkel jön (nem `ctrl+wheel`)
    const gl = c as unknown as { addEventListener: (t: string, f: (e: Event) => void, o?: AddEventListenerOptions) => void; removeEventListener: (t: string, f: (e: Event) => void) => void };
    const gesztusEsemeny = (tipus: 'gesturestart' | 'gesturechange' | 'gestureend') => {
      const f = (ev: Event) => {
        ev.preventDefault();
        const e = ev as Event & { scale: number; clientX: number; clientY: number };
        const r = c.getBoundingClientRect();
        if (tipus === 'gesturestart') this.gesztus = { k0: this.k, cx: e.clientX - r.left, cy: e.clientY - r.top };
        else if (tipus === 'gesturechange' && this.gesztus) {
          const cel = korlat(this.gesztus.k0 * e.scale, this.kMin(), K_MAX);
          this.nagyit(cel / this.k, this.gesztus.cx, this.gesztus.cy);
        } else if (tipus === 'gestureend') this.gesztus = null;
      };
      gl.addEventListener(tipus, f, { passive: false });
      this.leiratkoz.push(() => gl.removeEventListener(tipus, f));
    };
    gesztusEsemeny('gesturestart');
    gesztusEsemeny('gesturechange');
    gesztusEsemeny('gestureend');

    figyel('keydown', (e) => {
      if (e.metaKey || e.ctrlKey || e.altKey) return;
      const kozep: [number, number] = [this.w / 2, this.h / 2];
      let kezelt = true;
      switch (e.key) {
        case '+':
        case '=':
          this.nagyit(1.4, ...kozep);
          break;
        case '-':
        case '_':
          this.nagyit(1 / 1.4, ...kozep);
          break;
        case '0':
          this.teljesNezet();
          break;
        case 'ArrowLeft':
          this.tx += 90; this.nezetModositva = true;
          this.kerKeret();
          break;
        case 'ArrowRight':
          this.tx -= 90; this.nezetModositva = true;
          this.kerKeret();
          break;
        case 'ArrowUp':
          this.ty += 90; this.nezetModositva = true;
          this.kerKeret();
          break;
        case 'ArrowDown':
          this.ty -= 90; this.nezetModositva = true;
          this.kerKeret();
          break;
        case 'Enter':
          if (this.kijelolt >= 0) this.e.megnyit(this.kijelolt, e.shiftKey ? 'ujful' : 'aktiv');
          break;
        case 'Escape':
          if (this.kijelolt >= 0) {
            this.kijeloles(-1);
            this.e.kijeloles?.(-1);
          } else kezelt = false;
          break;
        default:
          kezelt = false;
      }
      if (kezelt) e.preventDefault();
    });
  }

  private hoverFrissit(x: number, y: number): void {
    const i = this.csucsAlatt(x, y);
    this.hoverBeallit(i, x, y);
  }

  private hoverBeallit(i: number, x: number, y: number): void {
    if (i === this.hover) return;
    this.hover = i;
    this.canvas.style.cursor = i >= 0 ? 'pointer' : '';
    this.fokuszSzomszedok();
    this.e.hover?.(i, x, y);
    this.kerKeret();
  }
}
