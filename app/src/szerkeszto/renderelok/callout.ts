// Callout-típusok: az Obsidian típusai és aliasai, magyar alapcímmel (ha a `[!típus]` után nincs cím) és
// Lucide-ikonnal. Az ismeretlen típus a „note” stílusát kapja, a címe a típus neve nagy kezdőbetűvel (ahogy
// az Obsidianban). A későbbi modulok ide kötnek be (C23: `card`, C24: `solution`):
//
//   calloutTipusok.regisztral({ nevek: ['card'], cim: 'Kártya', ikon: …, szin: 'lila' });

import { t as tr, tk } from '../../lib/i18n';
import type { IconNode } from 'lucide';
import {
  Bug,
  Check,
  CircleCheck,
  CircleQuestionMark,
  ClipboardList,
  Flame,
  Info,
  List,
  Pencil,
  Quote,
  TriangleAlert,
  X,
  Zap,
} from '../../lib/ikon/ikonok';

export type CalloutSzin = 'kek' | 'cian' | 'zold' | 'narancs' | 'piros' | 'lila' | 'szurke';

export interface CalloutTipus {
  /** a típus és aliasai kisbetűvel; az első a fő név */
  nevek: readonly string[];
  /** alapcím aliasonként (a hiányzó a fő névé) */
  cimek: Readonly<Record<string, string>>;
  ikon: IconNode;
  szin: CalloutSzin;
}

const BEEPITETT: CalloutTipus[] = [
  { nevek: ['note'], cimek: { note: tk('Megjegyzés|callout') }, ikon: Pencil, szin: 'kek' },
  {
    nevek: ['abstract', 'summary', 'tldr'],
    cimek: { abstract: tk('Kivonat|callout'), summary: tk('Összefoglaló|callout'), tldr: tk('Röviden|callout') },
    ikon: ClipboardList,
    szin: 'cian',
  },
  { nevek: ['info'], cimek: { info: tk('Információ|callout') }, ikon: Info, szin: 'kek' },
  { nevek: ['todo'], cimek: { todo: tk('Teendő|callout') }, ikon: CircleCheck, szin: 'kek' },
  { nevek: ['tip', 'hint', 'important'], cimek: { tip: tk('Tipp|callout'), hint: tk('Ötlet|callout'), important: tk('Fontos|callout') }, ikon: Flame, szin: 'cian' },
  { nevek: ['success', 'check', 'done'], cimek: { success: tk('Siker|callout'), check: tk('Rendben|callout'), done: tk('Kész|callout') }, ikon: Check, szin: 'zold' },
  {
    nevek: ['question', 'help', 'faq'],
    cimek: { question: tk('Kérdés|callout'), help: tk('Segítség|callout'), faq: tk('Gyakori kérdés|callout') },
    ikon: CircleQuestionMark,
    szin: 'narancs',
  },
  {
    nevek: ['warning', 'caution', 'attention'],
    cimek: { warning: tk('Figyelmeztetés|callout'), caution: tk('Vigyázat|callout'), attention: tk('Figyelem|callout') },
    ikon: TriangleAlert,
    szin: 'narancs',
  },
  { nevek: ['failure', 'fail', 'missing'], cimek: { failure: tk('Kudarc|callout'), fail: tk('Sikertelen|callout'), missing: tk('Hiányzik|callout') }, ikon: X, szin: 'piros' },
  { nevek: ['danger', 'error'], cimek: { danger: tk('Veszély|callout'), error: tk('Hiba|callout') }, ikon: Zap, szin: 'piros' },
  { nevek: ['bug'], cimek: { bug: tk('Programhiba|callout') }, ikon: Bug, szin: 'piros' },
  { nevek: ['example'], cimek: { example: tk('Példa|callout') }, ikon: List, szin: 'lila' },
  { nevek: ['quote', 'cite'], cimek: { quote: tk('Idézet|callout'), cite: tk('Hivatkozás|callout') }, ikon: Quote, szin: 'szurke' },
];

export interface CalloutMegjelenes {
  tipus: string;
  cim: string;
  ikon: IconNode;
  szin: CalloutSzin;
}

export class CalloutTipusok {
  private readonly tipusok = new Map<string, CalloutTipus>();

  constructor(kezdo: CalloutTipus[] = BEEPITETT) {
    for (const t of kezdo) this.regisztral(t);
  }

  regisztral(t: CalloutTipus): () => void {
    for (const n of t.nevek) if (this.tipusok.has(n)) throw new Error(`már regisztrált callout-típus: ${n}`); // i18n-ignore: programozói hiba
    for (const n of t.nevek) this.tipusok.set(n, t);
    return () => {
      for (const n of t.nevek) if (this.tipusok.get(n) === t) this.tipusok.delete(n);
    };
  }

  /** A regisztrált típusok egyszer-egyszer (az aliasok nélkül), a regisztrálás sorrendjében. */
  lista(): CalloutTipus[] {
    return [...new Set(this.tipusok.values())];
  }

  /** A `[!típus]` megjelenése: ikon, szín és — ha a forrásban nincs cím — az alapcím. */
  megjelenes(tipus: string): CalloutMegjelenes {
    const kis = tipus.toLowerCase();
    const t = this.tipusok.get(kis);
    if (!t) {
      const note = this.tipusok.get('note')!;
      return { tipus: kis, cim: tipus.charAt(0).toUpperCase() + tipus.slice(1), ikon: note.ikon, szin: note.szin };
    }
    return { tipus: kis, cim: tr(t.cimek[kis] ?? t.cimek[t.nevek[0]] ?? tipus), ikon: t.ikon, szin: t.szin };
  }
}

export const calloutTipusok = new CalloutTipusok();
