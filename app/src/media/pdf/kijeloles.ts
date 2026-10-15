// A PDF-szövegkijelölés átszámítása kiemeléssé (C16): a kijelölés téglalapjai a lap dobozához viszonyított
// törtekként (nagyítástól független), soronként összevonva; a szöveg egy bekezdésként (a core `normal_szoveg`-ével
// azonos szabály: sorvégi elválasztás összevonva, szóközök egyre). Tiszta függvények + a DOM-os belépési pont.

export type Teglalap = [number, number, number, number];

interface Doboz {
  left: number;
  top: number;
  width: number;
  height: number;
}

const KEREKIT = 1e4;
const k = (x: number) => Math.round(x * KEREKIT) / KEREKIT;

/** A kijelölt szöveg egy bekezdésként. */
export function normalSzoveg(s: string): string {
  return s
    .normalize('NFC')
    .replace(/­/g, '')
    .replace(/(\p{L}|\p{N})-[ \t]*\r?\n[ \t]*(\p{L}|\p{N})/gu, '$1$2')
    .replace(/[\x00-\x08\x0b-\x1f\x7f]/g, ' ')
    .split(/\s+/)
    .filter(Boolean)
    .join(' ');
}

/** Az egy sorba eső, egymást érő vagy fedő téglalapok összevonása (a szövegréteg betűnként/szavanként ad dobozt). */
export function osszevon(t: Teglalap[]): Teglalap[] {
  const rend = [...t].filter(([, , w, h]) => w > 0 && h > 0).sort((a, b) => a[1] - b[1] || a[0] - b[0]);
  const ki: Teglalap[] = [];
  for (const r of rend) {
    const u = ki.find((x) => {
      const kozepA = x[1] + x[3] / 2;
      const kozepB = r[1] + r[3] / 2;
      const egySor = Math.abs(kozepA - kozepB) < Math.min(x[3], r[3]) * 0.5;
      const res = Math.max(x[3], r[3]) * 0.6; // a szóköz miatti rés
      return egySor && r[0] <= x[0] + x[2] + res && x[0] <= r[0] + r[2] + res;
    });
    if (!u) {
      ki.push([...r]);
      continue;
    }
    const x0 = Math.min(u[0], r[0]);
    const y0 = Math.min(u[1], r[1]);
    const x1 = Math.max(u[0] + u[2], r[0] + r[2]);
    const y1 = Math.max(u[1] + u[3], r[1] + r[3]);
    u.splice(0, 4, x0, y0, x1 - x0, y1 - y0);
  }
  return ki.sort((a, b) => a[1] - b[1] || a[0] - b[0]);
}

/** A képernyő-téglalapok a lap dobozához viszonyított, 0–1 közé vágott törtekként; a lapon kívüli és a
 *  1 px-nél kisebb dobozok kimaradnak. */
export function laphozViszonyit(rects: Doboz[], lap: Doboz): Teglalap[] {
  if (lap.width <= 0 || lap.height <= 0) return [];
  const ki: Teglalap[] = [];
  for (const r of rects) {
    if (r.width < 1 || r.height < 1) continue;
    const x0 = Math.max(0, (r.left - lap.left) / lap.width);
    const y0 = Math.max(0, (r.top - lap.top) / lap.height);
    const x1 = Math.min(1, (r.left + r.width - lap.left) / lap.width);
    const y1 = Math.min(1, (r.top + r.height - lap.top) / lap.height);
    if (x1 <= x0 || y1 <= y0) continue;
    ki.push([x0, y0, x1 - x0, y1 - y0]);
  }
  return osszevon(ki).map(([x, y, w, h]) => [k(x), k(y), k(w), k(h)]);
}

export interface Kijeloles {
  oldal: number;
  szoveg: string;
  teglalapok: Teglalap[];
  /** a kijelölés alja a nézetben (a lebegő gomb helye) */
  hely: { x: number; y: number };
}

/** A kijelölés a nézet egy lapján, vagy `null` (üres, a nézeten kívüli, vagy több lapra nyúló). A `tobbLap` igaz,
 *  ha a kijelölés több lapra nyúlik (a hívó szól). */
export function kijelolesOlvas(nezet: HTMLElement, sel: Selection | null): { k: Kijeloles | null; tobbLap: boolean } {
  if (!sel || sel.isCollapsed || sel.rangeCount === 0) return { k: null, tobbLap: false };
  const r = sel.getRangeAt(0);
  if (!nezet.contains(r.commonAncestorContainer)) return { k: null, tobbLap: false };
  const lapja = (n: Node | null) => (n instanceof Element ? n : n?.parentElement)?.closest<HTMLElement>('.page[data-page-number]') ?? null;
  const a = lapja(r.startContainer);
  const b = lapja(r.endContainer);
  if (!a || !b) return { k: null, tobbLap: false };
  if (a !== b) return { k: null, tobbLap: true };
  const szoveg = normalSzoveg(sel.toString());
  if (!szoveg) return { k: null, tobbLap: false };
  const lap = a.getBoundingClientRect();
  const teglalapok = laphozViszonyit([...r.getClientRects()], lap);
  if (!teglalapok.length) return { k: null, tobbLap: false };
  const also = r.getBoundingClientRect();
  return {
    k: { oldal: Number(a.dataset.pageNumber), szoveg, teglalapok, hely: { x: also.left + also.width / 2, y: also.bottom } },
    tobbLap: false,
  };
}
