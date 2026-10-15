// A WCAG 2.x kontrasztarány és a tokens.css színpárjainak beolvasása (a teszt és a DESIGN.md táblája használja).

/**
 * `--név: light-dark(#világos, #sötét)` → { név: [világos, sötét] } (csak a hatjegyű hex párok); a `--név: var(--másik);`
 * álnév (pl. a canvas preset színei a callout-tokenekre, C37) a másik token értékét kapja.
 */
export function tokenSzinek(css: string): Record<string, [string, string]> {
  const ki: Record<string, [string, string]> = {};
  const re = /--([a-z0-9-]+):\s*light-dark\(\s*(#[0-9a-f]{6})\s*,\s*(#[0-9a-f]{6})\s*\)\s*;/gi;
  for (const m of css.matchAll(re)) ki[m[1]] = [m[2].toLowerCase(), m[3].toLowerCase()];
  for (const m of css.matchAll(/--([a-z0-9-]+):\s*var\(--([a-z0-9-]+)\)\s*;/gi)) {
    if (ki[m[2]]) ki[m[1]] = ki[m[2]];
  }
  return ki;
}

function csatorna(c: number): number {
  const s = c / 255;
  return s <= 0.04045 ? s / 12.92 : ((s + 0.055) / 1.055) ** 2.4;
}

export function relativFenyesseg(hex: string): number {
  const n = parseInt(hex.slice(1), 16);
  const r = (n >> 16) & 255;
  const g = (n >> 8) & 255;
  const b = n & 255;
  return 0.2126 * csatorna(r) + 0.7152 * csatorna(g) + 0.0722 * csatorna(b);
}

export function kontraszt(a: string, b: string): number {
  const la = relativFenyesseg(a);
  const lb = relativFenyesseg(b);
  return (Math.max(la, lb) + 0.05) / (Math.min(la, lb) + 0.05);
}
