// Egy oldal összes videója (84. döntés, javasolt): a bejárás eredményének kezelése a Bevitel szakaszban. A felfedezést a core
// `video_bejaras` feladata végzi (robots.txt, késleltetés, a kezdő úton belül; letöltés nélkül), az eredmény a
// `GET /api/video/bejaras?url=` válasza; innen a felhasználó kiválasztja a letöltendőket, és a kiválasztott videók egy
// `video_letoltes` feladatba mennek (`bejaras: true`; a `max_db` fölött `megerosit: true` kell).

export interface BejarasTetel {
  oldal: string;
  cim: string;
  /** a beágyazott lejátszó videójának linkje (pl. YouTube), ez töltődik le */
  video: string;
  /** a stagingben már megvan: alapból nincs kijelölve (a letöltés is kihagyná) */
  megvan: boolean;
  /** honnan töltődik: a kiadó közvetlen fájlja (`kozvetlen`) vagy a beágyazott lejátszó (`beagyazott`; régi listában hiányzik) */
  forras?: 'kozvetlen' | 'beagyazott';
  /** a beágyazott lejátszó videója (közvetlen fájlnál a nem használt másik út) */
  beagyazott?: string | null;
  /** a közvetlen fájl minőség-jelölője (pl. `1080p`) és nyelve */
  minoseg?: string;
  nyelv?: string | null;
  /** a közvetlen fájl kiadói felirata (a staging átirata ebből készül) */
  felirat?: string | null;
  /** a diák PDF-je: csak metaadat, nem töltődik le */
  diak?: string | null;
}

/** A tétel forrásának rövid leírása a listában: „közvetlen fájl (1080p, en, felirattal)” | „beágyazott lejátszó”. */
export function forrasLeiras(t: BejarasTetel): string {
  if (t.forras !== 'kozvetlen') return 'beágyazott lejátszó';
  const reszek = [t.minoseg, t.nyelv].filter((x): x is string => !!x);
  reszek.push(t.felirat ? 'felirattal' : 'felirat nélkül');
  return `közvetlen fájl (${reszek.join(', ')})`;
}

export interface BejarasEredmeny {
  kesz: boolean;
  start?: string;
  ido?: string;
  oldalak?: number;
  megszakitva?: boolean;
  max_db?: number;
  tetelek?: BejarasTetel[];
}

/** A bejárásból egy feladatban legfeljebb ennyi videó (megerősítéssel; a core `[video] bejaras_plafon`-ja). */
export const BEJARAS_PLAFON = 200;

/** Az alapkijelölés: minden, ami még nincs meg. */
export function alapKijeloles(tetelek: readonly BejarasTetel[]): Set<string> {
  return new Set(tetelek.filter((t) => !t.megvan).map((t) => t.video));
}

export interface LetoltesTerv {
  urlek: string[];
  /** a `max_db` fölött a felhasználónak külön meg kell erősítenie a számot */
  megerositesKell: boolean;
  /** a plafon fölött nem indítható */
  tulSok: boolean;
}

/** A kiválasztott videók a felfedezés sorrendjében, ismétlés nélkül. */
export function letoltesTerv(tetelek: readonly BejarasTetel[], kijelolt: ReadonlySet<string>, maxDb: number): LetoltesTerv {
  const urlek: string[] = [];
  for (const t of tetelek) if (kijelolt.has(t.video) && !urlek.includes(t.video)) urlek.push(t.video);
  return { urlek, megerositesKell: urlek.length > maxDb, tulSok: urlek.length > BEJARAS_PLAFON };
}
