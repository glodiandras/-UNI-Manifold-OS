// A Bases core-válaszának típusai (`core/bazis/api.py`, C12). A felület a `.base` szövegét átlátszatlanul kezeli:
// a sorokat, oszlopokat, csoportokat és összesítőket a core számolja, a felület csak rajzol és (a C12b-ben) írat.

export type Ertek =
  | null
  | boolean
  | number
  | string
  | { t: 'szam'; v: string }
  | { t: 'lista'; e: Ertek[] }
  | { t: 'objektum'; e: Record<string, Ertek> }
  | { t: 'datum'; iso: string; ido: boolean }
  | { t: 'idotartam'; szoveg: string; ms: number }
  | { t: 'link'; cel: string; ut: string | null; nev: string; alcel?: string; kulso?: boolean }
  | { t: 'cimke'; v: string }
  | { t: 'regex'; v: string }
  | { t: 'kep'; ut?: string; url?: string; szin?: string }
  | { t: 'ikon'; nev: string }
  | { t: 'html'; v: string }
  | { t: 'hiba'; u: string };

export type NezetTipus = 'table' | 'cards' | 'list' | 'kanban';

export interface Oszlop {
  /** `file.name`, `note.Rating` → `Rating`, `formula.x` */
  id: string;
  nev: string;
  ter: 'note' | 'file' | 'formula';
  /** a tulajdonság típusa: text, number, date, datetime, checkbox, tags, multitext, aliases, formula */
  tipus: string;
  szerkesztheto: boolean;
  szelesseg: number | null;
  /** igaz, ha a név a core angol alapneve (nem a felhasználó `displayName`-je): a felület az azonosítóból fordít (10-bases-01) */
  alap_nev?: boolean;
}

export type Boritos = { t: 'ut'; ut: string } | { t: 'szin'; v: string } | { t: 'kulso'; url: string };

export interface Sor {
  ut: string;
  nev: string;
  /** jegyzet-e (csak ennek a tulajdonsága szerkeszthető) */
  md: boolean;
  cellak: Ertek[];
  kep?: Boritos;
}

export interface Osszesito {
  nev: string;
  ertek: Ertek;
}

export interface Csoport {
  kulcs: Ertek;
  cimke: string;
  /** az első sor indexe a `sorok`-ban */
  tol: number;
  db: number;
  osszesitok: Record<string, Osszesito>;
  /** a csoport tulajdonsága szerkeszthető (note), azaz a kártya áthúzható */
  huzhato: boolean;
}

export interface BazisHiba {
  hely: string;
  /** a core angol tartalék-mondata */
  uzenet: string;
  /** a hibakód és a skalár paraméterei: a felület ezen át fordít (`hibak.ts`) */
  kod?: string;
  param?: Record<string, string | number | boolean | null>;
  db?: number;
}

/** Az új jegyzet előtöltése a nézet szűrőiből (10-bases-07; `core/bazis/elotoltes.py`). */
export interface Elotoltes {
  /** a jegyzet mappája, ha a szűrők egyértelműen megadják */
  mappa: string | null;
  tulajdonsagok: Array<{ kulcs: string; ertek: string | number | boolean; tipus: string }>;
  cimkek: string[];
  /** a kulcsok, amelyekre a szűrők ellentmondó értéket követelnek (nem töltődnek elő) */
  nem_egyertelmu: string[];
}

/** Egy elrejtett csoport (a `groupOrder` nem sorolja fel): a sorai nem látszanak (10-bases-05). */
export interface RejtettCsoport {
  kulcs: Ertek;
  cimke: string;
  db: number;
}

/** A szerkesztő-segítség függvénylistájának egy eleme (10-bases-10; `fuggvenyek.fuggveny_lista`). */
export interface Fuggveny {
  nev: string;
  /** `global` vagy a metódus tulajdonosa (`string`, `list`, `date`, `file`…) */
  tipus: string;
  min: number | null;
  max: number | null;
}

export interface NezetLeiro {
  nev: string;
  tipus: NezetTipus;
  ismert: boolean;
}

export interface AktivNezet {
  index: number;
  nev: string;
  tipus: NezetTipus;
  eredeti_tipus: string;
  /** a nézet nyers YAML-kulcsai (rowHeight, cardSize, imageFit, sort, …) */
  beallitas: Record<string, unknown>;
}

/** A tulajdonság-választó egy eleme: minden elérhető oszlop (file.*, a vault tulajdonságai, a képletek). */
export interface Elerheto {
  id: string;
  nev: string;
  ter: 'note' | 'file' | 'formula';
  tipus: string;
}

/** A `.base` fájl szintű adatai (a szűrő- és képletmezőkhöz): a core a nyers YAML-ből adja. */
export interface FajlAdat {
  /** a globális szűrő szövegként (egyetlen kifejezés vagy and/or/not YAML) */
  szuro: string;
  szuro_nezet: string;
  kepletek: Record<string, string>;
  /** az egyedi összesítők nevei */
  osszesitok: string[];
  elerheto: Elerheto[];
  elotoltes?: Elotoltes;
}

export interface Valasz {
  ok: boolean;
  nezetek: NezetLeiro[];
  nezet: AktivNezet | null;
  oszlopok: Oszlop[];
  sorok: Sor[];
  csoportok: Csoport[] | null;
  /** a `groupOrder` által elrejtett csoportok (a sorai nincsenek a `sorok`-ban) */
  rejtett_csoportok?: RejtettCsoport[];
  osszesitok: Record<string, Osszesito>;
  /** hiányzik, ha a fájl nem értelmezhető (`ok: false`) */
  fajl?: FajlAdat;
  osszes: number;
  levagva: boolean;
  hibak: BazisHiba[];
  figyelmeztetesek: BazisHiba[];
  ido_ms: number;
  /** C33 (T179): a sorhalmaz (`Tabla`) frissítésének ideje — írás után a hideg eset; a `mod` ennek módja. */
  tabla_ms?: number;
  tabla_mod?: 'meleg' | 'inkrementalis' | 'teljes';
  generacio: number;
}

export interface LekerdezOpciok {
  /** a `this` fájlja: fülön a `.base` útja, blokkban/beágyazva a befoglaló jegyzeté */
  ez?: string | null;
  nezet?: number | string | null;
  max_sor?: number;
  /** a kérés sorszáma a nézeten belül, és a nézet azonosítója: az újabb kérés a core-ban leállítja a régebbit (T040) */
  kerdes?: number;
  azon?: string;
}

export type Muvelet =
  | { fajta: 'nezet_beallit'; nezet: number; kulcs: string; ertek: unknown; alkulcs?: string }
  | { fajta: 'nezet_uj'; tipus?: NezetTipus; nev?: string }
  | { fajta: 'nezet_torol'; nezet: number }
  | { fajta: 'nezet_mozgat'; nezet: number; ujindex: number }
  | { fajta: 'szuro_beallit'; hol: 'globalis' | number; yaml: string }
  | { fajta: 'keplet_beallit'; nev: string; kifejezes: string | null }
  | { fajta: 'megjelenites_beallit'; id: string; displayName: string | null }
  | { fajta: 'forras_csere'; szoveg: string };

export interface ModositValasz {
  ok: boolean;
  szoveg_uj: string;
  valtozas: string;
  hibak: BazisHiba[];
}
