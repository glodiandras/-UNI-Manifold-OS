// Új jegyzet a Bases-nézetből (10-bases-07 és -14): a „New” gomb és a Kanban-oszlop „+”-ja. A létrehozás a meglévő biztonságos úton megy
// (`POST /api/vault/uj`: kizárólagos létrehozás, meglévő fájlt NEM ír felül — ütközésnél hiba, a név megmarad az újrapróbához), az
// előtöltött tulajdonságok pedig utána, a meglévő tulajdonság-műveleten át (nyitott dokumentum: séma-ellenőrzés, mentés, ⌘Z). Előtöltés
// csak ott van, ahol egyértelmű: a core a szűrőkből adja (`fajl.elotoltes`), az oszlop értéke a csoportosító tulajdonságot felülírja.

import { ApiHiba, kerdez } from '../lib/core/api';
import { t } from '../lib/i18n';
import { tulajdonsagokIr, type TulajdonsagMuvelet } from './cellaTobb';
import { iroTipus } from './cellaErtek';
import { csoport } from './muveletek';
import { tulajdonsagId } from './azonosito';
import type { Ertek, Valasz } from './tipusok';

export interface UjAdat {
  /** a szűrők által megadott mappa, vagy `null` (az alapértelmezett mappa jár) */
  mappa: string | null;
  tulajdonsagok: TulajdonsagMuvelet[];
  /** a kulcsok, amelyeket az ellentmondó szűrők miatt nem töltünk elő */
  nemEgyertelmu: string[];
}

const skalar = (e: Ertek): string | number | boolean | undefined =>
  typeof e === 'string' || typeof e === 'number' || typeof e === 'boolean' ? e : undefined;

/** A címke-tulajdonság kulcsa: a vaultban már szereplő írásmód (`Tags` / `tags`), különben `tags`. */
function cimkeKulcs(v: Valasz): string {
  return v.fajl?.elerheto.find((e) => e.ter === 'note' && e.tipus === 'tags' && e.id.toLowerCase() === 'tags')?.id ?? 'tags';
}

/** Az új jegyzet adatai: a szűrők előtöltése (`fajl.elotoltes`); `oszlop`: a Kanban-oszlop (vagy más csoport) értéke, amely a csoportosító
 *  note-tulajdonságot felülírja (üres érték: a tulajdonság nincs előtöltve). */
export function ujAdat(v: Valasz, oszlop?: { ertek: Ertek }): UjAdat {
  const e = v.fajl?.elotoltes;
  const ki = new Map<string, TulajdonsagMuvelet>();
  for (const x of e?.tulajdonsagok ?? []) ki.set(x.kulcs, { kulcs: x.kulcs, ertek: x.ertek, tipus: iroTipus(x.tipus) });
  if (e?.cimkek.length) {
    const k = cimkeKulcs(v);
    ki.set(k, { kulcs: k, ertek: e.cimkek, tipus: 'tags' });
  }
  const cs = csoport(v);
  if (oszlop && cs) {
    const { ter, nev } = tulajdonsagId(cs.property);
    if (ter === 'note') {
      const s = skalar(oszlop.ertek);
      if (s === undefined || s === '') ki.delete(nev);
      else ki.set(nev, { kulcs: nev, ertek: s, tipus: iroTipus(typeof s === 'number' ? 'number' : typeof s === 'boolean' ? 'checkbox' : 'text') });
    }
  }
  return { mappa: e?.mappa ?? null, tulajdonsagok: [...ki.values()], nemEgyertelmu: (e?.nem_egyertelmu ?? []).filter((k) => !(oszlop && cs && k === cs.property.replace(/^note\./, ''))) };
}

/** Az alapértelmezett mappa a „Fájlok → új jegyzet helye” beállításból: `.` = a nézetet tartalmazó fájl mappája. */
export function alapMappa(beallitasMappa: string, forrasUt: string | null): string {
  if (beallitasMappa === '.') return forrasUt && forrasUt.includes('/') ? forrasUt.slice(0, forrasUt.lastIndexOf('/')) : '';
  return beallitasMappa.replace(/^\/+|\/+$/g, '');
}

export interface UjEredmeny {
  ok: boolean;
  ut?: string;
  /** a létrehozás hibája (a név megmarad az újrapróbához) */
  hiba?: string;
  /** a jegyzet létrejött, de egy-egy előtöltött tulajdonság nem íródott (séma, hiba) */
  figyelmeztetesek: string[];
  /** a tulajdonságok mentésének pillanatképe (visszavonáshoz) */
  pillanat?: string | null;
}

/** Új jegyzet létrehozása: a név a core szabályai szerint érvényesül (érvénytelen név, ütközés → hiba, semmi nem íródik felül). */
export async function ujJegyzetLetrehoz(nev: string, mappa: string, adat: UjAdat): Promise<UjEredmeny> {
  const tiszta = nev.trim();
  if (!tiszta) return { ok: false, hiba: t('Adj nevet a jegyzetnek.'), figyelmeztetesek: [] };
  let ut: string;
  try {
    ut = (await kerdez<{ ut: string }>('/api/vault/uj', { metodus: 'POST', torzs: { mappa, nev: tiszta }, idokorlat: 10000 })).ut;
  } catch (e) {
    return { ok: false, hiba: e instanceof ApiHiba ? e.message : e instanceof Error ? e.message : String(e), figyelmeztetesek: [] };
  }
  const figy: string[] = [];
  let pillanat: string | null | undefined;
  if (adat.tulajdonsagok.length) {
    const r = await tulajdonsagokIr(ut, adat.tulajdonsagok);
    if (r.tiltva) figy.push(t('Az előtöltött tulajdonságok nem íródtak be: {ok}', { ok: r.tiltva }));
    else {
      if (r.fuggo?.length) figy.push(t('Az előtöltött tulajdonságok nem íródtak be: {ok}', { ok: r.fuggo[0].uzenet }));
      for (const x of r.elutasitva) figy.push(t('{kulcs}: {ok}', { kulcs: x.kulcs, ok: x.uzenet }));
      pillanat = r.pillanat;
    }
  }
  return { ok: true, ut, figyelmeztetesek: figy, pillanat };
}
