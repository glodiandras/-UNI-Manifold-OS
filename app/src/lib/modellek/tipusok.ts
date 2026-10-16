// A Model Manager adattípusai: a core `/api/modellek/*` válaszai (core/modell/api.py docstringje a szerződés).

export type TelepitAllapot = 'nincs' | 'reszleges' | 'ellenorizetlen' | 'kesz' | 'elter_revizio' | 'konvertalasra_var';

export interface Kalibracio {
  feladat: string;
  pontszam: number;
  kalibralt: boolean;
  aranyhalmaz_verzio: string;
  datum: string;
  /** `sajat`: a felhasználó saját halmazán mért; `szallitott`: a mellékelt halmazon */
  mero: 'sajat' | 'szallitott';
}

/** A modellhez tartozó futó háttérfeladat kivonata (a haladás a feladatsor WS-eseményein érkezik). */
export interface FeladatKivonat {
  feladat_id: string;
  allapot: string;
  szazalek: number | null;
  /** csak a mérésnél: melyik feladaton mér */
  feladat?: string;
}

export interface Modell {
  id: string;
  repo: string;
  revizio: string;
  licenc: string | null;
  /** `["*"]`: többnyelvű / nincs megkötés */
  nyelvek: string[];
  szerep: 'szoveg' | 'kep' | 'hang' | 'beagyazas' | 'rerank' | string;
  ajanlott: boolean;
  feladat: string[];
  meret_gb: number | null;
  csucs_gb: number | null;
  keret: 'munka' | 'tavol' | string | null;
  futtato: string | null;
  konvertalas: boolean;
  allapot: TelepitAllapot;
  lemez_bajt: number;
  ellenorizve: string | null;
  kalibracio: Kalibracio[];
  letoltes: FeladatKivonat | null;
  teszt: FeladatKivonat | null;
}

export interface FeladatLeiras {
  cim: string;
  leiras: string;
  /** `null`: a feladatnak nincs küszöbe, kalibrált jel nem adható */
  kuszob: number | null;
  min_tetel: number | null;
  funkciok: string[];
}

export interface Funkcio {
  cim: string;
  feladatok: string[];
}

export interface ModellLista {
  modellek: Modell[];
  feladatok: Record<string, FeladatLeiras>;
  funkciok: Record<string, Funkcio>;
  keretek: Record<string, number>;
}

export interface TorlesEredmeny {
  id: string;
  felszabadult_bajt: number;
  kalibracio_levett: string[];
}

export interface OkSor {
  kod: string;
  param?: Record<string, unknown>;
}

export interface TesztRiport {
  modell: string;
  feladat: string;
  halmaz: 'szallitott' | 'sajat';
  datum: string;
  allapot: 'kesz' | 'megallitva' | 'elofeltetel' | 'eloproba_bukott' | 'hiba' | string;
  /** `kalibralt`: a mérés átment a kapukon; `proba`: minden más */
  jel: 'kalibralt' | 'proba';
  okok: OkSor[];
  kuszob?: number | null;
  min_tetel?: number | null;
  rogzitve?: boolean;
  uzenet?: string;
  figyelmeztetes?: unknown;
  ertekeles?: {
    pontszam?: number | null;
    n?: number | null;
    tetelszam?: number | null;
    teljes?: boolean;
    ervenyes?: boolean;
    aranyhalmaz_verzio?: string | null;
    mero?: string | null;
    ervenyesseg?: Record<string, number | null> | null;
  } | null;
  eloproba?: TesztRiport['ertekeles'];
}

export interface SzallitottHalmaz {
  feladat: string;
  router_feladat: string;
  nyelv: string | null;
  licenc: string | null;
  verzio: string | null;
  allapot: 'jovahagyott' | 'vazlat' | 'hianyzik' | 'hibas' | string;
  tetelszam: number;
  min_tetel: number | null;
  kalibralhato: boolean;
}

export interface SajatOsszegzes {
  feladat: string;
  van: boolean;
  allapot: 'vazlat' | 'jovahagyott' | null;
  tetelszam: number;
  nyelv: string | null;
  min_tetel: number | null;
  valasztva: boolean;
  tetelek: { id: string; ut?: string }[];
}

export interface Halmazok {
  szallitott: SzallitottHalmaz[];
  sajat: Record<string, SajatOsszegzes>;
  tamogatott: string[];
}

/** Egy saját tétel (a fájlban): a mezők a feladattól függnek (lásd `HALMAZ_MEZOK`). */
export type SajatTetel = Record<string, unknown>;

/** A hibaszerződés `ai` mezője (core/modell/hibaszerzodes.py). */
export type AiKod = 'nincs_kalibralt' | 'nincs_telepitve' | 'csak_tavol' | 'nincs_ai_runtime' | 'worker_hiba';
export interface AiHibaAdat {
  kod: AiKod;
  feladat: string;
  funkcio: string | null;
  param: Record<string, string | number | boolean | null>;
}
