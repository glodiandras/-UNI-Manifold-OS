// Melyik fül számít az aktív időbe (C29.7b, 38. döntés / T074): minden fájl-fül — jegyzet, PDF, videó, hang, canvas, base — a
// saját útján; a gráf nézet-fül (nincs fájlja) egy álkulcson. A „Ma”, a Statisztika és a Használat lap, valamint az üres „Új fül”
// nem számít (ott nincs mit tanulni/szerkeszteni). A core az `ut`-ot szabad szövegként fogadja (tantárgya: „Egyéb”).

import type { Ful } from '../elrendezes/munkaterulet.svelte';

/** A gráf nézet-fül kulcsa az aktív idő útjaként (nem vault-út: zárójeles, hogy ne ütközzön fájlnévvel). */
export const GRAF_KULCS = '(gráf)';

export function aktivUtKulcs(f: Pick<Ful, 'ut' | 'nezet'> | null): string | null {
  if (!f) return null;
  if (f.ut) return f.ut;
  return f.nezet?.tipus === 'graf' ? GRAF_KULCS : null;
}
