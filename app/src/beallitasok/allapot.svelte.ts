import { tk } from '../lib/i18n';
export const SZAKASZOK = [
  { id: 'altalanos', csoport: tk('beallitasok.options'), cim: tk('beallitasok.altalanos') },
  { id: 'szerkeszto', csoport: tk('beallitasok.options'), cim: tk('beallitasok.szerkeszto') },
  { id: 'fajlok', csoport: tk('beallitasok.options'), cim: tk('beallitasok.fajlok') },
  { id: 'megjelenes', csoport: tk('beallitasok.options'), cim: tk('beallitasok.megjelenes') },
  { id: 'billentyuk', csoport: tk('beallitasok.options'), cim: tk('beallitasok.billentyuk') },
  { id: 'modulok', csoport: tk('beallitasok.options'), cim: tk('beallitasok.modulok') },
  { id: 'modellek', csoport: tk('beallitasok.ai'), cim: tk('beallitasok.modellek') },
  { id: 'kalibracio', csoport: tk('beallitasok.ai'), cim: tk('beallitasok.kalibracio') },
  { id: 'memoria', csoport: tk('beallitasok.ai'), cim: tk('beallitasok.memoria') },
  { id: 'asszisztens', csoport: tk('beallitasok.ai'), cim: tk('beallitasok.asszisztens') },
  { id: 'teljesitmeny', csoport: tk('beallitasok.ai'), cim: tk('beallitasok.teljesitmeny') },
  { id: 'kartya', csoport: tk('beallitasok.learning'), cim: tk('beallitasok.kartya') },
  { id: 'kviz', csoport: tk('beallitasok.learning'), cim: tk('beallitasok.kviz') },
  { id: 'felkeszultseg', csoport: tk('beallitasok.learning'), cim: tk('beallitasok.felkeszultseg') },
  { id: 'pillanatkepek', csoport: tk('beallitasok.backup'), cim: tk('beallitasok.pillanatkepek') },
  { id: 'helyi_mentes', csoport: tk('beallitasok.backup'), cim: tk('beallitasok.helyi_mentes') },
  { id: 'kulso_mentes', csoport: tk('beallitasok.backup'), cim: tk('beallitasok.kulso_mentes') },
  { id: 'visszaallitas', csoport: tk('beallitasok.backup'), cim: tk('beallitasok.visszaallitas') },
  { id: 'halozat', csoport: tk('beallitasok.privacy'), cim: tk('beallitasok.halozat') },
  { id: 'telemetria', csoport: tk('beallitasok.privacy'), cim: tk('beallitasok.telemetria') },
  { id: 'adatok', csoport: tk('beallitasok.privacy'), cim: tk('beallitasok.adatok') },
  { id: 'integraciok', csoport: tk('beallitasok.privacy'), cim: tk('beallitasok.integraciok') },
  { id: 'engedelyek', csoport: tk('beallitasok.privacy'), cim: tk('beallitasok.engedelyek') },
  { id: 'nevjegy', csoport: tk('beallitasok.about'), cim: tk('beallitasok.nevjegy') },
  // Developer mód (F7): csak bekapcsolt módban látszik (nav, parancs, megnyitás)
  { id: 'fejleszto_naplok', csoport: tk('beallitasok.developer'), cim: tk('beallitasok.fejleszto_naplok') },
  { id: 'fejleszto_diagnosztika', csoport: tk('beallitasok.developer'), cim: tk('beallitasok.fejleszto_diagnosztika') },
  { id: 'fejleszto_homokozo', csoport: tk('beallitasok.developer'), cim: tk('beallitasok.fejleszto_homokozo') },
  { id: 'fejleszto_modell', csoport: tk('beallitasok.developer'), cim: tk('beallitasok.fejleszto_modell') },
  { id: 'fejleszto_teszt', csoport: tk('beallitasok.developer'), cim: tk('beallitasok.fejleszto_teszt') },
  { id: 'fejleszto_git', csoport: tk('beallitasok.developer'), cim: tk('beallitasok.fejleszto_git') },
  { id: 'fejleszto_import', csoport: tk('beallitasok.developer'), cim: tk('beallitasok.fejleszto_import') },
] as const;
export type SzakaszId = typeof SZAKASZOK[number]['id'];
/** A Developer-csoport szakaszai: Developer mód nélkül nem látszanak, nem nyithatók, parancsuk nem él. */
export const fejlesztoiSzakasz = (id: string): boolean => id.startsWith('fejleszto_');
export const szakaszLathato = (id: string, fejleszto: boolean): boolean => fejleszto || !fejlesztoiSzakasz(id);
export const beallitasAblak = $state({ nyitva: false, szakasz: 'altalanos' as SzakaszId });
export function beallitasMegnyit(szakasz: SzakaszId = 'altalanos'): void {
  beallitasAblak.szakasz = szakasz;
  beallitasAblak.nyitva = true;
}
