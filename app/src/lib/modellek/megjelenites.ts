// A Model Manager szövegtáblái és kis segédei. A szövegek `tk()`-val jelöltek (megjelenítéskor `t()` fordít), a modell- és
// feladatcímek a core manifesztjéből jönnek (angolul), nem innen.
import { locale, tk } from '../i18n';
import type { AiKod, Kalibracio, Modell, TelepitAllapot } from './tipusok';

export const ALLAPOT_CIM: Record<TelepitAllapot, string> = {
  nincs: tk('modellek.allapot.nincs'),
  reszleges: tk('modellek.allapot.reszleges'),
  ellenorizetlen: tk('modellek.allapot.ellenorizetlen'),
  kesz: tk('modellek.allapot.kesz'),
  elter_revizio: tk('modellek.allapot.elter_revizio'),
  konvertalasra_var: tk('modellek.allapot.konvertalasra_var'),
};

export const ALLAPOT_LEIRAS: Record<TelepitAllapot, string> = {
  nincs: tk('modellek.allapot.nincs_leiras'),
  reszleges: tk('modellek.allapot.reszleges_leiras'),
  ellenorizetlen: tk('modellek.allapot.ellenorizetlen_leiras'),
  kesz: tk('modellek.allapot.kesz_leiras'),
  elter_revizio: tk('modellek.allapot.elter_revizio_leiras'),
  konvertalasra_var: tk('modellek.allapot.konvertalasra_var_leiras'),
};

export const SZEREP_CIM: Record<string, string> = {
  szoveg: tk('modellek.szerep.szoveg'),
  kep: tk('modellek.szerep.kep'),
  hang: tk('modellek.szerep.hang'),
  beagyazas: tk('modellek.szerep.beagyazas'),
  rerank: tk('modellek.szerep.rerank'),
};

/** A manifeszt feladatainak címe (a hibaüzenetekhez, amikor a Model Manager listája még nincs betöltve). */
export const FELADAT_CIM: Record<string, string> = {
  ocr_kezi: tk('modellek.feladat.ocr_kezi'),
  ocr_keplet: tk('modellek.feladat.ocr_keplet'),
  atirat: tk('modellek.feladat.atirat'),
  szoveg: tk('modellek.feladat.szoveg'),
  kviz: tk('modellek.feladat.kviz'),
  matek: tk('modellek.feladat.matek'),
  matek_cas: tk('modellek.feladat.matek_cas'),
  matek_ellenorzo: tk('modellek.feladat.matek_ellenorzo'),
  beagyazas: tk('modellek.feladat.beagyazas'),
  rerank: tk('modellek.feladat.rerank'),
  osztalyozas: tk('modellek.feladat.osztalyozas'),
  fuzet_fejezet: tk('modellek.feladat.fuzet_fejezet'),
  fuzet_valaszto: tk('modellek.feladat.fuzet_valaszto'),
  kod: tk('modellek.feladat.kod'),
  grafikon: tk('modellek.feladat.grafikon'),
  tema: tk('modellek.feladat.tema'),
  kotes: tk('modellek.feladat.kotes'),
  kiegeszites: tk('modellek.feladat.kiegeszites'),
  kifejtes: tk('modellek.feladat.kifejtes'),
  osszefoglal_kijeloles: tk('modellek.feladat.osszefoglal_kijeloles'),
};

export const AI_KODOK: readonly AiKod[] = ['nincs_kalibralt', 'nincs_telepitve', 'csak_tavol', 'nincs_ai_runtime', 'worker_hiba'];

/** A letöltés (GB) szövege: a manifeszt `meret_gb` mezője (10^9 bájt). */
export function gbSzoveg(gb: number | null | undefined): string {
  if (gb === null || gb === undefined || !Number.isFinite(gb)) return '–';
  return `${gb < 10 ? gb.toFixed(2) : gb.toFixed(1)} GB`;
}

/** Egy nyelvkód olvasható neve az aktív nyelven (ismeretlen kód: nagybetűs kód). */
export function nyelvNev(kod: string): string {
  try {
    return new Intl.DisplayNames([locale()], { type: 'language' }).of(kod) ?? kod.toUpperCase();
  } catch {
    return kod.toUpperCase();
  }
}

/** A modell nyelvei: `["*"]` (vagy üres) = nincs megkötés. */
export const tobbnyelvu = (m: Pick<Modell, 'nyelvek'>): boolean => !m.nyelvek?.length || m.nyelvek.includes('*');

/** A modell egy feladatának jele: kalibrált, ha van érvényes, kalibrált sor; különben próba. */
export interface FeladatJel {
  feladat: string;
  jel: 'kalibralt' | 'proba';
  sor: Kalibracio | null;
}
export function feladatJelek(m: Modell): FeladatJel[] {
  return m.feladat.map((f) => {
    const sor = m.kalibracio.find((k) => k.feladat === f) ?? null;
    return { feladat: f, jel: sor?.kalibralt ? 'kalibralt' : 'proba', sor };
  });
}

/** Van-e a lemezen valami, amit a törlés felszabadít. */
export const lemezen = (m: Modell): boolean => m.allapot !== 'nincs' || m.lemez_bajt > 0;
/** Mérhető-e a modell (a mérés előfeltétele a core-ban: telepítve, nem átalakításra váró). */
export const merheto = (m: Modell): boolean => m.allapot === 'kesz' || m.allapot === 'ellenorizetlen';
/** A letöltés gomb lehetséges-e (nincs, részleges vagy eltérő revízió). */
export const letoltheto = (m: Modell): boolean => m.allapot === 'nincs' || m.allapot === 'reszleges' || m.allapot === 'elter_revizio';

/** A saját halmaz tételeinek mezői feladatonként (a core `SAJAT_FELADATOK` tükre): a varázsló ezt ellenőrzi a fájlon. */
export const HALMAZ_MEZOK: Record<string, readonly string[]> = {
  kiegeszites: ['elotte', 'utana', 'elfogadhato'],
  kifejtes: ['ut', 'kezd', 'veg', 'kulcs', 'tema'],
  osszefoglal_kijeloles: ['ut', 'kezd', 'veg', 'kulcs'],
};
