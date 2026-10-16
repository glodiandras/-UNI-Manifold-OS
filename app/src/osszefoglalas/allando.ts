// Az összefoglaló felületi állandói (C26b). A kísérőjegyzetek mappája a core `[osszefoglalas] mappa` (os.toml) szállított
// alapjának tükre (`core/kiserok.py`: `<kisero_elotag>Summaries`): a `tests/test_osszefoglalas_api.py` és az
// `app/tests/osszefoglalas.test.ts` őrzi az egyezést. A munkatér saját mappáit a core adja (`GET /api/vault/sema` → `kisero`,
// `kisero_elotag`): a kapcsolat felépülésekor a felület `beallitKiserok`-ot hívja (kártya, kvíz és összefoglaló együtt).
import { beallitKartyaMappa } from '../kartya/allando';
import { beallitKvizMappa } from '../kviz/allando';

export let OSSZEFOGLALO_MAPPA = 'Manifold - Summaries';
/** A gépi kísérőmappák közös névelőtagja (a core `[vault] kisero_elotag`): az ilyen mappák jegyzetei nem tartalmi jegyzetek. */
export let KISERO_ELOTAG = 'Manifold - ';

/** A `GET /api/vault/sema` `kisero` + `kisero_elotag` mezője: a munkatér mappái (hiányzó érték: marad az alap). */
export function beallitKiserok(
  mappak: { kartya?: string; kviz?: string; osszefoglalas?: string } | null | undefined,
  elotag?: string | null,
): void {
  if (elotag) KISERO_ELOTAG = elotag.normalize('NFC');
  if (mappak?.osszefoglalas) OSSZEFOGLALO_MAPPA = mappak.osszefoglalas.normalize('NFC');
  beallitKartyaMappa(mappak?.kartya);
  beallitKvizMappa(mappak?.kviz);
}

/** Kísérőmappa-e a vault-relatív út (egyik eleme a kísérő-előtaggal kezdődik). */
export function kiseroUt(ut: string | undefined | null): boolean {
  return !!ut && ut.normalize('NFC').split('/').some((r) => r.startsWith(KISERO_ELOTAG));
}

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
