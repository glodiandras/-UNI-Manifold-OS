// Link megnyitása (C10): a cél feloldását a core végzi (`linkek.beagyazas`), itt csak a navigáció van: a fájl
// megnyitása az aktív fülben / új fülben (⌘) / osztásban (⌘⌥), fejezetre vagy blokkra ugrás, és — Obsidian-módra —
// a feloldatlan linkre kattintva új jegyzet; a helyét a core dönti (C31, T158: `POST /api/vault/uj {link}`).

import { t } from '../../lib/i18n';
import { ApiHiba, kerdez } from '../../lib/core/api';
import { ertesitesek } from '../../lib/ertesites/ertesites.svelte';
import { linkek } from '../../lib/vault/linkek.svelte';
import { fajlNev } from '../../lib/vault/fajlok.svelte';
import { szerkesztok } from '../szerkesztok.svelte';
import { mediaHorgony } from './adat';

export type NyitasMod = 'aktiv' | 'ujful' | 'osztas';

export interface NavFuggoseg {
  /** a fájl megnyitása; a `horgony` a média-horgony (`page=3`, `t=12`) a nézetnek (C16) */
  megnyit(ut: string, mod: NyitasMod, horgony?: string | null): void;
  /** a vault mappái (a C31 óta a felület nem használja: az új jegyzet helyét a core dönti) */
  mappak?(): string[];
}

/** Nem jegyzet: ilyen célhoz nem hozunk létre új jegyzetet (v1.2 vagy „Dr. Kovács” viszont jegyzetnév). */
export const ISMERT_KITERJESZTES = /\.(png|jpe?g|gif|webp|avif|svg|heic|bmp|tiff?|mp4|m4v|mov|webm|mkv|ogv|mp3|m4a|wav|flac|ogg|opus|aac|pdf|canvas|base|txt|csv|json)$/i;

let fugg: NavFuggoseg | null = null;

export function navigacioBeallit(f: NavFuggoseg | null): void {
  fugg = f;
}

/** Az egér-/billentyű-módosítókból a megnyitás módja: ⌘ (vagy ⌃) új fül, ⌘⌥ osztás. */
export function nyitasMod(e: { metaKey: boolean; ctrlKey: boolean; altKey: boolean }): NyitasMod {
  if ((e.metaKey || e.ctrlKey) && e.altKey) return 'osztas';
  if (e.metaKey || e.ctrlKey) return 'ujful';
  return 'aktiv';
}

export interface LinkCel {
  /** a linket tartalmazó jegyzet útja */
  forras: string;
  /** a nyers cél; üres: ugyanaz a jegyzet (`[[#Fejezet]]`) */
  cel: string;
  alcel?: string | null;
}

/** Új jegyzet a feloldatlan linkhez. A helyet a core dönti az Obsidian szabálya szerint (C31, T158): az útvonalas cél
 *  a vault gyökeréhez képest (a mappa kis-nagybetűtől függetlenül egyezik, a hiányzó létrejön), az út nélküli a vault
 *  `newFileLocation` beállítása szerint. Az új út, vagy `null` (a hiba értesítésként megjelent). */
export async function jegyzetLetrehoz(forras: string, cel: string): Promise<string | null> {
  const tiszta = cel.trim().replaceAll('\\', '/').replace(/^\/+/, '');
  const nev = tiszta.slice(tiszta.lastIndexOf('/') + 1).replace(/\.md$/i, '');
  if (!nev || ISMERT_KITERJESZTES.test(tiszta)) {
    ertesitesek.ertesit({ szint: 'figyelmeztetes', cim: t('A fájl nem található'), szoveg: cel });
    return null;
  }
  // C36a-UI: a hiányzó `![[x.cpp]]` célja C++ forrás (a core váza), nem `x.cpp.md` — a felhasználó művelete (53(d));
  // C31 (T158): a helyet mindkét esetben a core dönti a nyers link-célból
  const cpp = /\.cpp$/i.test(nev);
  try {
    const torzs = cpp ? { link: { cel, forras }, tipus: 'cpp' } : { link: { cel, forras } };
    const d = await kerdez<{ ut: string }>('/api/vault/uj', { metodus: 'POST', torzs, idokorlat: 10000 });
    linkek.ervenytelenit();
    return d.ut;
  } catch (e) {
    ertesitesek.ertesit({ szint: 'hiba', cim: t('Az új jegyzet nem hozható létre'), szoveg: e instanceof ApiHiba ? e.message : String(e) });
    return null;
  }
}

/** A link megnyitása. */
export async function linkMegnyit(l: LinkCel, mod: NyitasMod = 'aktiv'): Promise<void> {
  if (!fugg) return;
  const cel = l.cel.trim() || l.forras;
  let b;
  try {
    b = await linkek.beagyazas(l.forras, cel, l.alcel);
  } catch (e) {
    ertesitesek.ertesit({ szint: 'hiba', cim: t('A link nem oldható fel'), szoveg: e instanceof ApiHiba ? e.message : String(e) });
    return;
  }
  let ut = b.ut ?? null;
  if (b.tipus === 'nincs' || !ut) {
    ut = await jegyzetLetrehoz(l.forras, l.cel);
    if (!ut) return;
    fugg.megnyit(ut, mod);
    return;
  }
  const media = b.tipus === 'pdf' || b.tipus === 'video' || b.tipus === 'hang';
  const horgony = media && Object.keys(mediaHorgony(l.alcel)).length ? l.alcel! : null;
  if (ut === l.forras && mod === 'aktiv') {
    if (b.kezd && !b.alcel_hiba) szerkesztok.ugras(ut, b.kezd);
    return;
  }
  fugg.megnyit(ut, mod, horgony);
  if (b.tipus === 'jegyzet' && b.kezd && l.alcel && !b.alcel_hiba) szerkesztok.ugras(ut, b.kezd);
  else if (b.tipus === 'jegyzet' && l.alcel && b.alcel_hiba)
    ertesitesek.ertesit({ szint: 'figyelmeztetes', cim: t('A horgony nem található'), szoveg: `${fajlNev(ut)}#${l.alcel}` });
}
