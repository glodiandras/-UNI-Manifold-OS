// Az AI-funkciók közös hibaszerződése a felületen (core/modell/hibaszerzodes.py): a hibatörzs `ai` mezője
// `{kod, feladat, funkcio, param}`. Innen lesz érthető mondat és teendő („Install a model…”), a funkció saját `kod`-ja mellett.
import { t, tk } from '../i18n';
import { AI_KODOK, FELADAT_CIM } from './megjelenites';
import type { AiHibaAdat, AiKod } from './tipusok';

const MI: Record<AiKod, string> = {
  nincs_kalibralt: tk('Nincs kalibrált modell ehhez: {feladat}.'),
  nincs_telepitve: tk('Nincs telepített modell ehhez: {feladat}.'),
  csak_tavol: tk('A(z) {feladat} modellje csak távollétben fut.'),
  nincs_ai_runtime: tk('modellek.ai.mi.nincs_ai_runtime'),
  worker_hiba: tk('modellek.ai.mi.worker_hiba'),
};
const TEENDO: Record<AiKod, string> = {
  nincs_kalibralt: tk('modellek.ai.teendo.nincs_kalibralt'),
  nincs_telepitve: tk('modellek.ai.teendo.nincs_telepitve'),
  csak_tavol: tk('modellek.ai.teendo.csak_tavol'),
  nincs_ai_runtime: tk('modellek.ai.teendo.nincs_ai_runtime'),
  worker_hiba: tk('modellek.ai.teendo.worker_hiba'),
};

const objektum = (x: unknown): x is Record<string, unknown> => !!x && typeof x === 'object' && !Array.isArray(x);

/** A hibatörzsből (ApiHiba, `{ai}` törzs vagy maga az `ai` mező) az AI-hiba adata; `null`, ha nem AI-hiba. */
export function aiHibaAdat(x: unknown): AiHibaAdat | null {
  let ai: unknown = null;
  if (x instanceof Error) ai = (x as { adat?: Record<string, unknown> }).adat?.ai;
  else if (objektum(x) && objektum(x.ai)) ai = x.ai;
  else if (objektum(x) && typeof x.feladat === 'string') ai = x; // maga az `ai` mező (a hibatörzs `kod` mezője nem AI-kód)
  if (!objektum(ai) || typeof ai.kod !== 'string' || !(AI_KODOK as readonly string[]).includes(ai.kod)) return null;
  const param: AiHibaAdat['param'] = {};
  if (objektum(ai.param)) for (const [k, v] of Object.entries(ai.param)) if (v === null || ['string', 'number', 'boolean'].includes(typeof v)) param[k] = v as string | number | boolean | null;
  return { kod: ai.kod as AiKod, feladat: typeof ai.feladat === 'string' ? ai.feladat : '', funkcio: typeof ai.funkcio === 'string' ? ai.funkcio : null, param };
}

/** A feladat olvasható neve: a megadott címtábla, a mellékelt tábla, végül a nyers azonosító. */
export function feladatNev(feladat: string, cimek?: Record<string, string>): string {
  if (cimek?.[feladat]) return cimek[feladat];
  return FELADAT_CIM[feladat] ? t(FELADAT_CIM[feladat]) : feladat || t('modellek.ai.ez_a_feladat');
}

/** Két rész: mi történt, és mit tegyen a felhasználó (a „Model Manager” megnyitása a hívó gombja). */
export function aiHibaSzoveg(a: AiHibaAdat, cimek?: Record<string, string>): { mi: string; javitas: string } {
  const feladat = feladatNev(a.feladat, cimek);
  return { mi: t(MI[a.kod], { feladat }), javitas: t(TEENDO[a.kod], { feladat }) };
}

/** Egy mondatban (egysoros hibahelyekre, ahol nincs gomb): „mi történt. Mit tegyél.” */
export function aiHibaEgysor(a: AiHibaAdat, cimek?: Record<string, string>): string {
  const r = aiHibaSzoveg(a, cimek);
  return `${r.mi} ${r.javitas}`;
}

/** Az AI-hibához gomb is kell-e: a modellkezelő segít, ha hiányzik vagy nem kalibrált a modell, vagy a keret kevés. */
export const modellkezelovelJavithato = (a: AiHibaAdat): boolean => a.kod === 'nincs_kalibralt' || a.kod === 'nincs_telepitve' || a.kod === 'csak_tavol';
