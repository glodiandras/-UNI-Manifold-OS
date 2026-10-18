// A gráf adatmodellje (C13): a core gráfja (`/api/vault/graf`), a fájltípusok (`/api/vault/fa`) és a jegyzetenkénti
// címke/tulajdonság (`/api/vault/graf-meta`) összefűzése csúcstáblává; szomszédsági tömbök, szűrés, helyi gráf (BFS),
// színcsoportok és keresés. Tiszta modul (DOM nélkül): a csúcs- és élhalmaz pontosan a core gráfja, a felület nem old
// fel linket és nem talál ki élt (ARCHITECTURE 2., L42).

import { egyszerusit, lekerdezesFordit, type Csucs } from './lekerdezes';

/** `cimke` és `feloldatlan`: virtuális csúcsok (nem fájlok) — a címke és a még nem létező link-cél (11-graph-02/03). */
export type FajlTipus = 'md' | 'canvas' | 'base' | 'pdf' | 'kep' | 'video' | 'hang' | 'felirat' | 'egyeb' | 'cimke' | 'feloldatlan';

/** A `GET /api/vault/graf` válasza. */
export interface GrafValasz {
  csucsok: string[];
  elek: [string, string][];
  feloldatlan?: Record<string, number>;
  tobbertelmu?: Record<string, number>;
  canvas_hiba?: [string, string][];
}

/** A `GET /api/vault/graf-meta` válasza. A `cimke_csucsok` és a `feloldatlan_elek` a core adata (a felület nem old fel linket és
 *  nem talál ki élt, L42); a régebbi válaszban hiányozhatnak. */
export interface GrafMeta {
  cimkek: Record<string, string[]>;
  tulajdonsagok: Record<string, Record<string, string[]>>;
  /** Kisbetűs címke → a csúcs neve (az első írásmód) és a jegyzetek száma. */
  cimke_csucsok?: Record<string, { nev: string; db: number }>;
  /** [forrás jegyzet, feloldatlan cél] párok, forrásonként egyszer. */
  feloldatlan_elek?: [string, string][];
  /** A core a feloldatlan élek korlátjánál megállt. */
  feloldatlan_csonkolt?: boolean;
}

export interface Szurok {
  lekerdezes: string;
  mellekletek: boolean;
  arvak: boolean;
  /** A címkék csúcsként (alap: nem). */
  cimkek?: boolean;
  /** Csak létező fájlok: a feloldatlan link-célok nem csúcsok (alap: igen — a Manifold eddigi nézete). */
  letezoCsak?: boolean;
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

/** A virtuális csúcsok felső korlátja (címke + feloldatlan cél): a nagy vault gráfja ettől nem nő korlátlanul; a túlfutás jelzett. */
export const MAX_VIRTUALIS = 20000;

/** A virtuális csúcsok „útja” egy vault-úton nem álló (NUL) előtagot kap, így nem ütközhet fájllal és nem nyitható meg. */
export const FELOLDATLAN_ELOTAG = '\u0000?';
export const CIMKE_ELOTAG = '\u0000#';

export function virtualisUt(ut: string): boolean {
  return ut.charCodeAt(0) === 0;
}

const NEM_MELLEKLET = new Set<FajlTipus>(['md', 'canvas', 'base', 'cimke', 'feloldatlan']);

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
  /** Az összes csúcs (a fájlok, utánuk a virtuális címke- és feloldatlan-csúcsok). */
  readonly n: number;
  /** A fájl-csúcsok száma: a `0 … nValos − 1` indexek fájlok, a többi virtuális. */
  readonly nValos: number;
  readonly ut: string[];
  readonly nev: string[];
  readonly tipus: FajlTipus[];
  readonly felsoMappa: string[];
  /** A lekérdezés-nyelv csúcsai (egyszerűsített szövegekkel). */
  readonly csucsok: Csucs[];
  /** A címkék eredeti írásmóddal (a tooltipnek). */
  readonly cimkek: string[][];
  /** A core gráfjának irányított élei [forrás, cél, …] (önhurokkal), csúcsindexekben — csak fájl-csúcsok között. */
  readonly iranyitott: Int32Array;
  /** Egyedi irányítatlan élek [a, b, …] (a < b, önhurok nélkül), a virtuális csúcsokhoz vezetőket is beleértve. */
  readonly elek: Int32Array;
  /** Élenként: 1 = a→b, 2 = b→a, 3 = mindkettő, 0 = nem irányított (címke-él). */
  readonly irany: Uint8Array;
  readonly onhurok: Uint8Array;
  /** A megjelenített fok: fájlnál a másik fájlhoz vezető élek száma (a virtuális élek nem számítanak, így az árva-fogalom és a
   *  méret nem változik), virtuális csúcsnál az összes éle. */
  readonly fok: Int32Array;
  /** CSR szomszédság: a `lista[kezd[i] … kezd[i + 1])` az i csúcs szomszédai (a virtuálisakat is beleértve). */
  readonly kezd: Int32Array;
  readonly lista: Int32Array;
  /** Hány élvégpont nem volt csúcs (a core gráfjában 0): jelzés a paritás-vizsgálatnak. */
  readonly hianyzoElek: number;
  /** A korlát miatt kimaradt virtuális csúcsok (vagy a core korlátja): a felület jelzi. */
  readonly csonkolt: boolean;
  readonly alairas: string;
  private readonly index: Map<string, number>;

  constructor(valasz: GrafValasz, tipusok: (ut: string) => FajlTipus | undefined, meta?: GrafMeta | null) {
    const valosUt = valasz.csucsok;
    const nV = valosUt.length;
    this.nValos = nV;
    this.index = new Map(valosUt.map((u, i) => [u, i]));

    // a virtuális csúcsok és élei (a core adata): címke → fájl, fájl → feloldatlan cél
    const ut: string[] = valosUt.slice();
    const nev: string[] = valosUt.map(nevUtbol);
    const tipus: FajlTipus[] = valosUt.map((u) => tipusok(u) ?? 'egyeb');
    const virtEl: number[] = []; // [fájl, virtuális, irány-bit, …]
    let csonkolt = meta?.feloldatlan_csonkolt === true;
    let virtDb = 0;
    const cimkeIdx = new Map<string, number>();
    if (meta?.cimke_csucsok) {
      for (const [kulcs, c] of Object.entries(meta.cimke_csucsok)) {
        if (virtDb >= MAX_VIRTUALIS) {
          csonkolt = true;
          break;
        }
        cimkeIdx.set(kulcs, ut.length);
        ut.push(CIMKE_ELOTAG + kulcs);
        nev.push('#' + c.nev);
        tipus.push('cimke');
        virtDb++;
      }
      if (cimkeIdx.size) {
        for (const [forras, lista] of Object.entries(meta.cimkek)) {
          const a = this.index.get(forras);
          if (a === undefined) continue;
          const latott = new Set<number>();
          for (const c of lista) {
            const v = cimkeIdx.get(c.replace(/^#/, '').toLowerCase());
            if (v !== undefined && !latott.has(v)) {
              latott.add(v);
              virtEl.push(a, v, 0);
            }
          }
        }
      }
    }
    if (meta?.feloldatlan_elek?.length) {
      const celIdx = new Map<string, number>();
      for (const [forras, cel] of meta.feloldatlan_elek) {
        const a = this.index.get(forras);
        if (a === undefined || !cel) continue;
        let v = celIdx.get(cel);
        if (v === undefined) {
          if (virtDb >= MAX_VIRTUALIS) {
            csonkolt = true;
            continue;
          }
          v = ut.length;
          celIdx.set(cel, v);
          ut.push(FELOLDATLAN_ELOTAG + cel);
          nev.push(nevUtbol(cel));
          tipus.push('feloldatlan');
          virtDb++;
        }
        virtEl.push(a, v, 1);
      }
    }
    const n = ut.length;
    this.n = n;
    this.ut = ut;
    this.nev = nev;
    this.tipus = tipus;
    this.csonkolt = csonkolt;
    this.felsoMappa = ut.map((u, i) => {
      if (i >= nV) return u.slice(0, 2); // a virtuális csúcsok saját körcikket kapnak a kezdőállásban (nem a gyökér jegyzetei közé)
      const k = u.indexOf('/');
      return k < 0 ? '' : u.slice(0, k);
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
    for (let e = 0; e < virtEl.length; e += 3) {
      const k = virtEl[e] * n + virtEl[e + 1]; // a fájl-csúcs indexe mindig kisebb a virtuálisénál
      par.set(k, (par.get(k) ?? 0) | virtEl[e + 2]);
    }
    const kulcsok = [...par.keys()].sort((x, y) => x - y);
    const m = kulcsok.length;
    this.elek = new Int32Array(2 * m);
    this.irany = new Uint8Array(m);
    this.fok = new Int32Array(n);
    const szomszedDb = new Int32Array(n);
    kulcsok.forEach((k, e) => {
      const a = Math.floor(k / n);
      const b = k - a * n;
      this.elek[2 * e] = a;
      this.elek[2 * e + 1] = b;
      this.irany[e] = par.get(k)!;
      szomszedDb[a]++;
      szomszedDb[b]++;
      if (b < nV) {
        this.fok[a]++;
        this.fok[b]++;
      } else this.fok[b]++; // fájl–virtuális él: csak a virtuális csúcs foka nő (a < nV)
    });
    this.kezd = new Int32Array(n + 1);
    for (let i = 0; i < n; i++) this.kezd[i + 1] = this.kezd[i] + szomszedDb[i];
    this.lista = new Int32Array(2 * m);
    const toltes = this.kezd.slice(0, n);
    for (let e = 0; e < m; e++) {
      const a = this.elek[2 * e];
      const b = this.elek[2 * e + 1];
      this.lista[toltes[a]++] = b;
      this.lista[toltes[b]++] = a;
    }

    this.cimkek = ut.map((u, i) => (i < nV ? (meta?.cimkek[u] ?? []) : []));
    this.csucsok = ut.map((u, i) => {
      if (i >= nV) {
        const egy = egyszerusit(nev[i]);
        return { ut: u, fajlnev: nev[i], utN: egy, fajlnevN: egy, cimkek: [], tulajdonsagok: undefined };
      }
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

  /** Az út csúcsindexe, vagy -1 (csak fájl-csúcsra; a virtuális csúcs nem vault-út). */
  csucsIndex(ut: string): number {
    return this.index.get(ut) ?? -1;
  }

  /** Virtuális (címke vagy feloldatlan cél) csúcs-e. */
  virtualis(i: number): boolean {
    return i >= this.nValos;
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
  const nV = g.nValos;
  const mutatCimke = sz.cimkek === true;
  const mutatFeloldatlan = sz.letezoCsak === false;
  const alap = new Uint8Array(g.n);
  // 1. fájl-csúcsok: melléklet- és szöveges szűrő (az árva-szűrő a virtuális szomszédok után jön)
  for (let i = 0; i < nV; i++) {
    if (!sz.mellekletek && g.melleklet(i)) continue;
    if (szurtLek && !lek.ures && !lek.illeszt(g.csucsok[i])) continue;
    alap[i] = 1;
  }
  // 2. virtuális csúcsok: a kapcsoló be van, és legalább egy szomszédos fájl-csúcs látszik (különben árva címke / szellem-cél)
  const virtuslatszik = new Uint8Array(g.n);
  for (let i = nV; i < g.n; i++) {
    const kapcsolo = g.tipus[i] === 'cimke' ? mutatCimke : mutatFeloldatlan;
    if (!kapcsolo) continue;
    for (let e = g.kezd[i]; e < g.kezd[i + 1]; e++)
      if (alap[g.lista[e]]) {
        alap[i] = 1;
        virtuslatszik[i] = 1;
        break;
      }
  }
  // 3. árva-szűrő: fájl, amelynek nincs fájl-szomszédja és nem látszik hozzá virtuális csúcs sem
  if (!sz.arvak)
    for (let i = 0; i < nV; i++) {
      if (!alap[i] || g.fok[i] !== 0) continue;
      let kapcsolt = false;
      for (let e = g.kezd[i]; e < g.kezd[i + 1] && !kapcsolt; e++) kapcsolt = virtuslatszik[g.lista[e]] === 1;
      if (!kapcsolt) alap[i] = 0;
    }
  // 4. a virtuális csúcs nem marad látható, ha az árva-szűrő eltüntette az összes fájl-szomszédját
  for (let i = nV; i < g.n; i++) {
    if (!alap[i]) continue;
    let van = false;
    for (let e = g.kezd[i]; e < g.kezd[i + 1] && !van; e++) van = alap[g.lista[e]] === 1;
    if (!van) alap[i] = 0;
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
  for (let i = 0; i < g.nValos; i++) {
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
    if (i >= g.nValos && lathato && !lathato[i]) continue; // a rejtett címke / feloldatlan cél nem „találat”: a kapcsolók nem oldódnak fel
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
