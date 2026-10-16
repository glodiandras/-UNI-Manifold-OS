// A Health nézet szerződése (core/egeszseg.py): minden ellenőrzés egy sor; a szöveg angol tartalék, a `kod` stabil.
export type EgeszsegAllapot = 'ok' | 'info' | 'figyelem' | 'hiba';
export type Skalar = string | number | boolean | null;
export interface EgeszsegReszlet { kulcs: string; ertek: Skalar }
export interface EgeszsegSor {
  kod: string;
  cim: string;
  allapot: EgeszsegAllapot;
  uzenet_kod: string;
  param: Record<string, Skalar>;
  /** A core angol szövege a paraméterekkel kitöltve (a felület ezt mutatja). */
  uzenet: string;
  /** A gépi javítás azonosítója (csak biztonságos, visszafordítható művelet), vagy null. */
  javitas: string | null;
  reszletek: EgeszsegReszlet[];
  /** A doctor fejlesztői szövege: csak Developer módban látszik. */
  nyers?: string;
}
export interface EgeszsegJelentes {
  verzio: 1;
  zold: boolean;
  osszesen: Record<EgeszsegAllapot, number>;
  ellenorzesek: EgeszsegSor[];
}
export interface JavitasEredmeny {
  ok: boolean;
  javitas: string;
  uzenet: string;
  param: Record<string, Skalar>;
  ellenorzesek: EgeszsegSor[];
}

/** A „Learn more” célja (core `GET /api/doku/learn`): az útmutató oldala és a téma szakasza Markdown-ban. */
export interface DokuCel {
  tema: string;
  oldal: { azonosito: string; fajl: string; cim: string };
  horgony: string;
  fejlec: string;
  szakasz: string;
  /** a munkatér jegyzetének útja, ha a munkatér tartalmazza az útmutatót (demo); egyébként null */
  munkater_ut: string | null;
}
