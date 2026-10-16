// Egy cella szerkesztése (C12b, 9. lépés): a sor jegyzetének frontmatterébe írás **a nyitott dokumentumon át**
// (egy írási út: hash-alapú ütközés, automatikus mentés, ⌘Z) — az `emlites.ts` és a tulajdonság-panel mintája.
// A core csak számol (`tulajdonsagok/modosit`): a séma-sértő érték nem íródik csendben („Mégis beírom”), a hiba
// szintű (érvénytelen érték, formai hibás frontmatter) megerősítéssel sem. Ha a mentés pillanatképet készített,
// az értesítés „Visszavonás” gombbal visszaadja a régi értéket (a `Mos-Forras: pult-szerkeszto` commit revertje).

import { ChangeSet } from '@codemirror/state';
import { ApiHiba, kerdez } from '../lib/core/api';
import { ertesitesek } from '../lib/ertesites/ertesites.svelte';
import type { Dokumentumok } from '../szerkeszto/dokumentum/dokumentum.svelte';
import { szerkesztok } from '../szerkeszto/szerkesztok.svelte';
import { tulajdonsagApi } from '../szerkeszto/tulajdonsagok/api';
import { blokkCsere, fmBlokk } from '../szerkeszto/tulajdonsagok/fm';
import type { SemaProblema, TulajdonsagApi, TulajdonsagTipus } from '../szerkeszto/tulajdonsagok/tipusok';
import { t } from '../lib/i18n';

export interface CellaOlvasat {
  /** a frontmatterben ténylegesen álló kulcs (kis-nagybetűben a fájl írása) */
  kulcs: string;
  van: boolean;
  tipus: TulajdonsagTipus | null;
  ertek: unknown;
}

export interface CellaEredmeny {
  ok: boolean;
  /** séma-sértés: csak „Mégis beírom”-mal írható */
  fuggo?: SemaProblema[];
  /** miért nem írható */
  elutasitva?: string;
  /** a mentés pillanatképének azonosítója (visszavonáshoz) */
  pillanat?: string | null;
}

export interface CellaOpciok {
  api?: TulajdonsagApi;
  dk?: Dokumentumok;
}

/** A cella nyers (frontmatter-beli) értéke: a szerkesztő ebből indul, nem a megjelenített cellából (a link
 *  álneve, a dátum formátuma, a lista elemei így sértetlenek). */
export async function cellaOlvas(ut: string, kulcs: string, o: CellaOpciok = {}): Promise<CellaOlvasat> {
  const dk = o.dk ?? szerkesztok.dokumentumok;
  const api = o.api ?? tulajdonsagApi();
  const dok = await dk.megnyit(ut);
  try {
    const e = await api.elemez(ut, fmBlokk(dok.szoveg)?.szoveg ?? null);
    const kis = kulcs.toLowerCase();
    const t = e.tulajdonsagok.find((x) => x.kulcs === kulcs) ?? e.tulajdonsagok.find((x) => x.kulcs.toLowerCase() === kis);
    return t ? { kulcs: t.kulcs, van: true, tipus: t.tipus, ertek: t.ertek } : { kulcs, van: false, tipus: null, ertek: null };
  } finally {
    await dk.elenged(dok);
  }
}

/** Egy tulajdonság beállítása (`ertek: undefined` → a kulcs törlése). */
export async function cellaIr(
  ut: string,
  kulcs: string,
  ertek: unknown,
  tipus: TulajdonsagTipus | undefined,
  megerosit = false,
  o: CellaOpciok = {},
): Promise<CellaEredmeny> {
  const dk = o.dk ?? szerkesztok.dokumentumok;
  const api = o.api ?? tulajdonsagApi();
  let dok;
  try {
    dok = await dk.megnyit(ut);
  } catch (e) {
    return { ok: false, elutasitva: e instanceof ApiHiba ? e.message : e instanceof Error ? e.message : String(e) };
  }
  try {
    if (dok.csakOlvashato) return { ok: false, elutasitva: dok.csakOlvashato };
    if (dok.allapot === 'utkozes') return { ok: false, elutasitva: t('A jegyzet közben megváltozott a lemezen; előbb az ütközést kell feloldani.') };
    if (dok.allapot === 'eltunt') return { ok: false, elutasitva: t('A jegyzet közben eltűnt (törölték vagy áthelyezték).') };
    const blokk = fmBlokk(dok.szoveg);
    const kuldott = blokk?.szoveg ?? null;
    const r = await api.modosit(
      ut,
      kuldott,
      ertek === undefined ? { muvelet: 'torol', kulcs } : { muvelet: 'beallit', kulcs, ertek, ...(tipus ? { tipus } : {}) },
      megerosit,
    );
    if ((fmBlokk(dok.szoveg)?.szoveg ?? null) !== kuldott) {
      return { ok: false, elutasitva: t('A jegyzet közben megváltozott; a nézet frissül, próbáld újra.') };
    }
    if (!r.ok) {
      if (r.megerositheto) return { ok: false, fuggo: r.problemak };
      return { ok: false, elutasitva: r.problemak[0]?.uzenet ?? t('A módosítás nem írható.') };
    }
    if (r.fm_uj !== null && r.valtozas) {
      const c = blokkCsere(blokk, r.fm_uj);
      if (c) {
        const cs = ChangeSet.of([c], dok.szoveg.length);
        // a nyitott szerkesztő előzményébe kerül: a ⌘Z visszahozza a régi értéket (T028)
        dok.valtozott(cs, cs.apply(dok.szoveg), null, true);
      }
    }
    // Ha a jegyzet máshol nincs nyitva, a mentés pillanatképet készít (visszavonható); a nyitott szerkesztőben a
    // változás a szerkesztés része (⌘Z), pillanatkép a szerkesztés lezárásakor lesz.
    const egyedul = dok.nezetSzam === 0;
    const m = await dok.ment(egyedul ? { pillanat: true } : {});
    if (!m.ok) return { ok: false, elutasitva: dok.hiba ?? t('A mentés nem sikerült; a változás nem került a fájlba.') };
    return { ok: true, pillanat: m.pillanat ?? null };
  } catch (e) {
    return { ok: false, elutasitva: e instanceof ApiHiba ? e.message : e instanceof Error ? e.message : String(e) };
  } finally {
    await dk.elenged(dok);
  }
}

/** A pillanatkép visszavonása (`POST /api/pillanat/vault/visszavonas`). */
export function pillanatVisszavon(sha: string): Promise<{ ok: boolean; sha: string }> {
  return kerdez('/api/pillanat/vault/visszavonas', { metodus: 'POST', torzs: { sha }, idokorlat: 20000 });
}

/** Értesítés a mentett cellaváltozásról, „Visszavonás” gombbal (ha van pillanatkép). */
export function cellaErtesites(nev: string, kulcs: string, pillanat: string | null | undefined, utana?: () => void): void {
  if (!pillanat) return;
  ertesitesek.ertesit({
    szint: 'info',
    cim: t('{kulcs} módosítva', { kulcs }),
    szoveg: nev,
    idotartam: 6000,
    muvelet: {
      nev: t('Visszavonás'),
      futtat: () => {
        pillanatVisszavon(pillanat).then(
          () => {
            ertesitesek.ertesit({ szint: 'siker', cim: t('Visszavonva'), szoveg: `${nev} · ${kulcs}`, idotartam: 3000 });
            utana?.();
          },
          (e) =>
            ertesitesek.ertesit({
              szint: 'hiba',
              cim: t('A visszavonás nem sikerült'),
              szoveg: e instanceof Error ? e.message : String(e),
            }),
        );
      },
    },
  });
}
