// A kvíz végpontjainak alakjai (C22a; ARCHITECTURE: „A közös forráshűség-kapu és a kvíz”).

export type KvizMod = 'teljes' | 'hibasak';
export type Kategoria = 'tudja' | 'szerencses' | 'tevkepzet' | 'hiany';

export interface KvizKerdes {
  id: string;
  kerdes: string;
  valaszok: string[];
  szakasz: string | null;
  jelolt: boolean;
}

export interface KvizTartalom {
  azon: string;
  cim: string;
  /** a forrásjegyzet vault-relatív útja `.md` nélkül (a link célja) */
  forras: string;
  modell: string;
  keszult: string;
  kerdesek: KvizKerdes[];
}

export interface Elozmeny {
  mikor: string;
  mod: KvizMod;
  pont: number;
  osszes: number;
  szazalek: number;
}

export interface KvizValasz {
  ok: boolean;
  ut: string;
  forras_ut: string;
  /** a kitöltés tokenje: a válaszok ebben rögzülnek, a pontszámot a core ezekből számolja */
  token: string;
  kviz: KvizTartalom;
  hibak: { sor: number; fajta: string; szoveg: string; kerdes: string | null }[];
  ujra: string[];
  megvaltozott: boolean;
  elozmenyek: Elozmeny[];
}

export interface Megoldas {
  ok: boolean;
  kerdes: string;
  helyes: boolean;
  helyes_index: number;
  helyes_valasz: string;
  magyarazat: string;
  idezet: string;
  szakasz: string | null;
  horgony: string | null;
  jegyzet: string;
  forras_ut: string;
}

export interface Eredmeny {
  kerdes: string;
  sorszam: number;
  valasz: number | null;
  helyes: boolean;
  tipp: boolean;
  kategoria: Kategoria;
  jelolt: boolean;
  tartos: boolean;
  szakasz: string | null;
}

export interface Javaslat {
  szakasz: string;
  horgony: string | null;
  jegyzet: string;
  prioritas: 1 | 2 | 3;
  cimke: string;
  teendok: string[];
  kerdesek: number[];
  tevkepzetek: { sorszam: number; kerdes: string; hitted: string; helyes: string; idezet: string }[];
  idezetek: string[];
}

export interface SzakaszAllapot {
  szakasz: string;
  horgony: string | null;
  osszes: number;
  helyes: number;
  allapot: 'rendben' | 'ingatag' | 'hianyos';
}

export interface Ertekeles {
  mod: KvizMod;
  eredmenyek: Eredmeny[];
  osszegzes: {
    pont: number;
    osszes: number;
    szazalek: number;
    matrix: Record<Kategoria, number>;
    atnezni: { szakasz: string; horgony: string | null; kerdesek: number[] }[];
    jelolt: number[];
  };
  szakaszok: SzakaszAllapot[];
  javaslatok: Javaslat[];
  fo_uzenet: string;
  onismeret: { biztos: number; biztos_helyes: number; tipp: number; tipp_helyes: number };
  trend: { elozo_szazalek: number | null; javult: number; romlott: number; tartos: number } | null;
  fedetlen_szakaszok: string[];
  ujra: string[];
  ido_ms: number | null;
}

export interface KitoltesValasz {
  ok: boolean;
  uj: boolean;
  ertekeles: Ertekeles;
  /** a következő kitöltés (újrapróba, hibás kérdések köre) tokenje */
  token: string;
  tracker: { ut: string; adat: Record<string, unknown> };
}

export interface KitoltesValaszEgy {
  kerdes: string;
  /** a válasz sorszáma a kvízjegyzetben álló sorrendben; null: „nem tudom” */
  valasz: number | null;
  tipp: boolean;
  ms: number;
}
