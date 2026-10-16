// Összecsukás az Olvasóban (01-rendering-05/06): ugyanaz az állapot, mint a szerkesztőé. Az Olvasó a rejtett CodeMirror-nézet
// hajtás-állapotát mutatja, és a saját gombja is oda ír (nézet-állapot, a jegyzet szövege nem változik). A felső szintű
// címsor a következő azonos vagy magasabb szintű címsorig rejti a blokkokat; a gyermekes listaelem az első blokkja utáni
// tartalmát. A gomb csak a dokumentum saját elemein jelenik meg (a beágyazott jegyzet tartalmán nem).

import type { EditorView } from '@codemirror/view';
import { t } from '../../lib/i18n';
import { ikonElem } from '../../lib/ikon/ikonElem';
import { ChevronRight } from '../../lib/ikon/ikonok';
import { hajthatoTartomany, hajtottAzonSoron, sorHajtasValt } from '../hajtogatas';

const CIMSOR = /^H([1-6])$/;

/** Rejtés: a `hidden` attribútum (az Olvasó-keresés és az akadálymentesítés is kihagyja) és a beágyazott stílus (a szerzői
 *  `display` sem írhatja felül). Csak a saját rejtését bontja vissza. */
function rejt(e: HTMLElement, rejtve: boolean): void {
  if (rejtve) {
    e.dataset.hajtasRejtett = '';
    e.hidden = true;
    e.style.display = 'none';
  } else if (e.dataset.hajtasRejtett !== undefined) {
    delete e.dataset.hajtasRejtett;
    e.hidden = false;
    e.style.display = '';
  }
}

function gomb(e: HTMLElement): HTMLButtonElement {
  let b = e.querySelector<HTMLButtonElement>(':scope > button.olvaso-hajto');
  if (!b) {
    b = document.createElement('button');
    b.type = 'button';
    b.className = 'olvaso-hajto';
    b.appendChild(ikonElem(ChevronRight, 14));
    e.prepend(b);
  }
  return b;
}

/** A gombok és a rejtés alkalmazása a kirajzolt Olvasóra (újrarajzolás és minden hajtásváltás után; idempotens). */
export function olvasoHajtas(gyoker: HTMLElement, view: EditorView): void {
  const state = view.state;
  const doc = state.doc;
  const csukott = new Set<HTMLElement>();

  const jeloltek: HTMLElement[] = [];
  for (const e of gyoker.children) if (e instanceof HTMLElement && CIMSOR.test(e.tagName) && e.dataset.from !== undefined) jeloltek.push(e);
  for (const li of gyoker.querySelectorAll<HTMLElement>('li[data-from]')) jeloltek.push(li);

  for (const e of jeloltek) {
    const from = Number(e.dataset.from);
    const r = Number.isInteger(from) && from >= 0 && from <= doc.length ? hajthatoTartomany(state, doc.lineAt(from).from) : null;
    if (!r) {
      e.querySelector(':scope > button.olvaso-hajto')?.remove();
      delete e.dataset.hajthato;
      continue;
    }
    const sorKezdet = doc.lineAt(from).from;
    const csukva = !!hajtottAzonSoron(state, sorKezdet);
    if (csukva) csukott.add(e);
    e.dataset.hajthato = '';
    const b = gomb(e);
    b.classList.toggle('csukva', csukva);
    b.setAttribute('aria-expanded', String(!csukva));
    b.setAttribute('aria-label', csukva ? t('Kibontás') : t('Összecsukás'));
    b.title = b.getAttribute('aria-label')!;
    b.onclick = (ev) => {
      ev.preventDefault();
      ev.stopPropagation();
      sorHajtasValt(view, sorKezdet);
      olvasoHajtas(gyoker, view);
    };
  }

  // felső szintű címsor-szakaszok
  let rejtSzint: number | null = null;
  for (const e of gyoker.children) {
    if (!(e instanceof HTMLElement)) continue;
    if (e.dataset.from === undefined) {
      rejtSzint = null; // a lábjegyzet-szakasz mindig látszik
      rejt(e, false);
      continue;
    }
    const m = CIMSOR.exec(e.tagName);
    const szint = m ? Number(m[1]) : null;
    if (szint !== null && rejtSzint !== null && szint <= rejtSzint) rejtSzint = null;
    rejt(e, rejtSzint !== null);
    if (szint !== null && rejtSzint === null && csukott.has(e)) rejtSzint = szint;
  }

  // listaelemek: az első blokk utáni tartalom
  for (const li of gyoker.querySelectorAll<HTMLElement>('li[data-from]')) {
    let elso = true;
    for (const c of li.children) {
      if (!(c instanceof HTMLElement) || c.classList.contains('olvaso-hajto')) continue;
      rejt(c, !elso && csukott.has(li));
      elso = false;
    }
  }
}
