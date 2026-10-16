// Az importok adatszerződése (core/importalas.py docstringje): az Obsidian-előnézet, a v2-előnézet, a napló-állapot és a WS-esemény.

export type ImportFajta = 'obsidian' | 'v2';
export type ElonezetEredmeny = 'mehet' | 'figyelmeztet' | 'tilos' | 'kesz';
export type ImportAllapotKod = 'fut' | 'hiba' | 'megszakitva' | 'kesz' | 'visszaforditva' | 'reszben_visszaforditva';

export interface ImportOpciok {
  obsidian_mappa: boolean;
  kuka_mappa: boolean;
  nev: string;
}

export interface FajlSor { ut: string; fajta: string; meret: number; muvelet: 'masol' | 'megvan' | 'utkozes' }
export interface KihagyottSor { ut: string; ok: string }
export interface UtkozesSor { ut: string; masik?: string; ok: 'kis_nagy' | 'normalizalas' | 'cel_elter' | string }
export interface BeallitasSor { kulcs: string; ertek: unknown; forras: string; mod: 'ir' | 'azonos' | 'munkater' | 'kozvetlen' | string }
export interface NemAtvettSor { forras?: string; kulcs?: string; ok: string }
export interface PluginSor { id: string; be: boolean; allapot: 'tamogatott' | 'beepitett' | 'nem_tamogatott' | string; modul?: string | null }

export interface ObsidianElonezet {
  verzio: number;
  id: string;
  fajta: 'obsidian';
  forras: string;
  cel: string;
  eredmeny: ElonezetEredmeny;
  akadaly: string[];
  figyelmeztetes: string[];
  allapot: ImportAllapot | null;
  opciok: ImportOpciok;
  osszesites: {
    fajl_db: number; bajt: number; md_db: number; canvas_db: number; base_db: number; csatolmany_db: number;
    obsidian_db: number; egyeb_db: number; mappa_db: number; kihagyott_db: number; masolando_db: number; megvan_db: number;
  };
  fajlok: FajlSor[];
  fajlok_csonkitva: boolean;
  kihagyott: KihagyottSor[];
  utkozesek: UtkozesSor[];
  linkek: {
    wikilink_db: number; markdown_link_db: number; beagyazas_db: number; frontmatter_db: number;
    beallitas?: { wikilinkek?: boolean | null; link_formatum?: string | null };
  };
  obsidian: {
    beallitasok: BeallitasSor[];
    nem_atvett: NemAtvettSor[];
    mag_pluginok: PluginSor[];
    kozossegi_pluginok: PluginSor[];
    tipusok_db: number;
  };
  atiras: unknown[];
  letrehozando?: string[];
  szabad_bajt?: number | null;
  terv_hash: string | null;
}

export interface V2KulcsSor { kulcs: string; jelen: unknown; uj: unknown }
export interface V2UtkozesSor { kulcs: string; jelen?: unknown; v2?: unknown; ok?: string }
export interface V2Elonezet {
  verzio: number;
  id: string;
  fajta: 'v2';
  forras: string;
  eredmeny: ElonezetEredmeny;
  akadaly: string[];
  figyelmeztetes: string[];
  kulcsok: V2KulcsSor[];
  utkozesek: V2UtkozesSor[];
  nem_atvett: { kulcs: string; ok: string }[];
  nem_munkater_kulcs_db?: number;
  azonos_db?: number;
  sema: { cel: string; muvelet: 'ir' | 'azonos' | 'utkozes' | string } | null;
  valtozas_db: number;
  ujrainditas: boolean;
  terv_hash: string | null;
}

export interface ImportHibaAdat { kod?: string; uzenet?: string; param?: Record<string, unknown> }

export interface ObsidianEredmeny {
  id: string; allapot: string; cel?: string; munkater_id?: string; masolt_db?: number; megvolt_db?: number; bajt?: number;
  kihagyott_db?: number; beallitasok_irva?: string[]; forras_valtozott?: string[]; naplo?: string; ismetles?: boolean;
}
export interface V2Eredmeny {
  id: string; allapot: string; valtozas?: number; irt?: string[]; kulcsok?: string[]; ujrainditas?: boolean; ismetles?: boolean; naplo?: string;
}

export interface VisszaforditasEredmeny {
  id: string;
  allapot: 'visszaforditva' | 'reszben_visszaforditva' | string;
  kukaba?: string[];
  megtartva?: { ut: string; ok: 'modositott' | 'idegen' | string }[];
  visszaallitva?: string[];
  ismetles?: boolean;
  ujrainditas?: boolean;
}

export interface ImportAllapot {
  id: string;
  fajta: ImportFajta;
  allapot: ImportAllapotKod;
  /** A napló zárja foglalt: a futás ténylegesen él (különben a `fut` állapot megszakadt futás). */
  fut?: boolean;
  forras?: string;
  cel?: string;
  opciok?: Partial<ImportOpciok>;
  terv_hash?: string | null;
  kezdve?: string;
  frissitve?: string;
  hiba?: ImportHibaAdat | null;
  eredmeny?: (ObsidianEredmeny & V2Eredmeny) | null;
  visszaforditas?: VisszaforditasEredmeny | null;
}

export interface IndulasValasz { id: string; allapot: string; ismetles?: boolean }

/** A megszakítás válasza: `megszakitva` ha a szál a fájlhatáron megállt; `allapot: 'megszakitas'` (202) ha még az aktuális fájlt másolja. */
export interface MegszakitasValasz { id: string; allapot: string; megszakitva?: boolean }

/** A WS `import` esemény: haladás (`lepes`) vagy lezárás (`allapot`). */
export interface ImportEsemeny {
  tipus: 'import';
  id: string;
  fajta?: ImportFajta;
  lepes?: 'masolas' | 'munkater' | 'beallitasok' | string;
  kesz_db?: number;
  osszes_db?: number;
  bajt?: number;
  allapot?: string;
  eredmeny?: unknown;
  hiba?: ImportHibaAdat;
  visszaforditas?: VisszaforditasEredmeny;
}

export interface Halad { lepes: string; kesz_db: number; osszes_db: number; bajt: number }
