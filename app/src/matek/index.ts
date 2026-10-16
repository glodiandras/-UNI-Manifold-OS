// A matek-motor parancsai (C24b; docs/C24-TERV.md 5.6): a C17 helyőrzőit ugyanazon az azonosítón váltják ki (⌘P, a jegyzet
// helyi menüje).
//   matek.levezetes — a kijelölt (vagy a kurzor körüli bekezdés) sorai a core levezetés-ellenőrzőjén (modell nélkül, a CAS-homokozóban);
//                     az ítélet margójel a sorokon, a fájlba nem ír.
//   matek.megoldas  — a kijelölt feladat a „Megoldás” feladatként indul (modell + CAS, második vélemény); a callout gépi írással a
//                     feladat alá kerül, a vége a vezérlő szokásos értesítése.

import type { EditorState } from '@codemirror/state';
import type { EditorView } from '@codemirror/view';
import type { Felulet } from '../lib/elrendezes/felulet.svelte';
import { t, tk } from '../lib/i18n';
import { ertesitesek } from '../lib/ertesites/ertesites.svelte';
import type { Regiszter } from '../lib/parancsok/regiszter';
import { szerkesztok } from '../szerkeszto/szerkesztok.svelte';
import { matekApi } from './api';
import { jelekValaszbol, margoBeallit, margoUrit } from './margo';
import './matek.css';

const MAX_SOR = 60;

/** A parancs sorai: a kijelölés sorai (a kijelölés végén álló sor eleje nem számít), üres kijelölésnél a kurzor bekezdése
 *  (az üres sorok közti összefüggő rész). → { tol, ig } (1-től, zárt), vagy null, ha a kurzor üres soron áll. */
export function parancsSorai(state: EditorState): { tol: number; ig: number } | null {
  const s = state.selection.main;
  const doc = state.doc;
  if (!s.empty) {
    const elso = doc.lineAt(s.from).number;
    let utolso = doc.lineAt(s.to).number;
    if (utolso > elso && doc.line(utolso).from === s.to) utolso -= 1;
    return { tol: elso, ig: utolso };
  }
  const n = doc.lineAt(s.head).number;
  if (!doc.line(n).text.trim()) return null;
  let tol = n;
  let ig = n;
  while (tol > 1 && doc.line(tol - 1).text.trim()) tol -= 1;
  while (ig < doc.lines && doc.line(ig + 1).text.trim()) ig += 1;
  return { tol, ig };
}

function sorok(state: EditorState, tol: number, ig: number): { sor: number; szoveg: string }[] {
  const ki = [];
  for (let n = tol; n <= ig; n++) ki.push({ sor: n, szoveg: state.doc.line(n).text });
  return ki;
}

function hibaSzoveg(e: unknown): string {
  return e instanceof Error ? e.message : String(e);
}

function aktivNezet(): { view: EditorView; ut: string } | null {
  const p = szerkesztok.aktiv;
  const view = p?.nezet();
  if (!p || !view || !p.ut.toLowerCase().endsWith('.md')) {
    ertesitesek.ertesit({ szint: 'info', cim: t('Nyiss meg egy jegyzetet'), szoveg: t('A parancs a szerkesztő kijelölt sorain fut.') });
    return null;
  }
  return { view, ut: p.ut };
}

export async function levezetesEllenorzese(view: EditorView): Promise<void> {
  const tart = parancsSorai(view.state);
  if (!tart) {
    ertesitesek.ertesit({ szint: 'info', cim: t('Jelöld ki a levezetést'), szoveg: t('A kijelölt sorok (vagy a kurzor bekezdése) kerülnek ellenőrzésre.') });
    return;
  }
  if (tart.ig - tart.tol + 1 > MAX_SOR) {
    ertesitesek.ertesit({ szint: 'figyelmeztetes', cim: t('Túl hosszú kijelölés'), szoveg: t('Legfeljebb {n} sort ellenőriz egyszerre.', { n: MAX_SOR }) });
    return;
  }
  view.dispatch({ effects: margoUrit.of(null) });
  let v;
  try {
    v = await matekApi.levezetes(sorok(view.state, tart.tol, tart.ig));
  } catch (e) {
    ertesitesek.ertesit({ szint: 'hiba', cim: t('A levezetés nem ellenőrizhető'), szoveg: hibaSzoveg(e) });
    return;
  }
  view.dispatch({ effects: margoBeallit.of(jelekValaszbol(v)) });
  const h = v.elso_hiba;
  if (v.allapot === 'hiba' && h)
    ertesitesek.ertesit({
      szint: 'figyelmeztetes',
      cim: t('Hiba a(z) {n}. sorban', { n: h.jegyzet_sor ?? h.sor }),
      szoveg: h.uzenet + (h.bizonytalan ? ' ' + t('(a hiba az előző elemezhető sor óta bármelyik lépésben lehet)') : ''),
    });
  else if (v.allapot === 'rendben')
    ertesitesek.ertesit({ szint: 'siker', cim: t('A levezetés rendben'), szoveg: v.megjegyzes ?? t('Minden átmenet helyes (CAS-ellenőrzés).') });
  else if (v.allapot === 'reszben_ellenorizve')
    ertesitesek.ertesit({ szint: 'info', cim: t('Hibát nem talált, de nem minden sor ellenőrizhető'), szoveg: t('A „–” jelű sorokat a CAS nem tudta eldönteni.') });
  else ertesitesek.ertesit({ szint: 'info', cim: t('A levezetés nem ellenőrizhető'), szoveg: v.indok ?? t('A sorok nem elemezhetők.') });
}

export async function megoldasInditas(view: EditorView, ut: string, mentes: () => Promise<void>): Promise<void> {
  const tart = parancsSorai(view.state);
  if (!tart) {
    ertesitesek.ertesit({ szint: 'info', cim: t('Jelöld ki a feladatot'), szoveg: t('A kijelölt sorok (vagy a kurzor bekezdése) a megoldandó feladat.') });
    return;
  }
  const feladat = sorok(view.state, tart.tol, tart.ig).map((s) => s.szoveg).join('\n');
  try {
    await mentes(); // a gépi írás nyitott, mentetlen dokumentumba nem ír (28(c))
    await matekApi.megoldas({ ut, tol: tart.tol, ig: tart.ig, feladat });
  } catch (e) {
    ertesitesek.ertesit({ szint: 'hiba', cim: t('A megoldás nem indult el'), szoveg: hibaSzoveg(e) });
    return;
  }
  ertesitesek.ertesit({
    szint: 'info',
    cim: t('A megoldás készül'),
    szoveg: t('A modell megoldja, a CAS ellenőrzi; a megoldás a feladat alá kerül (visszavonható). Ez percekig tarthat.'),
  });
}

export function matekTelepit(reg: Regiszter, felulet: Felulet): () => void {
  const jegyzetNyitva = () => !!felulet.munkaterulet.aktivFul?.ut?.toLowerCase().endsWith('.md');
  return reg.regisztralMind([
    {
      id: 'matek.levezetes',
      nev: tk('Levezetés ellenőrzése'),
      kategoria: tk('Jegyzet'),
      elerheto: jegyzetNyitva,
      futtat: async () => {
        const a = aktivNezet();
        if (a) await levezetesEllenorzese(a.view);
      },
    },
    {
      id: 'matek.megoldas',
      nev: tk('Megoldás'),
      kategoria: tk('Jegyzet'),
      elerheto: jegyzetNyitva,
      futtat: async () => {
        const a = aktivNezet();
        const p = szerkesztok.aktiv;
        if (a && p) await megoldasInditas(a.view, a.ut, () => p.mentes());
      },
    },
  ]);
}
