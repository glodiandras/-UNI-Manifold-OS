export const MODULOK = ['hivatkozasok', 'vazlat', 'tulajdonsagok', 'gyorsvalto', 'kereses', 'perjel', 'cimkek', 'sablonok', 'napi', 'canvas', 'bazis', 'graf', 'pdf', 'media', 'kartya', 'kviz', 'osszefoglalas', 'matek', 'kod', 'fuzet', 'video', 'kerdezz', 'asszisztens', 'naptar', 'felkeszultseg', 'tracker'] as const;
export type ModulId = typeof MODULOK[number];
export interface Beallitasok {
  altalanos: { nyelv: 'auto'|'hu'|'en'; inditas: 'utolso'|'valaszto' };
  szerkeszto: { mod: 'elo'|'forras'; olvashato_szelesseg: boolean; helyesiras: boolean; tab_meret: number; perjel: boolean };
  fajlok: { uj_mappa: string; csatolmany_mappa: string; sablon_mappa: string; napi_ut: string; link_formatum: 'rovid'|'relativ' };
  megjelenes: { tema: 'rendszer'|'vilagos'|'sotet'; betumeret: number; csend: boolean };
  modulok: Record<ModulId, boolean>;
  adatvedelem: { asszisztens: boolean; tracker: boolean; ertesitesek: boolean; naptar: boolean };
  billentyuk: Record<string,string>;
  setup: { kesz: boolean; elmeny: 'diak'|'tudasmunka'|'fejleszto'|'kutato'|'egyeni' };
}
export type BeallitasokValtozas = { [K in keyof Beallitasok]?: Partial<Beallitasok[K]> };
export interface BeallitasokValasz {
  verzio: 1;
  rev: string;
  ertek: Beallitasok;
  munkater: { id: string; nev: string; vault: string };
  setup_szukseges: boolean;
  ujrainditas: string[];
}
export function alapBeallitasok(): Beallitasok {
  return {
    altalanos: { nyelv: 'auto', inditas: 'utolso' },
    szerkeszto: { mod: 'elo', olvashato_szelesseg: true, helyesiras: true, tab_meret: 2, perjel: true },
    fajlok: { uj_mappa: '', csatolmany_mappa: 'Attachments', sablon_mappa: '_Template', napi_ut: '[Daily]/YYYY-MM-DD', link_formatum: 'rovid' },
    megjelenes: { tema: 'rendszer', betumeret: 16, csend: false },
    modulok: Object.fromEntries(MODULOK.map(k => [k, true])) as Record<ModulId, boolean>,
    adatvedelem: { asszisztens: true, tracker: true, ertesitesek: true, naptar: false },
    billentyuk: {}, setup: { kesz: false, elmeny: 'egyeni' },
  };
}
