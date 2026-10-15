// A gráfnézet fizikája: erőirányított elrendezés (a legacy `graf-fizika.js` TypeScript-portja, C13).
//
// A modell a d3-force-é: rugók az éleken, Barnes–Hut-közelítésű taszítás minden csúcs között, gyenge középre húzás,
// csillapítás és egy „hőmérséklet” (alpha), amely lehűl; nyugalomban a számolás magától megáll, a gráf nem fogyaszt
// processzort. Típusos tömbök mindenütt (a négyfa is): tickenként nincs objektum-foglalás. Determinisztikus: ugyanarra
// a gráfra ugyanaz az elrendezés (a véletlen egy rögzített LCG). Tiszta modul: DOM és Worker nélkül tesztelhető.

/** A csúszkák szorzók az alapértékekre (1 = alap); az Obsidian graph.json értékei is ezekre képeződnek le. */
export interface ErokBeallitas {
  taszitas: number;
  rugo: number;
  rugohossz: number;
  kozep: number;
  csillapitas: number;
}

export const ALAP_EROK: ErokBeallitas = { taszitas: 1, rugo: 1, rugohossz: 1, kozep: 1, csillapitas: 1 };

export class Fizika {
  readonly n: number;
  readonly x: Float64Array;
  readonly y: Float64Array;
  readonly vx: Float64Array;
  readonly vy: Float64Array;
  /** A rögzített csúcs helyzete; NaN = szabad. */
  readonly fx: Float64Array;
  readonly fy: Float64Array;
  readonly aktiv: Uint8Array;
  alpha = 1;
  alphaCel = 0;
  readonly alphaMin = 0.001;
  readonly alphaLecseng = 1 - Math.pow(0.001, 1 / 300); // ~300 tick alatt hűl ki, mint a d3-ban

  private readonly elek: Int32Array; // [s0, t0, s1, t1, …] irányítatlan párok
  private readonly m: number;
  private readonly fok: Float64Array;
  private readonly bias: Float64Array;
  private readonly erosseg: Float64Array;
  private mag = 0x9e3779b9; // a determinisztikus „véletlen”
  private b: ErokBeallitas = { ...ALAP_EROK };
  private taszitasErosseg = 0;
  private rugohossz = 0;
  private kozep = 0;
  private sebessegMarad = 0;
  private readonly theta2 = 0.81; // Barnes–Hut θ = 0,9
  private readonly tavMin2 = 1;

  // négyfa
  private qkap = 0;
  private qdb = 0;
  private qx!: Float64Array; // a cella bal alsó sarka
  private qy!: Float64Array;
  private qs!: Float64Array; // oldalhossz
  private qm!: Float64Array; // töltés-összeg
  private qmx!: Float64Array; // a töltés súlypontja (összegként)
  private qmy!: Float64Array;
  private qpt!: Int32Array; // −1 üres levél · −2 belső · ≥0 egy pont
  private qch!: Int32Array;
  private verem!: Int32Array;

  constructor(n: number, elek: Int32Array, poz: Float32Array, beall: Partial<ErokBeallitas> = {}) {
    this.n = n;
    this.x = new Float64Array(n);
    this.y = new Float64Array(n);
    this.vx = new Float64Array(n);
    this.vy = new Float64Array(n);
    this.fx = new Float64Array(n).fill(NaN);
    this.fy = new Float64Array(n).fill(NaN);
    this.aktiv = new Uint8Array(n).fill(1);
    for (let i = 0; i < n; i++) {
      this.x[i] = poz[2 * i];
      this.y[i] = poz[2 * i + 1];
    }
    this.elek = elek;
    this.m = elek.length >> 1;
    this.fok = new Float64Array(n);
    this.bias = new Float64Array(this.m);
    this.erosseg = new Float64Array(this.m);
    this.beallit(beall);
    this.negyfa(Math.max(64, 4 * n + 16));
  }

  beallit(b: Partial<ErokBeallitas>): void {
    this.b = { ...this.b, ...b };
    this.taszitasErosseg = -34 * this.b.taszitas; // a d3 alapja −30; a vault sűrű, egy kicsit több levegő
    this.rugohossz = 34 * this.b.rugohossz;
    this.kozep = 0.035 * this.b.kozep;
    this.sebessegMarad = 1 - Math.min(0.9, 0.42 * this.b.csillapitas);
    this.fokok();
  }

  /** A maszk: 1 = részt vesz (a rejtett csúcs nem taszít, nem húz, és a fokok újraszámolódnak). */
  aktival(maszk: ArrayLike<number>): void {
    this.aktiv.set(maszk);
    this.fokok();
  }

  private fokok(): void {
    const { elek, fok, aktiv } = this;
    fok.fill(0);
    for (let e = 0; e < this.m; e++) {
      const s = elek[2 * e];
      const t = elek[2 * e + 1];
      if (aktiv[s] && aktiv[t]) {
        fok[s]++;
        fok[t]++;
      }
    }
    for (let e = 0; e < this.m; e++) {
      const a = fok[elek[2 * e]] || 1;
      const c = fok[elek[2 * e + 1]] || 1;
      this.bias[e] = a / (a + c);
      this.erosseg[e] = this.b.rugo / Math.min(a, c);
    }
  }

  private veletlen(): number {
    // [−0,5 … 0,5) · 1e−6 — csak az egybeeső pontokhoz
    this.mag = (Math.imul(this.mag, 1664525) + 1013904223) >>> 0;
    return (this.mag / 4294967296 - 0.5) * 1e-6;
  }

  // ------------------------------------------------------------------ Barnes–Hut négyfa (típusos tömbök)

  private negyfa(kap: number): void {
    this.qkap = kap;
    this.qx = new Float64Array(kap);
    this.qy = new Float64Array(kap);
    this.qs = new Float64Array(kap);
    this.qm = new Float64Array(kap);
    this.qmx = new Float64Array(kap);
    this.qmy = new Float64Array(kap);
    this.qpt = new Int32Array(kap);
    this.qch = new Int32Array(kap * 4);
    this.verem = new Int32Array(kap);
  }

  private cella(x: number, y: number, s: number): number {
    if (this.qdb >= this.qkap) {
      // ritka: mélyen egymásra tolt pontok. Csak a szerkezet másolódik, az összesítés (qm, qmx, qmy) minden
      // tickben újraszámolódik.
      const { qx, qy, qs, qpt, qch } = this;
      this.negyfa(this.qkap * 2);
      this.qx.set(qx);
      this.qy.set(qy);
      this.qs.set(qs);
      this.qpt.set(qpt);
      this.qch.set(qch);
    }
    const c = this.qdb++;
    this.qx[c] = x;
    this.qy[c] = y;
    this.qs[c] = s;
    this.qm[c] = 0;
    this.qmx[c] = 0;
    this.qmy[c] = 0;
    this.qpt[c] = -1;
    this.qch[4 * c] = this.qch[4 * c + 1] = this.qch[4 * c + 2] = this.qch[4 * c + 3] = -1;
    return c;
  }

  private gyerek(c: number, i: number): number {
    const h = this.qs[c] / 2;
    const jobb = this.x[i] >= this.qx[c] + h ? 1 : 0;
    const fent = this.y[i] >= this.qy[c] + h ? 2 : 0;
    const q = jobb | fent;
    let g = this.qch[4 * c + q];
    if (g < 0) {
      g = this.cella(this.qx[c] + (jobb ? h : 0), this.qy[c] + (fent ? h : 0), h);
      this.qch[4 * c + q] = g;
    }
    return g;
  }

  private epit(): void {
    const { n, x, y, aktiv } = this;
    let x0 = Infinity;
    let y0 = Infinity;
    let x1 = -Infinity;
    let y1 = -Infinity;
    for (let i = 0; i < n; i++) {
      if (!aktiv[i]) continue;
      if (x[i] < x0) x0 = x[i];
      if (x[i] > x1) x1 = x[i];
      if (y[i] < y0) y0 = y[i];
      if (y[i] > y1) y1 = y[i];
    }
    this.qdb = 0;
    if (x0 === Infinity) {
      this.cella(0, 0, 1);
      return;
    }
    const s = Math.max(x1 - x0, y1 - y0, 1) * 1.0001 + 1e-3;
    this.cella(x0, y0, s);
    for (let i = 0; i < n; i++) {
      if (!aktiv[i]) continue;
      let c = 0;
      let mely = 0;
      for (;;) {
        const p = this.qpt[c];
        if (p === -1) {
          this.qpt[c] = i; // üres levél
          break;
        }
        if (p >= 0) {
          // foglalt levél: a régi pont lejjebb
          if (x[p] === x[i] && y[p] === y[i]) {
            x[i] += this.veletlen();
            y[i] += this.veletlen();
          }
          if (++mely > 48) {
            x[i] += this.veletlen() * 1e3;
            y[i] += this.veletlen() * 1e3;
            mely = 0;
            c = 0;
            continue;
          }
          this.qpt[c] = -2;
          const g = this.gyerek(c, p);
          this.qpt[g] = p;
        }
        c = this.gyerek(c, i);
        if (this.qpt[c] === -1 && this.qch[4 * c] < 0 && this.qch[4 * c + 1] < 0 && this.qch[4 * c + 2] < 0 && this.qch[4 * c + 3] < 0) {
          this.qpt[c] = i;
          break;
        }
      }
    }
    // a töltések összesítése alulról: a gyerek mindig később jön létre, mint a szülője
    const t = this.taszitasErosseg;
    for (let c = this.qdb - 1; c >= 0; c--) {
      const p = this.qpt[c];
      if (p >= 0) {
        this.qm[c] = t;
        this.qmx[c] = x[p] * t;
        this.qmy[c] = y[p] * t;
        continue;
      }
      let m = 0;
      let mx = 0;
      let my = 0;
      for (let k = 0; k < 4; k++) {
        const g = this.qch[4 * c + k];
        if (g >= 0) {
          m += this.qm[g];
          mx += this.qmx[g];
          my += this.qmy[g];
        }
      }
      this.qm[c] = m;
      this.qmx[c] = mx;
      this.qmy[c] = my;
    }
  }

  private taszitas(alpha: number): void {
    const { n, x, y, vx, vy, aktiv, qm, qmx, qmy, qs, qpt, qch, verem, theta2, tavMin2 } = this;
    for (let i = 0; i < n; i++) {
      if (!aktiv[i]) continue;
      const xi = x[i];
      const yi = y[i];
      let fx = 0;
      let fy = 0;
      let sp = 0;
      verem[sp++] = 0;
      while (sp > 0) {
        const c = verem[--sp];
        const m = qm[c];
        if (m === 0) continue;
        const p = qpt[c];
        if (p === i) continue;
        let dx = qmx[c] / m - xi;
        let dy = qmy[c] / m - yi;
        let l2 = dx * dx + dy * dy;
        const w = qs[c];
        if (p >= 0 || (w * w) / theta2 < l2) {
          // levél, vagy elég messze: egy tömegként
          if (l2 === 0) {
            dx = this.veletlen();
            dy = this.veletlen();
            l2 = dx * dx + dy * dy;
          }
          if (l2 < tavMin2) l2 = Math.sqrt(tavMin2 * l2);
          const f = (m * alpha) / l2;
          fx += dx * f;
          fy += dy * f;
          continue;
        }
        for (let k = 0; k < 4; k++) {
          const g = qch[4 * c + k];
          if (g >= 0) verem[sp++] = g;
        }
      }
      vx[i] += fx;
      vy[i] += fy;
    }
  }

  // ------------------------------------------------------------------ egy lépés

  tick(): void {
    const { n, x, y, vx, vy, fx, fy, aktiv, elek, bias, erosseg } = this;
    this.alpha += (this.alphaCel - this.alpha) * this.alphaLecseng;
    const alpha = this.alpha;
    // rugók (d3-forceLink: a sebességgel előretolt helyzetből, a fokszám szerinti megosztással)
    const L = this.rugohossz;
    for (let e = 0; e < this.m; e++) {
      const s = elek[2 * e];
      const t = elek[2 * e + 1];
      if (!aktiv[s] || !aktiv[t]) continue;
      let dx = x[t] + vx[t] - x[s] - vx[s];
      let dy = y[t] + vy[t] - y[s] - vy[s];
      let l = Math.sqrt(dx * dx + dy * dy) || 1e-6;
      l = ((l - L) / l) * alpha * erosseg[e];
      dx *= l;
      dy *= l;
      const b = bias[e];
      vx[t] -= dx * b;
      vy[t] -= dy * b;
      vx[s] += dx * (1 - b);
      vy[s] += dy * (1 - b);
    }
    this.epit();
    this.taszitas(alpha);
    const k = this.kozep * alpha;
    const marad = this.sebessegMarad;
    for (let i = 0; i < n; i++) {
      if (!aktiv[i]) continue;
      if (fx[i] === fx[i]) {
        // rögzített (nem NaN)
        x[i] = fx[i];
        y[i] = fy[i];
        vx[i] = 0;
        vy[i] = 0;
        continue;
      }
      vx[i] = (vx[i] - x[i] * k) * marad;
      vy[i] = (vy[i] - y[i] * k) * marad;
      x[i] += vx[i];
      y[i] += vy[i];
    }
  }

  nyugalomban(): boolean {
    return this.alpha < this.alphaMin && this.alphaCel === 0;
  }

  helyzetek(): Float32Array {
    const ki = new Float32Array(2 * this.n);
    for (let i = 0; i < this.n; i++) {
      ki[2 * i] = this.x[i];
      ki[2 * i + 1] = this.y[i];
    }
    return ki;
  }
}
