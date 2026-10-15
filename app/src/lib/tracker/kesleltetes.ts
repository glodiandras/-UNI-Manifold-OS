// A késleltetés fix vödrös hisztogramja (C27, használati mérés). A vödörhatárok egyeznek a core-éval
// (`core/tracker.py` `VEDROK_MS`): a core a napokat és a futásokat ezen a közös felosztáson vonja össze, ezért
// a p95 a vödör felső határa (a túlcsordulási vödörnél a megfigyelt maximum).

export const VEDROK_MS = [1, 2, 4, 8, 16, 32, 50, 75, 100, 150, 200, 300, 500, 1000, 2000, 5000] as const;
export const VEDOR_DB = VEDROK_MS.length + 1;

export function vedorIndex(ms: number): number {
  for (let i = 0; i < VEDROK_MS.length; i++) if (ms <= VEDROK_MS[i]) return i;
  return VEDROK_MS.length;
}

/** A küldött alak: vödör sorszáma → [darab, a vödör megfigyelt maximuma ms-ban]. */
export type VedrokKuldes = Record<string, [number, number]>;

export class Hisztogram {
  private db = new Array<number>(VEDOR_DB).fill(0);
  private max = new Array<number>(VEDOR_DB).fill(0);

  add(ms: number): void {
    if (!Number.isFinite(ms) || ms < 0) return;
    const i = vedorIndex(ms);
    this.db[i]++;
    if (ms > this.max[i]) this.max[i] = Math.round(ms * 100) / 100;
  }

  get ures(): boolean {
    return this.db.every((d) => d === 0);
  }

  /** A puffer kiürítése: a nem üres vödrök, vagy null. */
  kiurit(): VedrokKuldes | null {
    if (this.ures) return null;
    const ki: VedrokKuldes = {};
    for (let i = 0; i < VEDOR_DB; i++) if (this.db[i]) ki[String(i)] = [this.db[i], this.max[i]];
    this.db.fill(0);
    this.max.fill(0);
    return ki;
  }

  /** Egy sikertelen küldés visszatétele a pufferbe. */
  vissza(v: VedrokKuldes): void {
    for (const [k, [d, m]] of Object.entries(v)) {
      const i = Number(k);
      this.db[i] += d;
      if (m > this.max[i]) this.max[i] = m;
    }
  }
}
