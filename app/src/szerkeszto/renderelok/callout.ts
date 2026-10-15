// Callout-típusok: az Obsidian típusai és aliasai, magyar alapcímmel (ha a `[!típus]` után nincs cím) és
// Lucide-ikonnal. Az ismeretlen típus a „note” stílusát kapja, a címe a típus neve nagy kezdőbetűvel (ahogy
// az Obsidianban). A későbbi modulok ide kötnek be (C23: `card`, C24: `solution`):
//
//   calloutTipusok.regisztral({ nevek: ['card'], cim: 'Kártya', ikon: …, szin: 'lila' });

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
  { nevek: ['note'], cimek: { note: 'Megjegyzés' }, ikon: Pencil, szin: 'kek' },
  {
    nevek: ['abstract', 'summary', 'tldr'],
    cimek: { abstract: 'Kivonat', summary: 'Összefoglaló', tldr: 'Röviden' },
    ikon: ClipboardList,
    szin: 'cian',
  },
  { nevek: ['info'], cimek: { info: 'Információ' }, ikon: Info, szin: 'kek' },
  { nevek: ['todo'], cimek: { todo: 'Teendő' }, ikon: CircleCheck, szin: 'kek' },
  { nevek: ['tip', 'hint', 'important'], cimek: { tip: 'Tipp', hint: 'Ötlet', important: 'Fontos' }, ikon: Flame, szin: 'cian' },
  { nevek: ['success', 'check', 'done'], cimek: { success: 'Siker', check: 'Rendben', done: 'Kész' }, ikon: Check, szin: 'zold' },
  {
    nevek: ['question', 'help', 'faq'],
    cimek: { question: 'Kérdés', help: 'Segítség', faq: 'Gyakori kérdés' },
    ikon: CircleQuestionMark,
    szin: 'narancs',
  },
  {
    nevek: ['warning', 'caution', 'attention'],
    cimek: { warning: 'Figyelmeztetés', caution: 'Vigyázat', attention: 'Figyelem' },
    ikon: TriangleAlert,
    szin: 'narancs',
  },
  { nevek: ['failure', 'fail', 'missing'], cimek: { failure: 'Kudarc', fail: 'Sikertelen', missing: 'Hiányzik' }, ikon: X, szin: 'piros' },
  { nevek: ['danger', 'error'], cimek: { danger: 'Veszély', error: 'Hiba' }, ikon: Zap, szin: 'piros' },
  { nevek: ['bug'], cimek: { bug: 'Programhiba' }, ikon: Bug, szin: 'piros' },
  { nevek: ['example'], cimek: { example: 'Példa' }, ikon: List, szin: 'lila' },
  { nevek: ['quote', 'cite'], cimek: { quote: 'Idézet', cite: 'Hivatkozás' }, ikon: Quote, szin: 'szurke' },
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
    for (const n of t.nevek) if (this.tipusok.has(n)) throw new Error(`már regisztrált callout-típus: ${n}`);
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
    return { tipus: kis, cim: t.cimek[kis] ?? t.cimek[t.nevek[0]] ?? tipus, ikon: t.ikon, szin: t.szin };
  }
}

export const calloutTipusok = new CalloutTipusok();
