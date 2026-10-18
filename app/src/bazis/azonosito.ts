// A Bases-tulajdonság azonosítója (`file.name`, `note.x`, `formula.y`, bare `x`): a core `modell.tulajdonsag_id` tükre.

export type Ter = 'file' | 'note' | 'formula';

export function tulajdonsagId(s: string): { ter: Ter; nev: string } {
  const i = s.indexOf('.');
  if (i > 0) {
    const ter = s.slice(0, i);
    if (ter === 'file' || ter === 'note' || ter === 'formula') return { ter, nev: s.slice(i + 1) };
  }
  return { ter: 'note', nev: s };
}
