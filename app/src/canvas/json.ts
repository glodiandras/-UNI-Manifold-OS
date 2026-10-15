// Pozíció-tudatos JSON-elemző a canvashoz (C14). A bájthű foltozás alapja: minden érték, objektum-tag és
// tömbelem a szövegbeli helyével jön, így az író (`iro.ts`) csak a megváltozott részt cseréli, a többi
// karakter (behúzás, kulcssorrend, a nem érintett stringek escape-alakja, a záró sorvég) marad.
// A `core/index/linkek.canvas_stringek` szkennerének párja, a számokkal és a literálokkal kiegészítve.
// A helyek a JavaScript-szöveg UTF-16 indexei; a `veg` kizáró.

export interface JPrim {
  t: 'prim';
  kezd: number;
  veg: number;
  ertek: string | number | boolean | null;
}

export interface JTag {
  kulcs: string;
  /** a kulcs nyitó idézőjelének helye */
  kulcsKezd: number;
  /** a kulcs záró idézőjele utáni hely */
  kulcsVeg: number;
  ertek: JErtek;
}

export interface JObj {
  t: 'obj';
  kezd: number;
  veg: number;
  tagok: JTag[];
}

export interface JTomb {
  t: 'tomb';
  kezd: number;
  veg: number;
  elemek: JErtek[];
}

export type JErtek = JPrim | JObj | JTomb;

export class JsonHiba extends Error {
  constructor(
    readonly hely: number,
    readonly sor: number,
    readonly oszlop: number,
    uzenet: string,
  ) {
    super(`${uzenet} (${sor}. sor, ${oszlop}. oszlop)`);
  }
}

const SZAM = /-?(?:0|[1-9]\d*)(?:\.\d+)?(?:[eE][+-]?\d+)?/y;
const MAX_MELYSEG = 500;

/** A teljes szöveg elemzése (szigorú JSON, mint a `JSON.parse`; a vezető és záró szóköz megengedett). */
export function elemez(s: string): JErtek {
  let i = 0;
  let melyseg = 0;

  const hiba = (uzenet: string, hely = i): never => {
    const elotte = s.slice(0, hely);
    const sor = elotte.split('\n').length;
    const oszlop = hely - elotte.lastIndexOf('\n');
    throw new JsonHiba(hely, sor, oszlop, uzenet);
  };

  const ures = () => {
    while (i < s.length) {
      const c = s.charCodeAt(i);
      if (c === 32 || c === 9 || c === 10 || c === 13) i++;
      else break;
    }
  };

  const szoveg = (): string => {
    const k = i;
    i++;
    while (i < s.length) {
      const c = s.charCodeAt(i);
      if (c === 34) {
        i++;
        try {
          return JSON.parse(s.slice(k, i)) as string;
        } catch {
          return hiba('hibás escape a szövegben', k);
        }
      }
      if (c === 92) i += 2;
      else if (c < 0x20) return hiba('vezérlőkarakter a szövegben');
      else i++;
    }
    return hiba('lezáratlan szöveg', k);
  };

  const ertek = (): JErtek => {
    ures();
    if (i >= s.length) return hiba('váratlan vége a szövegnek');
    const c = s[i];
    if (c === '{') return obj();
    if (c === '[') return tomb();
    const k = i;
    if (c === '"') {
      const v = szoveg();
      return { t: 'prim', kezd: k, veg: i, ertek: v };
    }
    for (const [szo, v] of [['true', true], ['false', false], ['null', null]] as const) {
      if (s.startsWith(szo, i)) {
        i += szo.length;
        return { t: 'prim', kezd: k, veg: i, ertek: v };
      }
    }
    SZAM.lastIndex = i;
    const m = SZAM.exec(s);
    if (!m) return hiba(`váratlan karakter: ${JSON.stringify(c)}`);
    i += m[0].length;
    return { t: 'prim', kezd: k, veg: i, ertek: Number(m[0]) };
  };

  const melyebb = () => {
    if (++melyseg > MAX_MELYSEG) hiba('túl mély szerkezet');
  };

  const obj = (): JObj => {
    melyebb();
    const kezd = i++;
    const tagok: JTag[] = [];
    ures();
    if (s[i] === '}') {
      i++;
      melyseg--;
      return { t: 'obj', kezd, veg: i, tagok };
    }
    for (;;) {
      ures();
      if (s[i] !== '"') hiba('kulcs (idézőjeles szöveg) kellene');
      const kulcsKezd = i;
      const kulcs = szoveg();
      const kulcsVeg = i;
      ures();
      if (s[i] !== ':') hiba('kettőspont kellene');
      i++;
      tagok.push({ kulcs, kulcsKezd, kulcsVeg, ertek: ertek() });
      ures();
      if (s[i] === ',') {
        i++;
        continue;
      }
      if (s[i] === '}') {
        i++;
        melyseg--;
        return { t: 'obj', kezd, veg: i, tagok };
      }
      hiba('vessző vagy } kellene');
    }
  };

  const tomb = (): JTomb => {
    melyebb();
    const kezd = i++;
    const elemek: JErtek[] = [];
    ures();
    if (s[i] === ']') {
      i++;
      melyseg--;
      return { t: 'tomb', kezd, veg: i, elemek };
    }
    for (;;) {
      elemek.push(ertek());
      ures();
      if (s[i] === ',') {
        i++;
        continue;
      }
      if (s[i] === ']') {
        i++;
        melyseg--;
        return { t: 'tomb', kezd, veg: i, elemek };
      }
      hiba('vessző vagy ] kellene');
    }
  };

  const gyoker = ertek();
  ures();
  if (i < s.length) hiba('fölösleges szöveg a JSON után');
  return gyoker;
}

/** Az elemzett érték közönséges JavaScript-értékként (az ismétlődő kulcsnál az utolsó nyer, mint a `JSON.parse`-nál). */
export function ertekbol(j: JErtek): unknown {
  if (j.t === 'prim') return j.ertek;
  if (j.t === 'tomb') return j.elemek.map(ertekbol);
  const o: Record<string, unknown> = {};
  for (const t of j.tagok) o[t.kulcs] = ertekbol(t.ertek);
  return o;
}

/** Két JSON-érték mély egyenlősége (az objektum kulcssorrendje nem számít). */
export function egyenlo(a: unknown, b: unknown): boolean {
  if (a === b) return true;
  if (typeof a !== 'object' || typeof b !== 'object' || a === null || b === null) return false;
  if (Array.isArray(a) !== Array.isArray(b)) return false;
  if (Array.isArray(a)) {
    const bb = b as unknown[];
    return a.length === bb.length && a.every((x, k) => egyenlo(x, bb[k]));
  }
  const ao = a as Record<string, unknown>;
  const bo = b as Record<string, unknown>;
  const ak = Object.keys(ao);
  if (ak.length !== Object.keys(bo).length) return false;
  return ak.every((k) => Object.prototype.hasOwnProperty.call(bo, k) && egyenlo(ao[k], bo[k]));
}
