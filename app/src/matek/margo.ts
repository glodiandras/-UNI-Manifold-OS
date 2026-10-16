// A levezetés-ellenőrzés margójele (C24b; docs/C24-TERV.md 5.6): a core ítélete (`POST /api/matek/levezetes`) a jegyzet soraira
// kerül sor-dekorációként — ✓ (helyes átmenet), ✗ (az első hibás sor, az ítélet szövegével), – (nem ellenőrizhető). A fájlba nem ír.
// A jel a megjelölt sorok szerkesztésekor és Esc-re eltűnik; a többi szerkesztés csak eltolja.

import { t, tk } from '../lib/i18n';
import { RangeSetBuilder, StateEffect, StateField, type Extension } from '@codemirror/state';
import { Decoration, type DecorationSet, EditorView, keymap } from '@codemirror/view';

export type JelFajta = 'ok' | 'hiba' | 'nem';

export interface MargoJel {
  /** a jegyzet sora (1-től) */
  sor: number;
  fajta: JelFajta;
  /** a jel magyarázata (a sor `title`-je) */
  szoveg: string;
}

export const JEL_SZOVEG: Record<JelFajta, string> = { ok: '✓', hiba: '✗', nem: '–' };

export const margoBeallit = StateEffect.define<MargoJel[]>();
export const margoUrit = StateEffect.define<null>();

interface Allapot {
  deko: DecorationSet;
  /** a megjelölt tartomány (a szerkesztése törli a jeleket); null: nincs jel */
  tol: number;
  ig: number;
}

const URES: Allapot = { deko: Decoration.none, tol: -1, ig: -1 };

function epit(view: { doc: EditorView['state']['doc'] }, jelek: MargoJel[]): Allapot {
  const b = new RangeSetBuilder<Decoration>();
  const rendezett = [...jelek].filter((j) => j.sor >= 1 && j.sor <= view.doc.lines).sort((a, c) => a.sor - c.sor);
  let tol = -1;
  let ig = -1;
  let elozo = -1;
  for (const j of rendezett) {
    if (j.sor === elozo) continue; // soronként egy jel (a hívó a súlyosabbat adja előbb)
    elozo = j.sor;
    const sor = view.doc.line(j.sor);
    if (tol < 0) tol = sor.from;
    ig = sor.to;
    b.add(
      sor.from,
      sor.from,
      Decoration.line({
        class: `matek-jel matek-jel-${j.fajta}`,
        attributes: { title: j.szoveg, 'data-matek-jel': JEL_SZOVEG[j.fajta], 'aria-label': `${JEL_SZOVEG[j.fajta]} ${j.szoveg}` },
      }),
    );
  }
  return tol < 0 ? URES : { deko: b.finish(), tol, ig };
}

export const margoMezo = StateField.define<Allapot>({
  create: () => URES,
  update(a, tr) {
    for (const e of tr.effects) {
      if (e.is(margoUrit)) return URES;
      if (e.is(margoBeallit)) return epit(tr.state, e.value);
    }
    if (!tr.docChanged || a.tol < 0) return a;
    let erintett = false;
    tr.changes.iterChangedRanges((fA, tA) => {
      if (fA <= a.ig && tA >= a.tol) erintett = true;
    });
    if (erintett) return URES;
    return { deko: a.deko.map(tr.changes), tol: tr.changes.mapPos(a.tol), ig: tr.changes.mapPos(a.ig) };
  },
  provide: (f) => EditorView.decorations.from(f, (a) => a.deko),
});

/** Van-e látható margójel (az Esc csak ekkor nyeli el a billentyűt). */
export function vanJel(state: EditorView['state']): boolean {
  return (state.field(margoMezo, false)?.tol ?? -1) >= 0;
}

export function matekMargo(): Extension {
  return [
    margoMezo,
    keymap.of([
      {
        key: 'Escape',
        run(view) {
          if (!vanJel(view.state)) return false;
          view.dispatch({ effects: margoUrit.of(null) });
          return true;
        },
      },
    ]),
  ];
}

// ------------------------------------------------------------------ a core válasza → jelek

export interface LevezetesValasz {
  allapot: 'rendben' | 'reszben_ellenorizve' | 'hiba' | 'nem_ellenorizheto';
  /** miért nem ellenőrizhető (a core `indok` mezője) */
  indok?: string;
  elso_hiba?: { sor: number; jegyzet_sor: number | null; fajta: string; uzenet: string; bizonytalan?: boolean } | null;
  atmenetek?: { honnan: number; hova: number; jegyzet_hova: number | null; itelet: string; bizonytalan?: boolean }[];
  megjegyzes?: string;
  vegeredmeny?: { valtozo: string; halmaz: string };
}

const ITELET: Record<string, string> = {
  ekvivalens: tk('ekvivalens az előző sorral'),
  szures: tk('helyes szűrés (a megoldáshalmaz szűkült, de a megoldás megmaradt)'),
  bovulo: tk('bővülő lépés (hamis gyök kerülhet be: ellenőrizd a végén)'),
  nem_eldontheto: tk('a CAS nem tudta eldönteni'),
  nem_elemezheto: tk('a sor nem elemezhető'),
};

/** A core ítélete → margójelek (a hibás sor jele előbb, hogy az nyerjen). */
export function jelekValaszbol(v: LevezetesValasz): MargoJel[] {
  const ki: MargoJel[] = [];
  const h = v.elso_hiba;
  if (h && h.jegyzet_sor) ki.push({ sor: h.jegyzet_sor, fajta: 'hiba', szoveg: h.uzenet || t('hibás átmenet') });
  for (const a of v.atmenetek ?? []) {
    if (!a.jegyzet_hova) continue;
    const fajta: JelFajta = a.itelet === 'hiba' ? 'hiba' : ['ekvivalens', 'szures', 'bovulo'].includes(a.itelet) ? 'ok' : 'nem';
    ki.push({ sor: a.jegyzet_hova, fajta, szoveg: ITELET[a.itelet] ? t(ITELET[a.itelet]) : fajta === 'hiba' ? t('hibás átmenet') : a.itelet });
  }
  return ki;
}
