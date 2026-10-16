// A ```plot függvényeinek CAS-jellemzői (C35a): zérushely, szélsőérték, aszimptota a core `POST /api/grafikon/elemzes`
// végpontjából (a CAS-homokozóban számolva). A rajz ezek nélkül is él: a hiba csendesen jelölés nélkülit jelent.
// Kifejezésenkénti gyorsítótár (az ablakkal együtt), az egyidejű azonos kérés egyszer megy, a megszakítás csak a
// hívó várakozását szakítja meg (a lekérés a gyorsítótárba fut), a hibát rövid ideig nem próbálja újra.

import { locale } from '../../../lib/i18n';
import { kerdez as apiKerdez, type KeresOpciok } from '../../../lib/core/api';

export interface Pont {
  x: string;
  ertek: number;
}
export interface Szelsoertek {
  x: string;
  y: string;
  x_ertek: number;
  y_ertek: number;
  tipus: 'maximum' | 'minimum';
}
export interface Aszimptota {
  egyenlet: string;
  tipus: 'fuggoleges' | 'vizszintes';
  ertek: number;
}
export interface FerdeAszimptota {
  egyenlet: string;
  tipus: 'ferde';
  meredekseg: number;
  eltolas: number;
}
export interface Jellemzok {
  allapot: 'ok' | 'reszleges' | 'hiba' | 'homokozo_hiba';
  zerushelyek: Pont[];
  szelsoertekek: Szelsoertek[];
  aszimptotak: Aszimptota[];
  ferde_aszimptotak: FerdeAszimptota[];
  numerikus: boolean;
  figyelmeztetesek: string[];
}

type Kerdez = (ut: string, o?: KeresOpciok) => Promise<unknown>;
const HIBA_HUTES_MS = 15_000; // ennyi ideig nem próbálja újra a hibás lekérést

/** Az elemzési ablak: a látható ablak két oldalán egy-egy szélességgel nagyobb, szép (1/2/5·10ᵏ) lépcsőre kerekítve —
 *  így a kis mozgatás ugyanazt az ablakot adja (gyorsítótár), és a jelölések a mozgatás közben is megvannak. */
export function kiterjeszt(lo: number, hi: number): [number, number] {
  const w = hi - lo;
  const nyers = w / 4;
  const k = 10 ** Math.floor(Math.log10(nyers));
  const m = nyers / k;
  const lepes = (m >= 5 ? 5 : m >= 2 ? 2 : 1) * k;
  const tiszta = (v: number) => Number(v.toPrecision(12));
  return [tiszta(Math.floor((lo - w) / lepes) * lepes), tiszta(Math.ceil((hi + w) / lepes) * lepes)];
}

function megszakitott(): DOMException {
  return new DOMException('megszakítva', 'AbortError') // i18n-ignore: belső megszakítás-jel, nem látszik;
}

export class JellemzoKliens {
  private readonly cache = new Map<string, { ertek: Promise<Jellemzok | null>; hiba: number | null }>();

  constructor(
    private readonly kerdez: Kerdez = apiKerdez,
    private readonly ora: () => number = () => Date.now(),
  ) {}

  private kulcs(kif: string, ablak: [number, number]): string {
    return JSON.stringify([kif, ablak]);
  }

  /** A kifejezések jellemzői (a sorrendjükben); `null` az elem, ha nem elérhető; a teljes `null`: a lekérés hibás. */
  async kerd(kifejezesek: string[], ablak: [number, number], jel?: AbortSignal): Promise<(Jellemzok | null)[] | null> {
    if (jel?.aborted) throw megszakitott();
    const hianyzo: string[] = [];
    for (const kif of kifejezesek) {
      const kulcs = this.kulcs(kif, ablak);
      const e = this.cache.get(kulcs);
      if (e && (e.hiba === null || this.ora() - e.hiba < HIBA_HUTES_MS)) continue;
      if (!hianyzo.includes(kif)) hianyzo.push(kif);
    }
    if (hianyzo.length) this.lekeres(hianyzo, ablak);
    const varj = Promise.all(kifejezesek.map((kif) => this.cache.get(this.kulcs(kif, ablak))!.ertek));
    const eredmeny = jel
      ? Promise.race([
          varj,
          new Promise<never>((_, nem) => jel.addEventListener('abort', () => nem(megszakitott()), { once: true })),
        ])
      : varj;
    const v = await eredmeny;
    return v.every((e) => e === null) ? null : v;
  }

  private lekeres(kifejezesek: string[], ablak: [number, number]): void {
    const feloldo = new Map<string, (e: Jellemzok | null) => void>();
    for (const kif of kifejezesek) {
      const kulcs = this.kulcs(kif, ablak);
      const ertek = new Promise<Jellemzok | null>((f) => feloldo.set(kif, f));
      const rekord = { ertek, hiba: null as number | null };
      this.cache.set(kulcs, rekord);
    }
    const hibas = () => {
      for (const kif of kifejezesek) {
        const r = this.cache.get(this.kulcs(kif, ablak));
        if (r) r.hiba = this.ora();
        feloldo.get(kif)!(null);
      }
    };
    this.kerdez('/api/grafikon/elemzes', {
      metodus: 'POST',
      torzs: { fuggvenyek: kifejezesek, ablak },
      idokorlat: 45_000,
    }).then(
      (v) => {
        const f = (v as { fuggvenyek?: unknown } | null)?.fuggvenyek;
        if (!Array.isArray(f) || f.length !== kifejezesek.length || !f.every((e) => e && typeof e === 'object')) {
          hibas();
          return;
        }
        kifejezesek.forEach((kif, i) => feloldo.get(kif)!(f[i] as Jellemzok));
      },
      hibas,
    );
  }
}

// ------------------------------------------------------------------ olvasható szöveg

const SZAMFORMA = new Map<string, Intl.NumberFormat>();
function szamForma(): Intl.NumberFormat {
  const l = locale();
  let f = SZAMFORMA.get(l);
  if (!f) SZAMFORMA.set(l, (f = new Intl.NumberFormat(l, { maximumSignificantDigits: 4, useGrouping: false })));
  return f;
}

/** Egy szám olvasható szövege: a nyelv tizedesjele, legfeljebb 4 értékes jegy, valódi mínuszjel. */
export function szam(v: number): string {
  return szamForma().format(v).replace('-', '−');
}

/** A CAS pontos értékének (`3*pi/2`, `-sqrt(3)`, `y=sqrt(3)*x`) olvasható alakja. */
export function szepSzoveg(s: string): string {
  return s
    .replace(/\*\*/g, '^')
    .replace(/sqrt\(([A-Za-z0-9.]+)\)/g, '√$1')
    .replace(/sqrt\(([^()]+)\)/g, '√($1)')
    .replace(/\bpi\b/g, 'π')
    .replace(/(\d)\*(?=[π√])/g, '$1')
    .replace(/\*/g, '·')
    .replace(/-/g, '−');
}
