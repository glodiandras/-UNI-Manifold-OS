// Fix sormagasságú ablakozás (C12): a kirajzolandó sorok tartománya a görgetésből. Tiszta függvény, a DOM-ot nem
// érinti, így a 2000 soros táblázat is csak a látható sorokat rajzolja (a `tulnyulas` sor fent és lent tartalék).

export interface Ablak {
  /** az első kirajzolt elem indexe (benne van) */
  elso: number;
  /** az utolsó kirajzolt elem indexe (nincs benne) */
  utolso: number;
  /** a kirajzolatlan elemek helye fent / lent, px-ben */
  fent: number;
  lent: number;
}

export function ablak(gorgetes: number, magassag: number, sorMagassag: number, db: number, tulnyulas = 8): Ablak {
  if (db <= 0 || sorMagassag <= 0) return { elso: 0, utolso: 0, fent: 0, lent: 0 };
  const g = Math.max(0, gorgetes);
  const elso = Math.min(db, Math.max(0, Math.floor(g / sorMagassag) - tulnyulas));
  const utolso = Math.min(db, Math.max(elso, Math.ceil((g + Math.max(0, magassag)) / sorMagassag) + tulnyulas));
  return { elso, utolso, fent: elso * sorMagassag, lent: (db - utolso) * sorMagassag };
}

/** A `rowHeight` nézet-beállítás px-ben (Obsidian: short, medium, tall, extra tall). */
export function sorMagassagPx(rowHeight: unknown): number {
  const k = String(rowHeight ?? 'short')
    .toLowerCase()
    .replace(/[\s_-]+/g, '');
  return { short: 30, medium: 44, tall: 62, extratall: 84 }[k] ?? 30;
}
