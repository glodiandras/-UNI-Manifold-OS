// Képlet-OCR (C21, 5. pont): a vágólapon álló képernyőkép képlete LaTeX-ben a kurzorhoz (⌥⌘L).
//
// A core olvassa a vágólapot és hívja a kalibrált `ocr_keplet` modellt (`POST /api/keplet-ocr`); a felület csak beszúr, a szerkesztő
// egyetlen írási útján (egy tranzakció: a ⌘Z egy lépés). A ⌘⇧L a CodeMirror `searchKeymap`-jében foglalt (`selectSelectionMatches`),
// ezért a parancs billentyűje a szabad ⌥⌘L (a regiszter ütközés-próbája a szerkesztő keymapjeit is nézi).

import { t } from '../lib/i18n';
import type { EditorView } from '@codemirror/view';
import { ApiHiba, kerdez } from '../lib/core/api';
import { ertesitesek } from '../lib/ertesites/ertesites.svelte';

export interface KepletOcrValasz {
  latex: string;
  modell?: string;
  proba?: boolean;
}

/** A beszúrandó szöveg: többsoros vagy környezetes képlet blokk (`$$…$$`), különben soron belüli (`$…$`). */
export function kepletSzoveg(latex: string): string {
  const k = latex.trim();
  return /\n|\\begin\{/.test(k) ? `$$\n${k}\n$$` : `$${k}$`;
}

/** A képlet beszúrása a nézet AKTUÁLIS kijelölésének helyére (a kijelölt szöveget lecseréli). → a beszúrt szöveg. */
export function kepletBeszur(v: EditorView, latex: string): string {
  const szoveg = kepletSzoveg(latex);
  const { from, to } = v.state.selection.main;
  v.dispatch({
    changes: { from, to, insert: szoveg },
    selection: { anchor: from + szoveg.length },
    userEvent: 'input.keplet-ocr',
    scrollIntoView: true,
  });
  return szoveg;
}

export async function kepletOcr(v: EditorView, keres = kerdez): Promise<boolean> {
  const kulcs = 'keplet-ocr';
  ertesitesek.ertesit({ kulcs, cim: t('Képlet olvasása a vágólapról…'), idotartam: 0 });
  try {
    const r = await keres<KepletOcrValasz>('/api/keplet-ocr', { metodus: 'POST', torzs: {}, idokorlat: 180_000 });
    kepletBeszur(v, r.latex);
    v.focus();
    ertesitesek.ertesit(
      r.proba
        ? { kulcs, szint: 'figyelmeztetes', proba: true, cim: t('Képlet beszúrva — próba-modellel'), szoveg: t('{modell}: nem kalibrált, ellenőrizd.', { modell: r.modell ?? '' }) }
        : { kulcs, szint: 'siker', cim: t('Képlet beszúrva'), szoveg: r.modell ? t('Olvasta: {modell}', { modell: r.modell }) : undefined },
    );
    return true;
  } catch (e) {
    const nincs = e instanceof ApiHiba && e.statusz === 404;
    ertesitesek.ertesit({
      kulcs,
      szint: nincs ? 'figyelmeztetes' : 'hiba',
      cim: nincs ? t('A vágólapon nincs kép') : t('A képlet nem olvasható'),
      szoveg: e instanceof Error ? e.message : String(e),
    });
    return false;
  }
}
