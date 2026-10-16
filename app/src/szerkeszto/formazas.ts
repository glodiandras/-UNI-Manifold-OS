// Formázás: a kijelölés körbefogása jelölővel (⌘B `**`, ⌘I `*`, ⌘⇧H `==`, áthúzás `~~`, kód `` ` ``). Ha a
// kijelölés már körbe van fogva, a jelölő lekerül (váltó); üres kijelölésnél a két jelölő közé áll a kurzor.
//
// Üres kijelölésnél, ha a pár kódkerítést (`~~~~`) vagy vízszintes vonalat (`****`) nyitna, a jelölők közé a kijelölt
// `szöveg` helyőrző kerül (az első leütés lecseréli; C32). A `==` beszúrása figyelmeztet, ha a munkaterület jegyzetszabályai nem ajánlják.
//
// Üres kijelölésnél, ha a sor különben üres, és alatta a `====` setext-aláhúzás lenne (a fölötte álló
// bekezdéssort fejléccé tenné; C10.7, F4), a jelölők új bekezdésbe kerülnek: előbb egy üres sor (a tároló
// előtagjával, pl. `>`), alá a jelölők. A fölötte álló sor így nem változik, és a félkész `====` is csak
// látható szöveg, nem fejléc.
//
// A `*` és a `**` egymás mellett is állhat (`***x***` félkövér és dőlt): ott a csillagok sorozatának hossza
// dönt (`**` = legalább 2, `*` = páratlan), így a ⌘I a `**x**`-et nem bontja szét, hanem `***x***`-t csinál.

import { t } from '../lib/i18n';
import { ensureSyntaxTree, syntaxTree } from '@codemirror/language';
import { EditorSelection, type EditorState, type SelectionRange } from '@codemirror/state';
import type { EditorView } from '@codemirror/view';
import { ertesitesek } from '../lib/ertesites/ertesites.svelte';

type Hol = 'kivul' | 'belul';

function csillagok(szoveg: string, vegerol: boolean): number {
  let n = 0;
  if (vegerol) while (n < szoveg.length && szoveg[szoveg.length - 1 - n] === '*') n++;
  else while (n < szoveg.length && szoveg[n] === '*') n++;
  return n;
}

function aktivJel(jel: string, elotte: string, utana: string, belul: string): Hol | null {
  if (jel === '*' || jel === '**') {
    const talal = (k: number) => (jel === '**' ? k >= 2 : k % 2 === 1);
    const kivul = Math.min(csillagok(elotte, true), csillagok(utana, false));
    if (talal(kivul)) return 'kivul';
    const b = Math.min(csillagok(belul, false), csillagok(belul, true));
    return belul.length > 2 * b && talal(b) ? 'belul' : null;
  }
  const n = jel.length;
  if (elotte.slice(-n) === jel && utana.slice(0, n) === jel) return 'kivul';
  return belul.length >= 2 * n && belul.startsWith(jel) && belul.endsWith(jel) ? 'belul' : null;
}

/** A főkijelölés körül (vagy benne) áll-e a jelölő: a gomb „nyomva” állapota. */
export function korbefogva(state: EditorState, jel: string): boolean {
  const r = state.selection.main;
  if (r.empty) return false;
  const kontextus = 12;
  const elotte = state.sliceDoc(Math.max(0, r.from - kontextus), r.from);
  const utana = state.sliceDoc(r.to, Math.min(state.doc.length, r.to + kontextus));
  return aktivJel(jel, elotte, utana, state.sliceDoc(r.from, r.to)) !== null;
}

/** Az üres kijelölésnél beírt jelölőpár a sort setext-aláhúzássá tenné-e (a próbaállapot elemzése szerint). */
function setextLenne(s: EditorState, r: SelectionRange, jel: string): boolean {
  const sor = s.doc.lineAt(r.head);
  if (sor.number === 1 || !/^[\s>]*$/.test(sor.text)) return false;
  const proba = s.update({ changes: { from: r.head, insert: jel + jel } }).state;
  const uj = proba.doc.line(sor.number);
  const fa = ensureSyntaxTree(proba, uj.to, 200) ?? syntaxTree(proba);
  let lenne = false;
  fa.iterate({
    from: uj.from,
    to: uj.to,
    enter: (n) => {
      if (n.name.startsWith('SetextHeading') && n.to > uj.from) lenne = true;
      return !lenne;
    },
  });
  return lenne;
}

/** Az üres sorba beírt jelölőpár kódkerítést (`~~~~`) vagy vízszintes vonalat (`****`) nyitna-e (C32; C10.7 ötlete):
 *  a jegyzet többi része egy leütésig kódnak látszana. */
function blokkotNyitna(s: EditorState, r: SelectionRange, jel: string): boolean {
  const sor = s.doc.lineAt(r.head);
  if (!/^[\s>]*$/.test(sor.text)) return false;
  const proba = s.update({ changes: { from: r.head, insert: jel + jel } }).state;
  const uj = proba.doc.line(sor.number);
  const fa = ensureSyntaxTree(proba, uj.to, 200) ?? syntaxTree(proba);
  let lenne = false;
  fa.iterate({
    from: uj.from,
    to: uj.to,
    enter: (n) => {
      if ((n.name === 'FencedCode' || n.name === 'HorizontalRule') && n.from >= uj.from) lenne = true;
      return !lenne;
    },
  });
  return lenne;
}

/** A helyőrző szó a blokkot nyitó üres jelölőpár helyett (kijelölve: az első leütés lecseréli). */
const helyorzo = (): string => t('szöveg');

/** A munkaterület jegyzetszabályai nem ajánlják a `==kiemelés==` jelölést: a beszúrás figyelmeztet, de nem tagad meg.
 *  A megjelenítés marad. */
function kiemelesFigyelmeztet(): void {
  ertesitesek.ertesit({
    szint: 'figyelmeztetes',
    kulcs: 'formazas-kiemeles',
    cim: t('A ==kiemelés== nem ajánlott jelölés'),
    szoveg: t('A munkaterület jegyzetszabályai nem ajánlják a == kiemelést; a vault-ellenőrző jelezni fogja. Helyette félkövér (⌘B).'),
  });
}

export function korbefog(view: EditorView, jel: string): boolean {
  const s = view.state;
  if (s.readOnly) return false;
  const n = jel.length;
  let beszur = false;
  const tr = s.changeByRange((r) => {
    const kontextus = 12;
    const elotte = s.sliceDoc(Math.max(0, r.from - kontextus), r.from);
    const utana = s.sliceDoc(r.to, Math.min(s.doc.length, r.to + kontextus));
    const belul = s.sliceDoc(r.from, r.to);
    const hol = r.empty ? null : aktivJel(jel, elotte, utana, belul);
    if (hol === null) beszur = true;
    if (r.empty && blokkotNyitna(s, r, jel))
      return {
        changes: { from: r.head, insert: jel + helyorzo() + jel },
        range: EditorSelection.range(r.head + n, r.head + n + helyorzo().length),
      };
    if (r.empty && setextLenne(s, r, jel)) {
      // új bekezdés: a sor helyére üres (előtag-)sor, alá az előtag és a jelölőpár
      const sor = s.doc.lineAt(r.head);
      const elso = sor.text.trimEnd() + s.lineBreak + sor.text;
      return {
        changes: { from: sor.from, to: sor.to, insert: elso + jel + jel },
        range: EditorSelection.cursor(sor.from + elso.length + n),
      };
    }
    if (hol === 'kivul')
      return {
        changes: [
          { from: r.from - n, to: r.from },
          { from: r.to, to: r.to + n },
        ],
        range: EditorSelection.range(r.from - n, r.to - n),
      };
    if (hol === 'belul')
      return {
        changes: [
          { from: r.from, to: r.from + n },
          { from: r.to - n, to: r.to },
        ],
        range: EditorSelection.range(r.from, r.to - 2 * n),
      };
    return {
      changes: [
        { from: r.from, insert: jel },
        { from: r.to, insert: jel },
      ],
      range: EditorSelection.range(r.from + n, r.to + n),
    };
  });
  view.dispatch(s.update(tr, { scrollIntoView: true, userEvent: 'input.formazas' }));
  if (jel === '==' && beszur) kiemelesFigyelmeztet();
  return true;
}
