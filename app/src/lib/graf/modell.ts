// A gráf adatmodellje (C13): a core gráfja (`/api/vault/graf`), a fájltípusok (`/api/vault/fa`) és a jegyzetenkénti
// címke/tulajdonság (`/api/vault/graf-meta`) összefűzése csúcstáblává; szomszédsági tömbök, szűrés, helyi gráf (BFS),
// színcsoportok és keresés. Tiszta modul (DOM nélkül): a csúcs- és élhalmaz pontosan a core gráfja, a felület nem old
// fel linket és nem talál ki élt (ARCHITECTURE 2., L42).

import { egyszerusit, lekerdezesFordit, type Csucs } from './lekerdezes';

export type FajlTipus = 'md' | 'canvas' | 'base' | 'pdf' | 'kep' | 'video' | 'hang' | 'felirat' | 'egyeb';

/** A `GET /api/vault/graf` válasza. */
export interface GrafValasz {
  csucsok: string[];
  elek: [string, string][];
  feloldatlan?: Record<string, number>;
  tobbertelmu?: Record<string, number>;
  canvas_hiba?: [string, string][];
}

/** A `GET /api/vault/graf-meta` válasza. */
export interface GrafMeta {
  cimkek: Record<string, string[]>;
  tulajdonsagok: Record<string, Record<string, string[]>>;
}

export interface Szurok {
  lekerdezes: string;
  mellekletek: boolean;
  arvak: boolean;
}

export interface SzinCsoport {
  lekerdezes: string;
  szin: string;
}

export interface Helyi {
  kozeppont: number;
  melyseg: number;
}

export const MAX_MELYSEG = 3;

const NEM_MELLEKLET = new Set<FajlTipus>(['md', 'canvas', 'base']);

/** A megjelenített név: jegyzetnél kiterjesztés nélkül (mint az Obsidianban), másnál teljes fájlnév. */
export function nevUtbol(ut: string): string {
  const alap = ut.slice(ut.lastIndexOf('/') + 1);
  return alap.toLowerCase().endsWith('.md') ? alap.slice(0, -3) : alap;
}

export function fnv(s: string, mag: number): number {
  let h = mag >>> 0;
  for (let i = 0; i < s.length; i++) {
    h ^= s.charCodeAt(i);
    h = Math.imul(h, 16777619) >>> 0;
  }
  return h;
}

/** A szerkezet (csúcsok és élek) aláírása: ha nem változott, a fizikát nem kell újraindítani. */
function alairasSzamol(utak: readonly string[], elek: Int32Array): string {
  let a = 0x811c9dc5;
  let b = 0x01000193;
  for (const u of utak) {
    a = fnv(u + '\0', a);
    b = fnv(u, b);
  }
  for (let i = 0; i < elek.length; i++) {
    const s = String(elek[i]) + ',';
    a = fnv(s, a);
    b = fnv(s, b ^ i);
  }
  return `${utak.length}:${elek.length >> 1}:${a.toString(16)}${b.toString(16)}`;
}

export class GrafAdat {
  readonly n: number;
  readonly ut: string[];
  readonly nev: string[];
  readonly tipus: FajlTipus[];
  readonly felsoMappa: string[];
  /** A lekérdezés-nyelv csúcsai (egyszerűsített szövegekkel). */
  readonly csucsok: Csucs[];
  /** A címkék eredeti írásmóddal (a tooltipnek). */
  readonly cimkek: string[][];
  /** A core gráfjának irányított élei [forrás, cél, …] (önhurokkal), csúcsindexekben. */
  readonly iranyitott: Int32Array;
  /** Egyedi irányítatlan élek [a, b, …] (a < b, önhurok nélkül). */
  readonly elek: Int32Array;
  /** Élenként: 1 = a→b, 2 = b→a, 3 = mindkettő. */
  readonly irany: Uint8Array;
  readonly onhurok: Uint8Array;
  readonly fok: Int32Array;
  /** CSR szomszédság: a `lista[kezd[i] … kezd[i + 1])` az i csúcs szomszédai. */
  readonly kezd: Int32Array;
  readonly lista: Int32Array;
  /** Hány élvégpont nem volt csúcs (a core gráfjában 0): jelzés a paritás-vizsgálatnak. */
  readonly hianyzoElek: number;
  readonly alairas: string;
  private readonly index: Map<string, number>;

  constructor(valasz: GrafValasz, tipusok: (ut: string) => FajlTipus | undefined, meta?: GrafMeta | null) {
    const ut = valasz.csucsok;
    const n = ut.length;
    this.n = n;
    this.ut = ut;
    this.index = new Map(ut.map((u, i) => [u, i]));
    this.nev = ut.map(nevUtbol);
    this.tipus = ut.map((u) => tipusok(u) ?? 'egyeb');
    this.felsoMappa = ut.map((u) => {
      const i = u.indexOf('/');
      return i < 0 ? '' : u.slice(0, i);
    });

    const ir: number[] = [];
    let hianyzo = 0;
    for (const [s, t] of valasz.elek) {
      const a = this.index.get(s);
      const b = this.index.get(t);
      if (a === undefined || b === undefined) {
        hianyzo++;
        continue;
      }
      ir.push(a, b);
    }
    this.hianyzoElek = hianyzo;
    this.iranyitott = Int32Array.from(ir);

    // egyedi irányítatlan élek az irány-bitekkel
    const par = new Map<number, number>(); // kulcs = a * n + b (a < b) → irány-bitek
    this.onhurok = new Uint8Array(n);
    for (let e = 0; e < ir.length; e += 2) {
      const s = ir[e];
      const t = ir[e + 1];
      if (s === t) {
        this.onhurok[s] = 1;
        continue;
      }
      const a = Math.min(s, t);
      const b = Math.max(s, t);
      const k = a * n + b;
      par.set(k, (par.get(k) ?? 0) | (s < t ? 1 : 2));
    }
    const kulcsok = [...par.keys()].sort((x, y) => x - y);
    const m = kulcsok.length;
    this.elek = new Int32Array(2 * m);
    this.irany = new Uint8Array(m);
    this.fok = new Int32Array(n);
    kulcsok.forEach((k, e) => {
      const a = Math.floor(k / n);
      const b = k - a * n;
      this.elek[2 * e] = a;
      this.elek[2 * e + 1] = b;
      this.irany[e] = par.get(k)!;
      this.fok[a]++;
      this.fok[b]++;
    });
    this.kezd = new Int32Array(n + 1);
    for (let i = 0; i < n; i++) this.kezd[i + 1] = this.kezd[i] + this.fok[i];
    this.lista = new Int32Array(2 * m);
    const toltes = this.kezd.slice(0, n);
    for (let e = 0; e < m; e++) {
      const a = this.elek[2 * e];
      const b = this.elek[2 * e + 1];
      this.lista[toltes[a]++] = b;
      this.lista[toltes[b]++] = a;
    }

    this.cimkek = ut.map((u) => meta?.cimkek[u] ?? []);
    this.csucsok = ut.map((u, i) => {
      const fajlnev = u.slice(u.lastIndexOf('/') + 1);
      const tul = meta?.tulajdonsagok[u];
      let tulN: Record<string, string[]> | undefined;
      if (tul) {
        tulN = {};
        for (const [k, v] of Object.entries(tul)) tulN[k.toLowerCase()] = v.map(egyszerusit);
      }
      return {
        ut: u,
        fajlnev,
        utN: egyszerusit(u),
        fajlnevN: egyszerusit(fajlnev),
        cimkek: this.cimkek[i].map((c) => egyszerusit(c).replace(/^#/, '')),
        tulajdonsagok: tulN,
      };
    });
    this.alairas = alairasSzamol(ut, this.elek);
  }

  /** Az út csúcsindexe, vagy -1. */
  csucsIndex(ut: string): number {
    return this.index.get(ut) ?? -1;
  }

  melleklet(i: number): boolean {
    return !NEM_MELLEKLET.has(this.tipus[i]);
  }

  /** A core gráfjának irányított élei útpárként (a paritás-vizsgálathoz). */
  iranyitottElek(): [string, string][] {
    const ki: [string, string][] = [];
    for (let e = 0; e < this.iranyitott.length; e += 2) ki.push([this.ut[this.iranyitott[e]], this.ut[this.iranyitott[e + 1]]]);
    return ki;
  }

  szomszedok(i: number): Int32Array {
    return this.lista.subarray(this.kezd[i], this.kezd[i + 1]);
  }
}

// ------------------------------------------------------------------ szűrés és helyi gráf

export interface SzuroEredmeny {
  /** 1 = látszik. */
  lathato: Uint8Array;
  /** A lekérdezés nem támogatott eleme (ekkor a szöveges szűrő nem hat). */
  nemTamogatott?: string;
  csucsDb: number;
}

/**
 * Melyik csúcs látszik: a mellékletek és az árvák kapcsolója, a szöveges lekérdezés; helyi gráfnál a középpontból
 * `melyseg` lépésre (irányítatlanul) elérhető, a szűrőn átmenő csúcsok (a középpont mindig látszik).
 */
export function lathatosag(g: GrafAdat, sz: Szurok, helyi?: Helyi | null): SzuroEredmeny {
  const lek = lekerdezesFordit(sz.lekerdezes);
  const szurtLek = lek.tamogatott;
  const alap = new Uint8Array(g.n);
  for (let i = 0; i < g.n; i++) {
    if (!sz.mellekletek && g.melleklet(i)) continue;
    if (!sz.arvak && g.fok[i] === 0) continue;
    if (szurtLek && !lek.ures && !lek.illeszt(g.csucsok[i])) continue;
    alap[i] = 1;
  }
  let lathato = alap;
  if (helyi && helyi.kozeppont >= 0 && helyi.kozeppont < g.n) {
    const melyseg = Math.max(0, Math.min(MAX_MELYSEG, Math.round(helyi.melyseg)));
    lathato = new Uint8Array(g.n);
    lathato[helyi.kozeppont] = 1;
    let front = [helyi.kozeppont];
    for (let lepes = 0; lepes < melyseg && front.length; lepes++) {
      const kov: number[] = [];
      for (const i of front) {
        for (let e = g.kezd[i]; e < g.kezd[i + 1]; e++) {
          const j = g.lista[e];
          if (!lathato[j] && alap[j]) {
            lathato[j] = 1;
            kov.push(j);
          }
        }
      }
      front = kov;
    }
  }
  let db = 0;
  for (let i = 0; i < g.n; i++) db += lathato[i];
  return { lathato, nemTamogatott: szurtLek ? undefined : lek.nemTamogatott, csucsDb: db };
}

/** A látható élek száma (mindkét végpont látszik): egyedi irányítatlan élek. */
export function lathatoElDb(g: GrafAdat, lathato: Uint8Array): number {
  let db = 0;
  for (let e = 0; e < g.elek.length; e += 2) if (lathato[g.elek[e]] && lathato[g.elek[e + 1]]) db++;
  return db;
}

// ------------------------------------------------------------------ színcsoportok

export interface SzinEredmeny {
  /** Csúcsonként a csoport indexe, vagy -1 (nincs találat). */
  csoport: Int16Array;
  /** Csoportonként: a lekérdezés teljes egészében támogatott-e. */
  tamogatott: boolean[];
}

/** Az első illeszkedő csoport nyer (mint az Obsidianban). */
export function szinCsoportok(g: GrafAdat, csoportok: readonly SzinCsoport[]): SzinEredmeny {
  const lekek = csoportok.map((c) => lekerdezesFordit(c.lekerdezes));
  const csoport = new Int16Array(g.n).fill(-1);
  for (let i = 0; i < g.n; i++) {
    for (let k = 0; k < lekek.length; k++) {
      const l = lekek[k];
      if (l.tamogatott && !l.ures && l.illeszt(g.csucsok[i])) {
        csoport[i] = k;
        break;
      }
    }
  }
  return { csoport, tamogatott: lekek.map((l) => l.tamogatott) };
}

// ------------------------------------------------------------------ keresés

/** Ékezetfüggetlen rangsor: névkezdet, a név része, az út része; döntetlennél a rövidebb név, majd a nagyobb fok. */
export function kereses(g: GrafAdat, szoveg: string, lathato: Uint8Array | null, korlat = 12): number[] {
  const q = egyszerusit(szoveg.trim());
  if (!q) return [];
  const talalat: { i: number; r: number }[] = [];
  for (let i = 0; i < g.n; i++) {
    const c = g.csucsok[i];
    const nev = egyszerusit(g.nev[i]);
    let r = -1;
    if (nev.startsWith(q)) r = 0;
    else if (nev.includes(q)) r = 1;
    else if (c.utN.includes(q)) r = 2;
    if (r < 0) continue;
    talalat.push({ i, r: r + (lathato && !lathato[i] ? 3 : 0) });
  }
  talalat.sort((a, b) => a.r - b.r || g.nev[a.i].length - g.nev[b.i].length || g.fok[b.i] - g.fok[a.i] || a.i - b.i);
  return talalat.slice(0, korlat).map((t) => t.i);
}
