// A mozgás JS-oldala: a Svelte-átmenetek ideje a tokenekből, prefers-reduced-motion esetén 0.

export const IDO = { gyors: 120, alap: 160, lassu: 200 } as const;

export function csokkentett(): boolean {
  return typeof matchMedia === 'function' && matchMedia('(prefers-reduced-motion: reduce)').matches;
}

export function ido(nev: keyof typeof IDO): number {
  return csokkentett() ? 0 : IDO[nev];
}

/** A tokens.css `--mozgas-gorbe` görbéje (cubic-bezier(0.2, 0, 0, 1)) Svelte-easingként. */
export function gorbe(t: number): number {
  // Newton-iteráció a cubic-bezier x(t)-jére
  const x1 = 0.2, y1 = 0, x2 = 0, y2 = 1;
  const bx = (s: number) => 3 * x1 * s * (1 - s) ** 2 + 3 * x2 * s * s * (1 - s) + s ** 3;
  const by = (s: number) => 3 * y1 * s * (1 - s) ** 2 + 3 * y2 * s * s * (1 - s) + s ** 3;
  let s = t;
  for (let i = 0; i < 8; i++) {
    const d = (bx(s + 1e-4) - bx(s - 1e-4)) / 2e-4;
    if (Math.abs(d) < 1e-6) break;
    s -= (bx(s) - t) / d;
    s = Math.min(1, Math.max(0, s));
  }
  return by(s);
}
