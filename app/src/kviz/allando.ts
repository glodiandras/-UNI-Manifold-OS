// A kvíz felületi állandói (C22a). A kvízjegyzetek mappája a core `[kviz] mappa` (os.toml) tükre: a `tests/test_kviz_api.py`
// őrzi az egyezést. A felület nem olvassa a konfigurációt; a core csak a mappa alatti jegyzetet szolgálja ki kvízként.

// mirror of config — F3 replaces with /api/workspace
export const KVIZ_MAPPA = 'ATTCHMNTS - quizes';

/** A vault-relatív út a kvízmappa alatti `.md`-e (a beágyazott jegyzet kvíz-e). */
export function kvizUt(ut: string | undefined | null): boolean {
  return !!ut && ut.normalize('NFC').startsWith(`${KVIZ_MAPPA}/`) && ut.toLowerCase().endsWith('.md');
}

export const BETUK = ['A', 'B', 'C', 'D'] as const;
