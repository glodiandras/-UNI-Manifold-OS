// A Bases List nézetének beállításai (10-bases-02): a jelölő (felsorolásjel / sorszám / nincs), a további tulajdonságok behúzása
// vagy sorközi elválasztóval. A kulcsnevek (`markers`, `indentProperties`, `separator`) feltételezés: az Obsidian oldalai nem
// mutatják őket (audit Q4); ismeretlen kulcs a `.base`-ben érintetlen marad (a core teljes körű ismeretlen-kulcs megőrzése).

export type ListaJel = 'bullet' | 'number' | 'none';

export interface ListaBeallitas {
  jel: ListaJel;
  /** igaz: a további tulajdonságok behúzott alpontok; hamis: egy sorban, az elválasztóval */
  behuzas: boolean;
  elvalaszto: string;
}

export const ALAP_ELVALASZTO = ', ';
export const MAX_ELVALASZTO = 12;

/** A `markers` kulcs értéke a három jelölő egyikére (a többes / egyes alak és a gyakori szinonimák is jók; ismeretlen: felsorolásjel). */
export function listaJel(ertek: unknown): ListaJel {
  const s = String(ertek ?? '').trim().toLowerCase();
  if (s === 'number' || s === 'numbers' || s === 'numbered' || s === 'ordered' || s === 'numeric') return 'number';
  if (s === 'none' || s === 'no' || s === 'false' || s === 'off') return 'none';
  return 'bullet';
}

export function listaBeallitas(beallitas: Record<string, unknown> | null | undefined): ListaBeallitas {
  const b = beallitas ?? {};
  const el = typeof b.separator === 'string' && b.separator.length <= MAX_ELVALASZTO ? b.separator : ALAP_ELVALASZTO;
  return { jel: listaJel(b.markers), behuzas: b.indentProperties === true, elvalaszto: el };
}
