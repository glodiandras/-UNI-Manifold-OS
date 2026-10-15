// Az összefoglaló felületi állandói (C26b). A kísérőjegyzetek mappája a core `[osszefoglalas] mappa` (os.toml) tükre: a
// `tests/test_osszefoglalas_api.py` és az `app/tests/osszefoglalas.test.ts` őrzi az egyezést. A felület nem olvassa a konfigurációt.

export const OSSZEFOGLALO_MAPPA = 'ATTCHMNTS - summaries';

/** A vault-relatív út az összefoglaló-mappa alatti `.md`-e (a beágyazott jegyzet összefoglaló-e). */
export function osszefoglaloUt(ut: string | undefined | null): boolean {
  return !!ut && ut.normalize('NFC').startsWith(`${OSSZEFOGLALO_MAPPA}/`) && ut.toLowerCase().endsWith('.md');
}

/** Az átirat-alapú (videó, hang) összefoglalóhoz tartozó kiterjesztések (a core `atirat.MEDIA_KIT` tükre). */
const MEDIA_RE = /\.(mp4|m4v|mov|webm|mkv|ogv|mp3|m4a|wav|flac|ogg|opus|aac)$/i;

export function mediaUt(ut: string | undefined | null): boolean {
  return !!ut && MEDIA_RE.test(ut);
}

/** Az összefoglaló szintjének felirata. */
export const SZINT_NEV: Record<string, string> = {
  jegyzet: 'jegyzet',
  mappa: 'mappa',
  video: 'videó',
  kontextus: 'külső AI',
};
