export const MODULOK = ['hivatkozasok', 'vazlat', 'tulajdonsagok', 'gyorsvalto', 'kereses', 'perjel', 'cimkek', 'sablonok', 'napi', 'canvas', 'bazis', 'graf', 'pdf', 'media', 'kartya', 'kviz', 'osszefoglalas', 'matek', 'kod', 'fuzet', 'video', 'kerdezz', 'asszisztens', 'naptar', 'felkeszultseg', 'tracker'] as const;
export type ModulId = typeof MODULOK[number];
export interface Beallitasok {
  altalanos: { nyelv: 'auto'|'hu'|'en'; inditas: 'utolso'|'valaszto' };
  szerkeszto: { mod: 'elo'|'forras'; olvashato_szelesseg: boolean; helyesiras: boolean; tab_meret: number; perjel: boolean;
    /** Auto-pair, külön-külön: zárójelek `( { [`, idézőjelek `" ' `` ` ``, Markdown-jelek `* _ ~ = $` (14-appearance-05). */
    auto_par_zarojel: boolean; auto_par_idezojel: boolean; auto_par_jeloles: boolean };
  fajlok: { uj_mappa: string; csatolmany_mappa: string; sablon_mappa: string; napi_ut: string; link_formatum: 'rovid'|'relativ'|'abszolut'; wikilinkek: boolean;
    /** Excluded files (14-appearance-06): útvonal-előtag vagy `/regex/`; csak láthatóságot szűr, a fájl érintetlen. */
    kizart: string[] };
  megjelenes: { tema: 'rendszer'|'vilagos'|'sotet'; betumeret: number; csend: boolean;
    /** Telepített betűcsalád neve a jegyzet szövegéhez / a monospace helyekhez; `''` = alapértelmezett (14-appearance-01/02). */
    betu_szoveg: string; betu_mono: string };
  modulok: Record<ModulId, boolean>;
  adatvedelem: { asszisztens: boolean; tracker: boolean; ertesitesek: boolean; naptar: boolean };
  billentyuk: Record<string,string>;
  setup: { kesz: boolean; elmeny: 'diak'|'tudasmunka'|'fejleszto'|'kutato'|'egyeni' };
  /** Developer mód (F7): a technikai nézetek kapcsolója; az indító ⌥-kattintása erre a munkamenetre bekapcsolja (`fejleszto_kenyszer`). */
  fejleszto: { mod: boolean };
}
export type BeallitasokValtozas = { [K in keyof Beallitasok]?: Partial<Beallitasok[K]> };
export interface BeallitasokValasz {
  verzio: 1;
  rev: string;
  ertek: Beallitasok;
  munkater: { id: string; nev: string; vault: string };
  setup_szukseges: boolean;
  /** Igaz, ha a Developer nézetet az indító kérte erre a munkamenetre (a mentett érték nem változott). */
  fejleszto_kenyszer?: boolean;
  ujrainditas: string[];
}
export function alapBeallitasok(): Beallitasok {
  return {
    altalanos: { nyelv: 'auto', inditas: 'utolso' },
    szerkeszto: { mod: 'elo', olvashato_szelesseg: true, helyesiras: true, tab_meret: 2, perjel: true, auto_par_zarojel: true, auto_par_idezojel: true, auto_par_jeloles: true },
    fajlok: { uj_mappa: '', csatolmany_mappa: 'Attachments', sablon_mappa: '_Template', napi_ut: '[Daily]/YYYY-MM-DD', link_formatum: 'rovid', wikilinkek: true, kizart: [] },
    megjelenes: { tema: 'rendszer', betumeret: 16, csend: false, betu_szoveg: '', betu_mono: '' },
    modulok: Object.fromEntries(MODULOK.map(k => [k, true])) as Record<ModulId, boolean>,
    adatvedelem: { asszisztens: true, tracker: true, ertesitesek: true, naptar: false },
    billentyuk: {}, setup: { kesz: false, elmeny: 'egyeni' },
    fejleszto: { mod: false },
  };
}
