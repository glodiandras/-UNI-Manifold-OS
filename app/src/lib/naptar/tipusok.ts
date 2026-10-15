// A naptár és az emlékeztetők (C29) API-alakjai: `GET /api/naptar/allapot`, `POST /api/naptar/szinkron`,
// a javaslat-, kategória- és ütközés-végpontok és a WS-események. A szerződés: docs/C29-TERV.md.

/** A macOS-engedély állapota (a héj-segéd `S` értékei). */
export type EngedelyAllapot = 'nincs_dontes' | 'korlatozott' | 'megtagadva' | 'engedelyezve' | 'csak_iras' | 'ismeretlen';

export interface NaptarValtozas {
  /** a változás ideje (csak az adatbázisból olvasott listában) */
  mikor?: string;
  azon: string;
  fajta: 'atnevezve' | 'eltunt' | 'visszajott' | 'osszekotve' | 'szin' | 'uj' | string;
  regi: string | null;
  uj: string | null;
}

export interface NaptarEredmeny {
  allapot: string;
  uj: number;
  valtozott: number;
  torolt: number;
  osszes: number;
  valtozasok: NaptarValtozas[];
  blokkok: number | null;
}

export interface EmlekeztetoKor {
  allapot: string;
  uj?: number;
  torolt?: number;
  kesz_emlekezteto?: number;
  kesz_jegyzet?: number;
  utkozes?: number;
  kesobb?: number;
  hibak?: string[];
  hiba?: string;
}

export interface UtolsoSzinkron {
  vege: string | null;
  allapot: string | null;
  utolso_sikeres: string | null;
  uzenet: string | null;
}

export type KategoriaForras = 'auto' | 'javaslat' | 'gazda';

export interface NaptarInfo {
  azon: string;
  nev: string;
  forras: string | null;
  szin: string | null;
  kategoria: string;
  kategoria_forras: KategoriaForras | string;
  eltunt: string | null;
}

export interface Kategoria {
  id: string;
  nev: string;
}

export type UtkozesFajta = 'kesz' | 'szerkesztve' | 'sor_nincs' | 'torles_visszatartva';

export interface Utkozes {
  id: number;
  mikor: string;
  kulcs: string;
  ut: string | null;
  szoveg: string | null;
  fajta: UtkozesFajta | string;
  reszlet: string | null;
  latva: string | null;
}

export interface EmlekeztetoAllapot {
  be: boolean;
  lista: string;
  tukor: { aktiv: number; kezi_torolt: number; torolve: number; [allapot: string]: number };
  utkozesek: Utkozes[];
  utolso: unknown;
}

export interface Javaslat {
  id: number;
  nap: string;
  kezd: string;
  veg: string;
  perc: number | null;
  cim: string;
  tantargy: string | null;
  tema: string | null;
  indok: string | null;
  allapot: string;
}

export interface NaptarAllapotValasz {
  /** `null`: a szolgáltatás még nem próbálta; `false`: nincs héj-segéd */
  seged: boolean | null;
  esemeny_engedely: EngedelyAllapot | null;
  emlekezteto_engedely: EngedelyAllapot | null;
  utolso: string | null;
  hiba: string | null;
  naptar: NaptarEredmeny | null;
  emlekezteto_kor: EmlekeztetoKor | null;
  utolso_szinkron: UtolsoSzinkron | null;
  naptarak: NaptarInfo[];
  valtozasok: NaptarValtozas[];
  kategoriak: Kategoria[];
  automatikus: boolean;
  emlekezteto_allapot: EmlekeztetoAllapot;
  javaslatok: Javaslat[];
}

/** A héj válasza (`window.manifold.naptarEngedely`). */
export interface NaptarEngedelyValasz {
  esemeny?: EngedelyAllapot | null;
  emlekezteto?: EngedelyAllapot | null;
  hiba?: string;
}
