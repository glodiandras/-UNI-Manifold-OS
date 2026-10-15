// Szövegek a dolgozat-oldalhoz (C28a): a számok mindig szövegben is megjelennek, a szín csak kiegészíti őket.

import type { KalibracioAllapot, KotesFok, OsszetevoNev, Szint } from './tipusok';

/** 0–1 → „62%”; `null` → „—”. */
export function szazalek(x: number | null | undefined): string {
  return x === null || x === undefined ? '—' : `${Math.round(x * 100)}%`;
}

export const SZINT_SZOVEG: Record<Szint, string> = {
  jo: 'jó',
  kozepes: 'közepes',
  gyenge: 'gyenge',
  nincs_adat: 'nincs adat',
};

export const KOTES_SZOVEG: Record<KotesFok, string> = {
  biztos: 'biztos kötés',
  valoszinu: 'valószínű kötés',
  athelyezve: 'áthelyezve?',
};

export const OSSZETEVO_SZOVEG: Record<OsszetevoNev, string> = {
  kartya: 'Kártya (átlagos felidézés)',
  kviz: 'Kvíz',
  frissesseg: 'Frissesség',
  ido: 'Tanult idő',
};

/** Egy tizedesjegyre kerekített szám magyar írásmóddal: „8,9”, „0,4”. */
export function tizedes(x: number): string {
  return (Math.round(x * 10) / 10).toLocaleString('hu-HU', { maximumFractionDigits: 1 });
}

/** A súly két tizedesig: „0,35”. */
export function suly(x: number): string {
  return x.toLocaleString('hu-HU', { maximumFractionDigits: 2 });
}

/** „45 perc”, „1 óra 15 perc”. */
export function percSzoveg(perc: number): string {
  const p = Math.round(perc);
  if (p < 60) return `${p} perc`;
  const o = Math.floor(p / 60);
  const m = p % 60;
  return m ? `${o} óra ${m} perc` : `${o} óra`;
}

/** Az utolsó tanulás szövege a mai naphoz képest: „ma”, „tegnap”, „3 napja”, vagy „nincs jel”. */
export function utolsoSzoveg(nap: string | null, maKulcs: string): string {
  if (!nap) return 'nincs jel';
  const [y1, m1, d1] = nap.split('-').map(Number);
  const [y2, m2, d2] = maKulcs.split('-').map(Number);
  const kulonbseg = Math.round((Date.UTC(y2, m2 - 1, d2) - Date.UTC(y1, m1 - 1, d1)) / 86_400_000);
  if (kulonbseg <= 0) return 'ma';
  return kulonbseg === 1 ? 'tegnap' : `${kulonbseg} napja`;
}

/** Egy összetevő nyers adatának rövid szövege a lefúráshoz (a core `adat` mezőiből). */
export function osszetevoAdat(nev: OsszetevoNev, adat: Record<string, unknown>): string {
  const szam = (k: string) => (typeof adat[k] === 'number' ? (adat[k] as number) : null);
  if (nev === 'kartya') {
    const db = szam('db') ?? 0;
    const uj = szam('uj') ?? 0;
    return db ? `${db} kártya${uj ? `, ebből ${uj} új` : ''}` : 'nincs kötött kártya';
  }
  if (nev === 'kviz') {
    const db = szam('db') ?? 0;
    return db ? `${db} eredmény, ${tizedes(szam('kerdes') ?? 0)} (időben csökkentett) kérdés` : 'nincs kvízeredmény';
  }
  if (nev === 'frissesseg') {
    const nap = szam('nap');
    return nap === null ? 'nincs tanulási jel' : `${Math.round(nap)} napja tanultál utoljára`;
  }
  const perc = szam('perc') ?? 0;
  return perc ? percSzoveg(perc) : 'nincs mért idő';
}

export const KALIBRACIO_SZOVEG: Record<KalibracioAllapot, string> = {
  nem_teljesitheto: 'nem teljesíthető',
  nincs_javulas: 'nincs javulás',
  javasolt: 'javítás javasolt',
};

/** Egy hiba (0–1 skálán) százalékpontban: „9,1 százalékpont”; `null` → „—”. */
export function szazalekpont(x: number | null | undefined): string {
  return x === null || x === undefined ? '—' : `${tizedes(x * 100)} százalékpont`;
}

/** „16 / 23 pont”; ha nincs pont (csak százalék), üres. */
export function pontSzoveg(pont: number | null, max: number | null): string {
  return pont === null || max === null ? '' : `${tizedes(pont)} / ${tizedes(max)} pont`;
}

/** C28c (K348): a kiértékelő szakaszának szabott eredmény-mezője (Dataview-stílusú inline mező; a felhasználó írja, gép soha). */
export const EREDMENY_MEZO_KULCS = 'Eredmény';
export const EREDMENY_MEZO_PELDA = 'Eredmény:: 16/23';
