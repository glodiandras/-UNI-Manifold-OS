// A dolgozat-oldal API-alakjai (C28a): `GET /api/felkeszultseg` és `GET /api/felkeszultseg/dolgozat`.
// A szám a core-ban számolódik (átlátható képlet, `core/felkeszultseg/keplet.py`); a felület csak megjelenít.

export type Szint = 'jo' | 'kozepes' | 'gyenge' | 'nincs_adat';
export type KotesFok = 'biztos' | 'valoszinu' | 'athelyezve';
export type OsszetevoNev = 'kartya' | 'kviz' | 'frissesseg' | 'ido';

export interface Kotes {
  fok: KotesFok;
  ok: string;
}

export interface Lefedettseg {
  van: number;
  osszes: number;
}

/** A lista egy sora: a dolgozat összefoglalója (a `hiba` mezős sor egy dolgozat hibáját hordozza). */
export interface DolgozatSor {
  azon: string;
  cim: string;
  nap: string;
  ora?: string;
  napok: number;
  tantargy?: string | null;
  lezart: boolean;
  jegyzet?: string | null;
  kotes?: Kotes | null;
  szam?: number | null;
  kilatas?: number | null;
  szint?: Szint;
  lefedettseg?: Lefedettseg;
  gyenge_db?: number;
  nincs_adat_db?: number;
  esedekes_kartya?: number;
  uj_kartya?: number;
  temak_db?: number;
  hiba?: string;
}

export interface ForrasAllapot {
  van: boolean | null;
  ok?: string | null;
  db?: number;
  kotetlen?: number;
}

export interface Adatok {
  kartya: ForrasAllapot;
  kviz: ForrasAllapot;
  tracker: ForrasAllapot;
  /** C28b: a „Dolgozat kiértékelő” jegyzetekből kinyert eredmények forrása. */
  eredmeny?: ForrasAllapot;
}

export interface NaptarKor {
  utolso_szinkron: string | null;
  regi: boolean;
}

export interface ListaValasz {
  nap: string;
  dolgozatok: DolgozatSor[];
  naptar: NaptarKor | null;
  adatok: Partial<Adatok>;
  figyelmeztetesek: string[];
  hiba?: string;
}

export interface Osszetevo {
  nev: OsszetevoNev;
  ertek: number | null;
  bizalom: number;
  suly: number;
  adat: Record<string, unknown>;
}

export interface GyengeKartya {
  azon: string;
  kerdes: string;
  felidezes: number;
  tema?: string;
}

export interface Tema {
  ut: string;
  nev: string;
  szam: number | null;
  kilatas: number | null;
  bizonyitek: number;
  ok: string | null;
  szint: Szint;
  osszetevok: Osszetevo[];
  aliasok: string[];
  tanult_perc: number;
  utolso_tanulas: string | null;
  kartya: { db: number; uj: number; esedekes: number; gyenge: GyengeKartya[] };
  kviz: { db: number };
}

export interface Forras {
  ut: string;
  tipus: 'pdf' | 'kep' | 'media' | 'egyeb';
  oldalak: string | null;
}

export interface TervSzelet {
  tema_ut: string | null;
  tema: string;
  perc: number;
  ok: string;
}

export interface TervNap {
  nap: string;
  perc: number;
  kartya_esedekes: number;
  naptar: { kezd: string | null; veg: string | null; cim: string }[];
  javaslat: { id: number; allapot: string } | null;
  szeletek: TervSzelet[];
}

/** C28b: a lezárt dolgozat kinyert eredménye a kiértékelő jegyzetből (a vaultba nem írunk). */
export interface Eredmeny {
  pont: number | null;
  max: number | null;
  szazalek: number;
  forras: string;
  szakasz: string;
  jegyzet: string;
  /** C28c: honnan jött — a szabott `Eredmény::` mezőből vagy a szabad szövegből. */
  eredet?: EredmenyEredet;
}

/** C28c (K348): a kiértékelő szakaszának `Eredmény:: 16/23` mezője (`mezo`) vagy a szabad szöveg (`szoveg`). */
export type EredmenyEredet = 'mezo' | 'szoveg';

export interface EredmenyEllentmondas {
  ok: string;
  /** A hibás mező jelöltjének nincs százaléka (`null`). */
  jeloltek: { forras: string; szazalek: number | null }[];
  szakasz: string;
  jegyzet: string;
  eredet?: EredmenyEredet;
}

export interface Reszlet extends DolgozatSor {
  temak: Tema[];
  forrasok: Forras[];
  onmaga: boolean;
  gyenge_pontok: {
    temak: { ut: string; nev: string; szam: number }[];
    nincs_adat: { ut: string; nev: string }[];
    kartyak: GyengeKartya[];
  };
  terv: { uzenet: string | null; napok: TervNap[] };
  keplet: {
    suly: Record<OsszetevoNev, number>;
    min_bizonyitek: number;
    cel: number;
    gyenge: number;
    jo: number;
    kalibralt: boolean;
    leiras: string;
  };
  naptar: NaptarKor | null;
  adatok: Adatok;
  figyelmeztetesek: string[];
  eredmeny?: Eredmeny | null;
  eredmeny_ellentmondas?: EredmenyEllentmondas | null;
  /** A szöveges értékelés tényeinek ujjlenyomata: ha eltér az értékelés `kulcs`-ától, a számok azóta változtak. */
  ertekeles_kulcs?: string;
}

/** `POST /api/felkeszultseg/ertekeles` (C28b). */
export type ErtekelesAllapot = 'kesz' | 'kapu_bukott' | 'ures' | 'nincs_mert_adat';

export interface Ertekeles {
  ok: boolean;
  allapot: ErtekelesAllapot;
  szoveg: string | null;
  modell: string | null;
  proba: boolean;
  kalibralt: boolean;
  probalkozas: number;
  tiltott_szamok: string[];
  kulcs: string;
  uzenet?: string | null;
}

export type KalibracioAllapot = 'nem_teljesitheto' | 'nincs_javulas' | 'javasolt';

export interface HibaStat {
  n: number;
  rmse: number | null;
  mae: number | null;
  torzitas: number | null;
}

/** `GET /api/felkeszultseg/kalibracio` (C28b): az önkalibráció állapota és a mért becslési hiba. */
export interface Kalibracio {
  allapot: KalibracioAllapot;
  ok: string;
  pontok: number;
  kell: number;
  lezart?: number;
  eredmennyel?: number;
  kalibralt: boolean;
  elotte_nap: number;
  kis_minta?: boolean;
  kihagyott: { azon: string; cim: string; nap: string; ok: string }[];
  alap: HibaStat & { suly?: Record<string, number> };
  loo: HibaStat;
  illesztett?: { suly: Record<string, number>; rmse: number | null };
  javulas?: number | null;
  pontok_reszlet: { azon: string; cim: string; nap: string; eredmeny: number; becsles: number | null; hiba: number; loo_becsles: number | null }[];
}
