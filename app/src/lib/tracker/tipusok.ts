// A tracker (C27) adattípusai: a core `GET /api/tracker/statisztika` és `/hasznalat` alakjai.

export interface NapiSor {
  /** A nap (ÉÉÉÉ-HH-NN), heti bontásnál a hét hétfője. */
  nap: string;
  aktiv_mp: number;
  beszurt: number;
  torolt: number;
  kartya: number;
  kviz: number;
  integralt: number;
  /** A tervezett tanulási idő másodpercben (a naptár `tanulas` kategóriájú, legacy-importból származó eseményeiből). */
  terv_mp: number;
}

export interface Tantargy {
  tantargy: string;
  aktiv_mp: number;
  beszurt: number;
  torolt: number;
}

export interface Statisztika {
  tol: string;
  ig: string;
  bontas: 'nap' | 'het';
  kapcsolo: boolean;
  napok: NapiSor[];
  osszes: Omit<NapiSor, 'nap'>;
  tantargyak: Tantargy[];
  jegyzetek: { ut: string; tantargy: string; aktiv_mp: number }[];
  elerheto: { kartya: boolean; kviz: boolean; integralt: boolean; terv: boolean };
}

export interface KesleltetesOsszeg {
  db: number;
  p50_ms: number | null;
  p95_ms: number | null;
  max_ms: number | null;
  /** A vödrök darabszáma (a `vedrok_ms` felosztásán, az utolsó a túlcsordulás). */
  vedrok?: number[];
}

export interface Hasznalat {
  tol: string;
  ig: string;
  kapcsolo: boolean;
  parancsok: { parancs: string; db: number; forrasok: Record<string, number> }[];
  gepi: { funkcio: string; iras: number; visszavonas: number; elfogadas: number | null }[];
  kesleltetes: { gepeles: KesleltetesOsszeg; mentes: KesleltetesOsszeg };
  vedrok_ms: number[];
  szunetek: { memoria: { db: number; mp: number }; hutes: { db: number; mp: number } };
}

export interface ExportEredmeny {
  ut: string;
  tartalom: unknown;
}

/** A törlés hatóköre (`POST /api/tracker/torles {mit}`): a `tr_*`, a `has_*` vagy mindkettő. */
export type TorlesMit = 'tevekenyseg' | 'hasznalat' | 'minden';
