// A kvíz felületi állandói (C22a). A kvízjegyzetek mappája a core `[kviz] mappa` (os.toml) szállított alapjának tükre
// (`core/kiserok.py`: `<kisero_elotag>Quizzes`): a `tests/test_kviz_api.py` őrzi az egyezést. A munkatér saját mappáját a core adja
// (`GET /api/vault/sema` → `kisero.kviz`; `beallitKiserok`, osszefoglalas/allando.ts); a core csak a mappa alatti jegyzetet
// szolgálja ki kvízként.

export let KVIZ_MAPPA = 'Manifold - Quizzes';

/** A munkatér kvízmappája (üres vagy hiányzó érték: marad az alap). */
export function beallitKvizMappa(mappa: string | null | undefined): void {
  if (mappa) KVIZ_MAPPA = mappa.normalize('NFC');
}

/** A vault-relatív út a kvízmappa alatti `.md`-e (a beágyazott jegyzet kvíz-e). */
export function kvizUt(ut: string | undefined | null): boolean {
  return !!ut && ut.normalize('NFC').startsWith(`${KVIZ_MAPPA}/`) && ut.toLowerCase().endsWith('.md');
}

export const BETUK = ['A', 'B', 'C', 'D'] as const;
