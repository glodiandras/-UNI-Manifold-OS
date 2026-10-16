import { MODULOK, type Beallitasok, type ModulId } from '../lib/beallitasok/tipusok';
import { tk } from '../lib/i18n';

export type Elmeny = Beallitasok['setup']['elmeny'];

export const ELMENYEK = [
  { id: 'diak', nev: tk('Diák|setup'), leiras: tk('Tanulás jegyzetekkel, kártyákkal, kvízekkel és matematikával.') },
  { id: 'tudasmunka', nev: tk('Tudásmunka|setup'), leiras: tk('Napi jegyzetek, összefoglalók, naptár és összekapcsolt tudás.') },
  { id: 'fejleszto', nev: tk('Fejlesztő|setup'), leiras: tk('Kód, vásznak és strukturált projektek a jegyzetek mellett.') },
  { id: 'kutato', nev: tk('Kutatás|setup'), leiras: tk('PDF-ek, források, matematika és összekapcsolt kutatási jegyzetek.') },
  { id: 'egyeni', nev: tk('Egyéni|setup'), leiras: tk('A jelenlegi modulok megtartása. Később mindegyik külön állítható.') },
] as const;

const ALAP: readonly ModulId[] = ['hivatkozasok', 'vazlat', 'tulajdonsagok', 'gyorsvalto', 'kereses', 'perjel', 'cimkek', 'sablonok', 'napi', 'canvas', 'bazis', 'graf', 'pdf', 'media'];
const EXTRA: Record<Exclude<Elmeny, 'egyeni'>, readonly ModulId[]> = {
  diak: ['kartya', 'kviz', 'osszefoglalas', 'matek', 'fuzet', 'video', 'kerdezz', 'asszisztens', 'naptar', 'felkeszultseg', 'tracker'],
  tudasmunka: ['osszefoglalas', 'kerdezz', 'asszisztens', 'naptar', 'tracker'],
  fejleszto: ['kod', 'osszefoglalas', 'kerdezz', 'asszisztens'],
  kutato: ['osszefoglalas', 'matek', 'kod', 'fuzet', 'video', 'kerdezz', 'asszisztens', 'naptar'],
};

/** A preset csak a felület moduljait állítja; fájlt és jegyzetet nem ír. Az egyéni visszaadja a megnyitáskori választást. */
export function elmenyModulok(id: Elmeny, eredeti: Record<ModulId, boolean>): Record<ModulId, boolean> {
  if (id === 'egyeni') return { ...eredeti };
  const bekapcsolt = new Set([...ALAP, ...EXTRA[id]]);
  return Object.fromEntries(MODULOK.map((modul) => [modul, bekapcsolt.has(modul)])) as Record<ModulId, boolean>;
}
