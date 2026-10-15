// Ékezetfüggetlen, elírástűrő név-keresés a gyorsváltónak és a parancspalettának (C07).
//
// Pontozás lekérdezés-szavanként, a legjobb illeszkedés számít:
//   szókezdet (100+) > részszöveg (70) > betűtűrő szókezdet: Damerau–Levenshtein ≤ 1 (4+ betű) / ≤ 2 (8+ betű)
//   (50 − 15·d) > részsorozat (20 + egymás utáni és szókezdő betűk) > találat csak az útban (25–30).
// Ha egy szó sehol nem illeszkedik, az elem kiesik. A kiemelés az eredeti név UTF-16-indexeiben jön vissza.

export interface Jelolt<T> {
  ertek: T;
  nev: string;
  /** Másodlagos szöveg (pl. a mappa-út), kisebb súllyal. */
  ut?: string;
}

export interface Talalat<T> {
  ertek: T;
  pont: number;
  /** [kezdet, vég) tartományok a `nev`-ben, rendezve, összevonva. */
  kiemeles: [number, number][];
}

interface Szo {
  kezd: number;
  szo: string;
}

interface Elokeszitett<T> {
  ertek: T;
  nev: string;
  norm: string;
  /** norm-index → [eredeti kezdet, eredeti vég) */
  kezdet: number[];
  veg: number[];
  szavak: Szo[];
  normUt: string;
  utSzavak: string[];
}

const KOMBINALO = /[̀-ͯ]/g;
const SZOKARAKTER = /[\p{L}\p{N}]/u;

/** Kisbetűs, ékezet nélküli alak (NFD + a kombináló jelek nélkül): „Mértani Ősz” → „mertani osz”. */
export function normalizal(s: string): string {
  return s.normalize('NFD').replace(KOMBINALO, '').toLowerCase();
}

function normalizalTerkeppel(s: string): { norm: string; kezdet: number[]; veg: number[] } {
  let norm = '';
  const kezdet: number[] = [];
  const veg: number[] = [];
  let i = 0;
  for (const c of s) {
    const n = normalizal(c);
    for (let j = 0; j < n.length; j++) {
      kezdet.push(i);
      veg.push(i + c.length);
    }
    norm += n;
    i += c.length;
  }
  return { norm, kezdet, veg };
}

function szavakra(norm: string): Szo[] {
  const ki: Szo[] = [];
  let kezd = -1;
  for (let i = 0; i <= norm.length; i++) {
    const szo = i < norm.length && SZOKARAKTER.test(norm[i]);
    if (szo && kezd < 0) kezd = i;
    if (!szo && kezd >= 0) {
      ki.push({ kezd, szo: norm.slice(kezd, i) });
      kezd = -1;
    }
  }
  return ki;
}

/** Damerau–Levenshtein (optimális illesztés) korláttal: ha biztosan > k, k+1-et ad. */
export function tavolsag(a: string, b: string, k: number): number {
  if (Math.abs(a.length - b.length) > k) return k + 1;
  const m = a.length;
  const n = b.length;
  let elozo2 = new Array<number>(n + 1).fill(0);
  let elozo = Array.from({ length: n + 1 }, (_, j) => j);
  for (let i = 1; i <= m; i++) {
    const sor = new Array<number>(n + 1);
    sor[0] = i;
    let sorMin = sor[0];
    for (let j = 1; j <= n; j++) {
      const ar = a[i - 1] === b[j - 1] ? 0 : 1;
      let v = Math.min(elozo[j] + 1, sor[j - 1] + 1, elozo[j - 1] + ar);
      if (i > 1 && j > 1 && a[i - 1] === b[j - 2] && a[i - 2] === b[j - 1]) v = Math.min(v, elozo2[j - 2] + 1);
      sor[j] = v;
      if (v < sorMin) sorMin = v;
    }
    if (sorMin > k) return k + 1;
    elozo2 = elozo;
    elozo = sor;
  }
  return elozo[n];
}

function turesHatar(hossz: number): number {
  return hossz >= 8 ? 2 : hossz >= 4 ? 1 : 0;
}

interface SzoTalalat {
  pont: number;
  tart: [number, number][]; // norm-indexek
  hely: number; // az első érintett norm-index (a sorrend-bónuszhoz)
}

function reszsorozat(norm: string, szavak: Szo[], t: string): SzoTalalat | null {
  const szokezdet = new Set(szavak.map((s) => s.kezd));
  const pozok: number[] = [];
  let i = 0;
  for (const c of t) {
    // először a következő szókezdő egyezést keressük, ha nincs, az első egyezést
    let talalt = -1;
    for (let j = i; j < norm.length; j++) {
      if (norm[j] === c) {
        if (szokezdet.has(j)) {
          talalt = j;
          break;
        }
        if (talalt < 0) talalt = j;
        if (pozok.length && j === pozok[pozok.length - 1] + 1) break; // a folytatás erősebb
      }
    }
    if (talalt < 0) return null;
    pozok.push(talalt);
    i = talalt + 1;
  }
  // Szétszórt egyezés nem találat: a futamok száma legfeljebb max(2, ⌈hossz/3⌉)
  // („mertanisor” → mértani + sor; a „mertani” viszont nem illeszkedik a „geometriai transzformációk”-ra).
  let futamok = 1;
  for (let j = 1; j < pozok.length; j++) if (pozok[j] !== pozok[j - 1] + 1) futamok++;
  if (futamok > Math.max(2, Math.ceil(t.length / 3))) return null;
  let pont = 20;
  const tart: [number, number][] = [];
  for (let j = 0; j < pozok.length; j++) {
    if (j > 0 && pozok[j] === pozok[j - 1] + 1) {
      pont += 3;
      tart[tart.length - 1][1] = pozok[j] + 1;
    } else {
      tart.push([pozok[j], pozok[j] + 1]);
    }
    if (szokezdet.has(pozok[j])) pont += 5;
  }
  pont -= Math.min(10, Math.floor((pozok[pozok.length - 1] - pozok[0] + 1 - t.length) / 3));
  return { pont, tart, hely: pozok[0] };
}

function szoIllesztes<T>(e: Elokeszitett<T>, t: string): SzoTalalat | null {
  // 1. szókezdet
  let legjobb: SzoTalalat | null = null;
  for (const [idx, w] of e.szavak.entries()) {
    if (w.szo.startsWith(t)) {
      const pont = 100 + (w.szo.length === t.length ? 15 : 0) + (idx === 0 ? 20 : 0);
      if (!legjobb || pont > legjobb.pont) legjobb = { pont, tart: [[w.kezd, w.kezd + t.length]], hely: w.kezd };
    }
  }
  if (legjobb) return legjobb;
  // 2. részszöveg
  const idx = e.norm.indexOf(t);
  if (idx >= 0) return { pont: 70, tart: [[idx, idx + t.length]], hely: idx };
  // 3. betűtűrő szókezdet
  const k = turesHatar(t.length);
  if (k > 0) {
    let tures: SzoTalalat | null = null;
    for (const [widx, w] of e.szavak.entries()) {
      for (let L = t.length - k; L <= t.length + k; L++) {
        if (L < 1 || L > w.szo.length) continue;
        const d = tavolsag(t, w.szo.slice(0, L), k);
        if (d <= k) {
          const pont = 50 - 15 * d + (widx === 0 ? 10 : 0);
          if (!tures || pont > tures.pont) tures = { pont, tart: [[w.kezd, w.kezd + L]], hely: w.kezd };
        }
      }
    }
    if (tures) return tures;
  }
  // 4. részsorozat
  if (t.length >= 2) {
    const r = reszsorozat(e.norm, e.szavak, t);
    if (r) return r;
  }
  // 5. csak az útban
  if (e.normUt) {
    if (e.utSzavak.some((w) => w.startsWith(t))) return { pont: 30, tart: [], hely: Infinity };
    if (e.normUt.includes(t)) return { pont: 25, tart: [], hely: Infinity };
  }
  return null;
}

function osszevon(tart: [number, number][]): [number, number][] {
  const r = [...tart].sort((a, b) => a[0] - b[0]);
  const ki: [number, number][] = [];
  for (const t of r) {
    const u = ki[ki.length - 1];
    if (u && t[0] <= u[1]) u[1] = Math.max(u[1], t[1]);
    else ki.push([t[0], t[1]]);
  }
  return ki;
}

const rendezo = new Intl.Collator('hu', { sensitivity: 'base', numeric: true });

export class FuzzyIndex<T> {
  private readonly elemek: Elokeszitett<T>[];

  constructor(jeloltek: Iterable<Jelolt<T>>) {
    this.elemek = [];
    for (const j of jeloltek) {
      const { norm, kezdet, veg } = normalizalTerkeppel(j.nev);
      const normUt = j.ut ? normalizal(j.ut) : '';
      this.elemek.push({
        ertek: j.ertek,
        nev: j.nev,
        norm,
        kezdet,
        veg,
        szavak: szavakra(norm),
        normUt,
        utSzavak: szavakra(normUt).map((s) => s.szo),
      });
    }
  }

  get meret(): number {
    return this.elemek.length;
  }

  /** Találatok csökkenő pont szerint. `bonusz`: pl. a legutóbbiaknak (0–40). Üres lekérdezésre üres lista. */
  keres(lekerdezes: string, opciok: { limit?: number; bonusz?: (ertek: T) => number } = {}): Talalat<T>[] {
    const q = normalizal(lekerdezes).trim();
    if (!q) return [];
    const szavak = q.split(/\s+/);
    const egyben = q.replace(/\s+/g, '');
    const ki: (Talalat<T> & { hossz: number; nev: string })[] = [];
    for (const e of this.elemek) {
      let pont = 0;
      const tart: [number, number][] = [];
      let elozoHely = -1;
      let sorrendben = true;
      let ok = true;
      for (const t of szavak) {
        const r = szoIllesztes(e, t);
        if (!r) {
          ok = false;
          break;
        }
        pont += r.pont;
        tart.push(...r.tart);
        if (r.hely < elozoHely) sorrendben = false;
        elozoHely = r.hely;
      }
      if (!ok) continue;
      if (szavak.length > 1 && sorrendben) pont += 10;
      if (e.norm.replace(/[^\p{L}\p{N}]/gu, '') === egyben) pont += 50;
      pont -= Math.min(20, e.norm.length / 4);
      if (opciok.bonusz) pont += opciok.bonusz(e.ertek);
      ki.push({
        ertek: e.ertek,
        pont,
        kiemeles: osszevon(tart).map(([a, b]) => [e.kezdet[a], e.veg[b - 1]] as [number, number]),
        hossz: e.norm.length,
        nev: e.nev,
      });
    }
    ki.sort((a, b) => b.pont - a.pont || a.hossz - b.hossz || rendezo.compare(a.nev, b.nev));
    const limit = opciok.limit ?? 50;
    return ki.slice(0, limit).map(({ ertek, pont, kiemeles }) => ({ ertek, pont, kiemeles }));
  }
}

/** A név darabjai kiemeléssel (a megjelenítéshez). */
export function darabol(nev: string, kiemeles: [number, number][]): { szoveg: string; kiemelt: boolean }[] {
  const ki: { szoveg: string; kiemelt: boolean }[] = [];
  let i = 0;
  for (const [a, b] of kiemeles) {
    if (a > i) ki.push({ szoveg: nev.slice(i, a), kiemelt: false });
    ki.push({ szoveg: nev.slice(a, b), kiemelt: true });
    i = b;
  }
  if (i < nev.length) ki.push({ szoveg: nev.slice(i), kiemelt: false });
  return ki;
}
