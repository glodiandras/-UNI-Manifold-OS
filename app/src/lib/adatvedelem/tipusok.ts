// A Privacy Center szerződése (core/adatvedelem.py): valós állapot, csak olvasható.
export interface Letoltes { fajta: 'models' | 'video_links'; nev: string; mikor: string; eredmeny: string }
export interface HalozatAllapot {
  offline: boolean;
  engedett: { kod: 'models' | 'runtime_tools' | 'video_links'; elerheto: boolean }[];
  tiltott: string[];
  utolso_letoltesek: Letoltes[];
}
export interface TelepitettModell { nev: string; repo: string; feladat: string[]; allapot: string; bajt: number }
export interface AdatHely { kod: string; ut: string | null; bajt: number | null; van: boolean; torolheto: boolean }
export interface AdatvedelemAllapot {
  verzio: 1;
  mikor: string;
  halozat: HalozatAllapot;
  modellek: { telepitve: TelepitettModell[]; ut: string | null; bajt: number; hiba: string | null };
  adat: AdatHely[];
  memoria: { kapcsolo: boolean; tetelek: { mintak: number; muveletek: number; elutasitott: number; hangolas: number }; osszes: number };
  tracker: { be: boolean; ut: string; bajt: number; van: boolean; tarol: string[]; nem_tarol: string[] };
  integraciok: { kod: 'calendar' | 'notifications' | 'assistant' | 'tracker'; be: boolean; elerheto: boolean | null; utolso: string | null }[];
  engedelyek: { naptar: { kapcsolo: boolean; esemeny: string | null; emlekezteto: string | null }; ertesitesek: { kapcsolo: boolean } };
}
