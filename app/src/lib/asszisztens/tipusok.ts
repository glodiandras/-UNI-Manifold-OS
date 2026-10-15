// Az Asszisztens (C30a) API-alakjai: `GET /api/higienia?ut=`, `/api/asszisztens/*`, a „Ma” oldal `asszisztens` szakasza.

export type HigieniaFajta =
  | 'torott_link'
  | 'tobbertelmu_link'
  | 'arva_jegyzet'
  | 'hibas_keplet'
  | 'hibas_frontmatter'
  | 'sema_sertes'
  | 'hianyzo_forrashorgony'
  | 'hianyzo_media';

export type HigieniaSzint = 'hiba' | 'figyelmeztetes' | 'tajekoztato';

export interface HigieniaTetel {
  /** stabil, tartalmi kulcsból épülő azonosító (a sor eltolódására nem változik) */
  azonosito: string;
  fajta: HigieniaFajta;
  szint: HigieniaSzint;
  ut: string;
  /** 1-től; az árva jegyzetnek nincs sora */
  sor: number | null;
  uzenet: string;
}

/** `GET /api/higienia?ut=`: egy jegyzet tételei (egyetlen indexelt lekérdezés, frissen). */
export interface JegyzetHigienia {
  kesz: boolean;
  jegyzetek: number;
  tetelek: HigieniaTetel[];
}

/** `GET /api/asszisztens/higienia`: a háttérben számolt, gyorsítótárazott teljes riport összegzése. */
export interface HigieniaOsszegzes {
  kapcsolo: boolean;
  kesz: boolean;
  szamolva: string | null;
  szamol: boolean;
  /** a számítás aktív használat miatt vár */
  szunetel: boolean;
  hiba: string | null;
  /** az első riport csendes alapvonal: a meglévő tételek nem „újak” */
  alapvonal: boolean;
  osszesites: Record<string, number> | null;
  ossz: number;
  uj: number;
  uj_tetelek: HigieniaTetel[];
}

export interface SzokasJavaslat {
  azon: string;
  allapot: string;
  tantargy: string;
  tantargy_nev: string;
  nap_neve: string;
  hit: number;
  het: number;
  atlag_perc: number;
  /** a tantárgy legutóbbi jegyzete (a tracker aktív idejéből), vagy null */
  legutobbi_ut: string | null;
  /** C30b (K205 (a)): a szokásos napszak (reggel | délelőtt | délután | este | éjszaka), ha a `tr_aktiv_ora` elég adatot ad; különben null */
  napszak?: string | null;
  /** hány alkalommal volt ebben a napszakban (az ablak azonos hétköznapjai közül) */
  napszak_hit?: number | null;
  szoveg: string;
}

export type StatisztikaFajta = 'emlites' | 'szokas' | 'higienia';

export interface Kuszob {
  szint: 'alap' | 'szigoru' | 'nema';
  szorzo: number | null;
}

/** A küszöb a linkjavaslat szerkesztő-oldalán: a szint és a szorzó mellett a hasonlósági küszöb (C30b; `null`/hiányzó: nincs szűrés). */
export interface JavaslatKuszob extends Kuszob {
  hasonlosag?: number | null;
}

export interface StatisztikaSor {
  elfogad: number;
  elutasit: number;
  db: number;
  arany: number | null;
  kuszob: Kuszob;
  /** csak az `emlites` sorban (C30b): a jegyzet–cél hasonlóság alsó határa a szorzóval együtt; `null`: néma */
  hasonlosag_kuszob?: number | null;
}

export interface Statisztika {
  kapcsolo: { asszisztens: boolean; tracker: boolean };
  ablak_nap: number;
  fajtak: Record<StatisztikaFajta, StatisztikaSor>;
  osszes: { elfogad: number; elutasit: number };
}

/** A `GET /api/ma` `asszisztens` szakasza (csak olvas; a régebbi core nem adja). */
export interface MaAsszisztens {
  kapcsolo: boolean;
  higienia: { kesz: boolean; ossz: number; uj: number } | null;
}

/** A `POST /api/asszisztens/emlitesek` egy találata (C30a core API; a pozíciók Python-kódpont szerintiek, `veg` kizárólagos). */
export interface EmlitesTalalat {
  kezd: number;
  veg: number;
  sor: number;
  oszlop: number;
  szoveg: string;
  /** a cél jegyzet útja; `null`, ha több jegyzet viseli ezt a nevet */
  cel: string | null;
  tobbertelmu: boolean;
  jeloltek: string[];
  forras: string;
}

export interface EmlitesValasz {
  ut: string | null;
  emlitesek: EmlitesTalalat[];
  /** hamis, ha az Asszisztens-kapcsoló a core-ban ki van kapcsolva (ilyenkor nincs találat) */
  kapcsolo: boolean;
}

export type DontesFajta = 'emlites' | 'szokas' | 'higienia';

/** `POST /api/kereses/hasonlosag` (C25c): a jegyzet és a célok hasonlósága a vektortárból, modell nélkül. */
export interface HasonlosagValasz {
  ut: string;
  allapot: 'ok' | 'nincs_tar' | 'nincs_vektor' | 'nem_jegyzet';
  elavult: boolean;
  /** cél → koszinusz-hasonlóság, vagy `null` (a cél nincs az indexben / nincs vektora) */
  pontok: Record<string, number | null>;
}

// ---------------------------------------------------------------- J1–J3: tanuló mag és javaslat-kártya

export type TanultMuvelet = 'cimke' | 'sablon' | 'link';
export type KartyaTipus = 'szerkezet' | 'muvelet' | 'tartalom';
export type HangolasSzint = 'batrabb' | 'alap' | 'ritkabb' | 'nema';

/** A kártya elfogadásakor a szerkesztőn át végzett művelet (a core nem ír). */
export type KartyaMuvelet =
  | { fajta: 'szakasz'; szoveg: string }
  | { fajta: 'cimke'; ertek: string }
  | { fajta: 'link'; cel: string }
  | { fajta: 'sablon'; ut: string };

export interface KartyaJavaslat {
  azon: string;
  tipus: KartyaTipus;
  helyzet: string;
  /** „Mit szólnál…?” */
  cim: string;
  indok: string;
  allas: HangolasSzint;
  muvelet: KartyaMuvelet;
}

/** `POST /api/asszisztens/kartya`: a legjobb jelölt (vagy `null`) és a következő kártyáig várandó idő. */
export interface KartyaValasz {
  javaslat: KartyaJavaslat | null;
  varakozas_mp: number;
  kapcsolo: boolean;
}

export interface KartyaDontes {
  azon: string;
  tipus: KartyaTipus;
  helyzet: string;
  dontes: 'elfogad' | 'elutasit' | 'figyelmen_kivul';
  cim?: string;
}

export type TanultFajta = 'minta' | 'muvelet' | 'elutasitott' | 'hangolas' | 'mind';

/** `GET /api/asszisztens/tanult`: minden, amit az asszisztens helyben tanult (`{state}/asszisztens.json`). */
export interface TanultLista {
  kapcsolo: boolean;
  mintak: { elotte: string; szoveg: string }[];
  muveletek: { kulcs: string; muvelet: TanultMuvelet; muvelet_nev: string; mappa: string; ertek: string; db: number; tanult: boolean }[];
  elutasitott: { kulcs: string; tipus: string; cim: string }[];
  hangolas: { kulcs: string; tipus: string; tipus_nev: string; helyzet: string; elfogad: number; elutasit: number; szint: HangolasSzint }[];
}
