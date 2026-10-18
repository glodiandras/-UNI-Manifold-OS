// Jegyzetkártya szerkesztése a kártyában (09-canvas-09). A kártya szerkesztője a CÉL jegyzet közös `Dokumentum`-án dolgozik
// (ugyanaz az egy írási út, mint a jegyzet fülé: automatikus mentés, hash-alapú ütközés, külső változás, kilépési mentés,
// pillanatkép). Egész jegyzetnél a teljes dokumentum szerkeszthető; `#fejezet` / `#^blokk` esetén csak a core által adott szelet
// (első–utolsó sor), és csak akkor, ha az a dokumentumban pontosan ugyanott, változatlanul áll — különben nincs írás.
//
// Biztonsági elvek:
//   - csak olvasható, ütköző vagy eltűnt dokumentumba nem írunk: a szerkesztés meg sem nyílik, a hiba mondja, mit tegyen a felhasználó;
//   - a szerkesztő változása csend után kerül a dokumentumba, egyetlen legkisebb cserével (a szelet többi bájtja érintetlen);
//   - ha a dokumentum közben máshonnan változik, a szerkesztő követi (a szelet új tartalma), vagy — ha a begépelt szöveg még
//     nem került át — bezár, és a begépelt szöveget a vágólapra teszi;
//   - a nyitott szerkesztés a core felé „mentetlen” (a gép nem ír a jegyzetre), amíg át nem vitte a szöveget.

import { ChangeSet, EditorState } from '@codemirror/state';
import { EditorView, keymap, tooltips } from '@codemirror/view';
import { ApiHiba } from '../lib/core/api';
import { t } from '../lib/i18n';
import type { FajlInfo } from '../lib/vault/fajlok.svelte';
import { linkek } from '../lib/vault/linkek.svelte';
import { bovitmenyek } from '../szerkeszto/beallitas';
import type { Csatolt, Dokumentum } from '../szerkeszto/dokumentum/dokumentum.svelte';
import { csere } from '../szerkeszto/dokumentum/kulonbseg';
import { szerkesztok } from '../szerkeszto/szerkesztok.svelte';
import { vagolapra } from '../szerkeszto/vagolap';
import { KARTYA_ATVETEL_MS } from './forras';

export interface JegyzetSzerkesztoOpciok {
  /** a cél jegyzet útja */
  ut: string;
  /** a canvas útja (a szelet kérésének forrása) */
  canvasUt: string;
  /** a kártya `subpath`-ja (`#fejezet`, `#^blokk`), vagy nincs */
  subpath?: string;
  kiegeszites: { fajlok: () => FajlInfo[]; legutobbi: () => string[] };
  /** a szerkesztő lezárult; a `hiba` a felhasználónak szóló helyreállító szöveg (cím, szöveg), ha nem sima lezárás volt */
  lezarult: (hiba?: { cim: string; szoveg: string }) => void;
}

export interface JegyzetSzerkeszto {
  /** a szerkesztő azonnali lebontása (a függő szöveg átvitele után) */
  bont: () => void;
  /** a függő szöveg átvitele a dokumentumba (mentés, kilépés előtt) */
  atvesz: () => void;
  /** átvitel + azonnali mentés (⌘S) */
  ment: () => Promise<void>;
}

/** A szelet helye a dokumentumban: [kezdet, vég) eltolás, és a core által adott szöveg ott álljon pontosan. */
function szeletHelye(d: Dokumentum, kezd: number | null | undefined, veg: number | null | undefined, szoveg: string): { from: number; to: number } | null {
  if (!Number.isSafeInteger(kezd) || !Number.isSafeInteger(veg) || kezd! < 1 || veg! < kezd! || veg! > d.szoveg.lines) return null;
  const from = d.szoveg.line(kezd!).from;
  const to = d.szoveg.line(veg!).to;
  return d.szoveg.sliceString(from, to) === szoveg ? { from, to } : null;
}

export function jegyzetSzerkesztoNyit(el: HTMLElement, o: JegyzetSzerkesztoOpciok): JegyzetSzerkeszto {
  let lezart = false;
  let doc: Dokumentum | null = null;
  let view: EditorView | null = null;
  let le: (() => void) | null = null;
  let idozito: ReturnType<typeof setTimeout> | null = null;
  /** a szelet helye és a legutóbb a dokumentumban látott szövege */
  let eleje = 0;
  let ismert = '';
  let fuggo = false;
  let sajatValtozas = false;

  const csatolt: Csatolt = {
    alkalmaz: (cs) => {
      const d = doc;
      if (!d || !view || lezart || sajatValtozas) return;
      if (fuggo) {
        // a begépelt szöveg még nincs a dokumentumban, a dokumentum pedig máshonnan változott: nem fésülhető össze csendben
        const szoveg = view.state.doc.toString();
        fuggo = false;
        void vagolapra(szoveg);
        bezar({ cim: t('The note changed elsewhere'), szoveg: t('Your latest text in the card was copied to the clipboard. Open the note to review it.') });
        return;
      }
      const regiVeg = eleje + ismert.length;
      const ujEleje = cs.mapPos(eleje, 1);
      const ujVeg = cs.mapPos(regiVeg, -1);
      eleje = ujEleje;
      ismert = d.szoveg.sliceString(ujEleje, Math.max(ujEleje, ujVeg));
      if (view.state.doc.toString() !== ismert) {
        sajatValtozas = true;
        try {
          view.dispatch({ changes: { from: 0, to: view.state.doc.length, insert: ismert } });
        } finally {
          sajatValtozas = false;
        }
      }
    },
    mentesElott: () => atvesz(),
    mentetlen: () => fuggo,
  };

  function atvesz(): void {
    if (idozito) clearTimeout(idozito);
    idozito = null;
    const d = doc;
    if (!d || !view || !fuggo) return;
    const uj = view.state.doc.toString();
    if (uj === ismert) {
      fuggo = false;
      d.mentetlenValtozott();
      return;
    }
    const tiltas = d.csakOlvashato ?? (d.allapot === 'utkozes' ? t('The note changed on disk. Resolve the conflict in its tab first.') : d.allapot === 'eltunt' ? t('The note file is gone.') : null);
    if (tiltas || d.szoveg.sliceString(eleje, eleje + ismert.length) !== ismert) {
      fuggo = false;
      void vagolapra(uj);
      bezar({
        cim: t('The note could not be updated'),
        szoveg: `${tiltas ?? t('The text changed since the card opened.')} ${t('Your latest text was copied to the clipboard.')}`,
      });
      return;
    }
    const c = csere(ismert, uj);
    if (c) {
      const cs = ChangeSet.of({ from: eleje + c.from, to: eleje + c.to, insert: c.insert }, d.szoveg.length);
      d.valtozott(cs, cs.apply(d.szoveg), csatolt, true);
    }
    ismert = uj;
    fuggo = false;
    d.mentetlenValtozott();
  }

  function bezar(hiba?: { cim: string; szoveg: string }): void {
    if (lezart) return;
    atvesz();
    lezart = true;
    if (idozito) clearTimeout(idozito);
    le?.();
    le = null;
    view?.destroy();
    view = null;
    const d = doc;
    doc = null;
    if (d) void szerkesztok.dokumentumok.elenged(d);
    o.lezarult(hiba);
  }

  function bont(): void {
    if (lezart) return;
    atvesz();
    lezart = true;
    if (idozito) clearTimeout(idozito);
    le?.();
    le = null;
    view?.destroy();
    view = null;
    const d = doc;
    doc = null;
    if (d) void szerkesztok.dokumentumok.elenged(d);
  }

  void (async () => {
    try {
      const d = await szerkesztok.dokumentumok.megnyit(o.ut);
      if (lezart) {
        void szerkesztok.dokumentumok.elenged(d);
        return;
      }
      if (!d.mentetlen) await d.kulsoValtozas();
      if (lezart) {
        void szerkesztok.dokumentumok.elenged(d);
        return;
      }
      if (d.csakOlvashato) throw new Hiba(t('The note is read-only: {ok}', { ok: d.csakOlvashato }));
      if (d.allapot === 'utkozes') throw new Hiba(t('The note changed on disk. Open it and resolve the conflict, then edit it here.'));
      if (d.allapot === 'eltunt') throw new Hiba(t('The note file is gone (deleted or moved).'));
      let from = 0;
      let to = d.szoveg.length;
      if (o.subpath) {
        const alcel = o.subpath.replace(/^#/, '');
        const b = await linkek.beagyazas(o.canvasUt, o.ut, alcel);
        if (lezart) {
          void szerkesztok.dokumentumok.elenged(d);
          return;
        }
        const h = b.alcel_hiba ? null : szeletHelye(d, b.kezd, b.veg, b.szoveg ?? '');
        if (!h) throw new Hiba(t('This part of the note cannot be edited in the card. Open the note to edit it.'));
        ({ from, to } = h);
      }
      doc = d;
      eleje = from;
      ismert = d.szoveg.sliceString(from, to);
      le = d.csatol(csatolt);
      d.mentetlenValtozott();
      view = new EditorView({
        parent: el,
        state: EditorState.create({
          doc: ismert,
          extensions: [
            tooltips({ parent: document.body }),
            ...bovitmenyek({ mod: 'elo', csakOlvashato: false, ut: o.ut, cimke: t('Edit note card'), kiegeszites: o.kiegeszites }),
            keymap.of([{ key: 'Escape', run: () => (bezar(), true) }]),
            EditorView.updateListener.of((u) => {
              if (!u.docChanged || sajatValtozas) return;
              fuggo = true;
              d.mentetlenValtozott();
              if (idozito) clearTimeout(idozito);
              idozito = setTimeout(atvesz, KARTYA_ATVETEL_MS);
            }),
            EditorView.domEventHandlers({
              blur: (_e, v) => {
                setTimeout(() => {
                  if (!v.dom.contains(document.activeElement) && !document.activeElement?.closest('.cm-tooltip, .nt-lebego')) bezar();
                }, 0);
              },
            }),
          ],
        }),
      });
      view.focus();
      view.dispatch({ selection: { anchor: view.state.doc.length } });
    } catch (e) {
      const szoveg = e instanceof Hiba ? e.message : e instanceof ApiHiba ? e.message : e instanceof Error ? e.message : String(e);
      bezar({ cim: t('The note cannot be edited here'), szoveg });
    }
  })();

  return { bont, atvesz, ment: async () => { atvesz(); await doc?.ment(); } };
}

class Hiba extends Error {}
