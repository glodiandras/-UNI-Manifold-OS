// A jegyzet jobb alsó sarkának mentés-jelzése (E12, CLAUDE.md 80(f)): az automatikus mentés látszik, de nem zavar.
//
//   tiszta, épp most mentve   →  „Mentve” (erősebb, ERES_MS-ig)
//   tiszta, korábban mentve   →  „Mentve” (halvány)
//   piszkos (a gépelés után, a mentés előtt) → halvány pont szöveg nélkül (nem villog)
//   mentés folyik             →  pont; „Mentés…” csak ha a mentés LASSU_MS-nál tovább tart (a gyors mentés nem villog)
//   hiba / ütközés / eltűnt   →  itt semmi: a fejlécben a meglévő, soha nem rejtett jel áll (25. döntés, C38)
//   nincs még mentés (megnyitás után) → semmi

import { t } from '../../lib/i18n';
import type { MentesAllapot } from './dokumentum.svelte';

/** Ennyi ideig erősebb a „Mentve” a mentés után. */
export const ERES_MS = 2000;
/** Ennyi után írja ki a folyó mentésnél a „Mentés…” szöveget. */
export const LASSU_MS = 700;

export type JelzesFajta = 'nincs' | 'pont' | 'mentes' | 'mentve-eros' | 'mentve';

export interface Jelzes {
  fajta: JelzesFajta;
  /** látható szöveg ('' a pontnál és a semminél) */
  szoveg: string;
  /** képernyőolvasónak (a pontnál is) */
  cimke: string;
}

/** A mentés-jelzés állapotgépe (tiszta függvény). `utolsoMentes`: a legutóbbi sikeres mentés ideje (ms), vagy `null`;
 *  `most`: az óra; `mentesKezdet`: a folyó mentés kezdete (ms), vagy `null`. */
export function mentesJelzes(allapot: MentesAllapot | undefined, utolsoMentes: number | null, most: number, mentesKezdet: number | null = null): Jelzes {
  switch (allapot) {
    case 'piszkos':
      return { fajta: 'pont', szoveg: '', cimke: t('Módosítva, a mentés következik') };
    case 'mentes':
      return mentesKezdet !== null && most - mentesKezdet >= LASSU_MS
        ? { fajta: 'mentes', szoveg: t('Mentés…'), cimke: t('Mentés folyamatban') }
        : { fajta: 'pont', szoveg: '', cimke: t('Mentés folyamatban') };
    case 'tiszta':
      if (utolsoMentes === null) return { fajta: 'nincs', szoveg: '', cimke: '' };
      return { fajta: most - utolsoMentes < ERES_MS ? 'mentve-eros' : 'mentve', szoveg: t('Mentve'), cimke: t('Mentve') };
    default:
      return { fajta: 'nincs', szoveg: '', cimke: '' };
  }
}
