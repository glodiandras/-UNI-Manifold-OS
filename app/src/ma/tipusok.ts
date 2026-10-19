// A „Ma” oldal és a napi jegyzet API-alakjai (C15): `GET /api/ma`, `POST /api/naplo/ma`, `/api/sablon/*`.
// A szakaszok egymástól függetlenek: egy elérhetetlen forrás csak a saját `hiba` mezőjét tölti.

import type { MaAsszisztens } from '../lib/asszisztens/tipusok';
import type { EngedelyAllapot, Javaslat } from '../lib/naptar/tipusok';

export type { Javaslat, MaAsszisztens };

export interface Hiba {
  hiba: string;
}

export interface NapiJegyzet {
  ut: string;
  letezik: boolean;
  kivonat: string;
}

export interface NaptarEsemeny {
  azon: string;
  cim: string;
  egesznap: boolean;
  /** az esemény kezdete és vége ISO-ban, a naptár saját időzónájával */
  kezd: string;
  veg: string;
  /** `HH:mm`; egész napos eseménynél üres */
  kezd_ora: string;
  veg_ora: string;
  hely: string;
  szin: string;
  kategoria: string;
  naptar: string;
}

export interface NaptarSzakasz {
  esemenyek: NaptarEsemeny[];
  /** a legacy utolsó naptár-importjának ideje (ISO), vagy null */
  utolso_szinkron: string | null;
  regi: boolean;
}

export interface Dolgozat {
  azon: string;
  cim: string;
  /** `ÉÉÉÉ-HH-NN` */
  nap: string;
  egesznap: boolean;
  ora: string;
  hely: string;
  szin: string;
  /** hány nap múlva (0 = ma) */
  napok: number;
  /** a kötött felkészülési jegyzet vault-relatív útja (L59), vagy null */
  jegyzet: string | null;
  kotes: 'biztos' | 'valoszinu' | 'athelyezve' | null;
}

export interface DolgozatSzakasz {
  lista: Dolgozat[];
  utolso_szinkron: string | null;
  regi: boolean;
}

export interface Feladat {
  ut: string;
  sor: number;
  szoveg: string;
  hatarido: string | null;
  utemezve: string | null;
}

export interface FeladatSzakasz {
  ma: Feladat[];
  lejart: Feladat[];
  osszes_ma: number;
  osszes_lejart: number;
}

export interface KartyaSzakasz {
  /** `kesz` (C23b): a kártyák összesítője; `nincs`: a régebbi core helyőrzője */
  allapot: 'nincs' | 'kesz';
  /** a most esedékes (nem új) kártyák */
  esedekes: number;
  /** a ma még elkezdhető új kártyák (a napi limitig) */
  uj?: number;
  /** a következő tanulási napon esedékessé válók */
  holnap?: number;
  osszes?: number;
}

/** A naptár-szinkron élő állapota (C29, `naptar_allapot`): segéd, engedély, utolsó kör, hiba. */
export interface NaptarAllapotSzakasz {
  /** `null`: a szolgáltatás még nem próbálta; `false`: nincs héj-segéd */
  seged: boolean | null;
  esemeny_engedely?: EngedelyAllapot | null;
  emlekezteto_engedely?: EngedelyAllapot | null;
  hiba?: string | null;
  utolso?: string | null;
  automatikus?: boolean;
}

/** A jóváhagyásra váró tanulásiblokk-javaslatok (C29; csak a hátralévők). */
export interface JavaslatSzakasz {
  lista: Javaslat[];
}

export interface MaValasz {
  datum: string;
  felirat: string;
  ma: boolean;
  napi: NapiJegyzet | Hiba;
  dolgozatok: DolgozatSzakasz | Hiba;
  naptar: NaptarSzakasz | Hiba;
  feladatok: FeladatSzakasz | Hiba;
  /** a C29 szakaszai; a régebbi core nem adja őket */
  naptar_allapot?: NaptarAllapotSzakasz | Hiba;
  javaslatok?: JavaslatSzakasz | Hiba;
  /** a C30a szakasza (az Asszisztens új higiénia-tételei); a régebbi core nem adja */
  asszisztens?: MaAsszisztens | Hiba;
  kartyak: KartyaSzakasz | Hiba;
}

export interface NaploValasz {
  ut: string;
  letrejott: boolean;
  /** a kurzor helye az új jegyzetben (UTF-16 egység); meglévő jegyzetnél null */
  kurzor: number | null;
  figyelmeztetes: string | null;
  /** A konfigurált sablon nem található; csak új napi jegyzet fallbackjénél. Régi core nem adja. */
  sablon_hiany?: string | null;
}

export interface SablonInfo {
  ut: string;
  nev: string;
}

export interface SablonLista {
  mappa: string;
  sablonok: SablonInfo[];
}

export interface SablonKimenet {
  szoveg: string;
  kurzor: number | null;
  /** a kiértékelt sablon frontmatterrel kezdődik */
  frontmatter: boolean;
}

export function hibas<T extends object>(szakasz: T | Hiba): szakasz is Hiba {
  return 'hiba' in szakasz;
}
