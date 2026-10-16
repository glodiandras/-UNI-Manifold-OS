// A vezérlő (C17) adattípusai: a core `/api/feladatok`, `/api/feladatok/{id}/valtozasok` és `/api/vezerlo/*` alakjai.

export type FeladatAllapot = 'sorban' | 'fut' | 'kesz' | 'hiba' | 'megallitva' | 'torolve' | 'megszakadt';

export const LEZART: ReadonlySet<FeladatAllapot> = new Set(['kesz', 'hiba', 'megallitva', 'torolve', 'megszakadt']);

export interface Feladat {
  id: string;
  tipus: string;
  cim: string;
  osszegzes: string;
  figyelmeztetes: string[];
  lepesek: { cim: string }[];
  kulturalt_stop: boolean;
  allapot: FeladatAllapot;
  letrehozva: string;
  indult: string | null;
  vegzett: string | null;
  /** 0–100 */
  szazalek: number;
  lepes_i: number;
  kilepes: number | null;
  hiba: string | null;
  /** A feladathiba nyelvfüggetlen kódja és paraméterei; a kész `hiba` szöveg a tartalék. */
  kod?: string;
  param?: Record<string, unknown>;
  leallitas_kerve: boolean;
  /** a feladat eredete: `2.0` (a Manifold saját sora) vagy más (egy korábbi importból: napló és változás-előzmény nincs vagy máshol van) */
  forras: string;
  vault_ir: boolean;
  modell: boolean;
  /** a gép magától indította (`TaskType.automatikus`); hiányzik: kézi (régi core) */
  automatikus?: boolean;
}

export interface FeladatReszlet extends Feladat {
  sorok: string[];
  tol: number;
  osszes_sor: number;
}

export interface ValtozasFajl {
  ut: string;
  /** A hozzáadva, M módosítva, D törölve */
  allapot: 'A' | 'M' | 'D';
  /** `null`: bináris */
  plusz: number | null;
  minusz: number | null;
}

export interface ValtozasCommit {
  sha: string;
  datum: string;
  targy: string;
  tetel: string | null;
  fajlok: ValtozasFajl[];
}

export interface ValtozasKor {
  kor: string;
  visszavonva: boolean;
  visszavonhato: boolean;
  commitok: ValtozasCommit[];
}

export interface Valtozasok {
  feladat: string;
  korok: ValtozasKor[];
  nincs_tar: boolean;
  /** A feladatnak a plafonnál több gépi commitja van: a lista csonka (a legfrissebbek látszanak; 2. audit T144). */
  levagva?: boolean;
}

export interface Kapcsolok {
  asszisztens: boolean;
  tracker: boolean;
}

export interface Rendszer {
  memoria: { szabad_szazalek: number; osszes_gb: number; swap_mb: number; core_rss_mb: number | null };
  modellzar: { szabad: boolean; tartalom: string; pid: number | null; repo: string | null; ido: string | null; elavult: boolean };
  worker:
    | { fut: false }
    | {
        fut: true;
        pid: number | null;
        rss_mb: number | null;
        modell: string | null;
        repo: string | null;
        keret_gb: number | null;
        szunetek: number | null;
        aktivitas: string | null;
      };
  ssd: { elerheto: false; hiba?: string } | { elerheto: true; kotet: string; osszes_gb: number; szabad_gb: number };
  mentes: {
    utolso: string | null;
    friss: boolean;
    tarolok: Record<string, { fajl: string | null; ido: string | null; friss: boolean }>;
    mappa: string;
    /** az utolsó belső lemezes mentés hibája (`mentes-hiba.json`): `hibak` = {tároló/elem: üzenet}; `null`: nincs (C29.6) */
    hiba?: { ido: string | null; hibak: Record<string, string> } | null;
  };
  kapcsolok: Kapcsolok;
}

/** A Modellek szakasz adata (C19, `GET /api/vezerlo/modellek`): feladatonként a router-tábla és a router döntése. */
export interface RouterSor {
  modell: string;
  pontszam: number;
  datum: string;
  aranyhalmaz_verzio: string;
  kalibralt: boolean;
  ervenyes: boolean;
  /** az aranyhalmaz aktuális verzióján mért-e (a router csak ezt fogadja el) */
  aktualis: boolean;
  csucs_gb: number | null;
  keret: 'munka' | 'tavol' | '—' | '?';
  snapshot: string;
  megjegyzes: string;
}

export interface RouterDontes {
  modell: string | null;
  var_tavolra: boolean;
  indok: string;
}

export interface ModellFeladat {
  feladat: string;
  aktualis_verzio: string | null;
  router_feladat: boolean;
  sorok: RouterSor[];
  dontes: { munka: RouterDontes; tavol: RouterDontes };
}

export interface ModellAttekintes {
  keretek: { munka: number; tavol: number };
  feladatok: ModellFeladat[];
}
