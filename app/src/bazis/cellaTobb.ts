// Több tulajdonság egy jegyzetben, egyetlen mentéssel (10-bases-07 előtöltés, 10-bases-12 beillesztés / törlés). A `cellaIr` mintája,
// de a műveletek láncolva számolnak (a core `modosit` mindig az előző `fm_uj`-ból indul), a nyitott dokumentumba EGY csere kerül, és
// EGY mentés (pillanatkép) készül jegyzetenként. Séma-sértésnél a jegyzetbe semmi nem íródik: a sértések visszajönnek, és csak a
// megerősítés („Mégis beírom”) után megy újra `megerosit: true`-val; a hiba szintű elutasítás megerősítéssel sem íródik.
// A jegyzetet MINDIG a meglévő biztonságos tulajdonság-műveleten át írjuk (nyitott `Dokumentum`: CAS, mentés, ⌘Z).

import { ChangeSet } from '@codemirror/state';
import { ApiHiba } from '../lib/core/api';
import { t } from '../lib/i18n';
import type { Dokumentumok } from '../szerkeszto/dokumentum/dokumentum.svelte';
import { szerkesztok } from '../szerkeszto/szerkesztok.svelte';
import { tulajdonsagApi } from '../szerkeszto/tulajdonsagok/api';
import { blokkCsere, fmBlokk } from '../szerkeszto/tulajdonsagok/fm';
import type { SemaProblema, TulajdonsagApi, TulajdonsagTipus } from '../szerkeszto/tulajdonsagok/tipusok';
import type { CellaOpciok } from './cellaIr';

export interface TulajdonsagMuvelet {
  kulcs: string;
  /** `undefined`: a kulcs törlése */
  ertek: unknown;
  tipus?: TulajdonsagTipus;
}

export interface TobbEredmeny {
  /** a jegyzet írva van (vagy nem volt változás) */
  ok: boolean;
  /** az írt (ténylegesen megváltozott) műveletek kulcsai */
  irva: string[];
  /** séma-sértés miatt nem írt kulcsok: csak „Mégis beírom”-mal írhatók (a jegyzetbe ilyenkor semmi nem került) */
  fuggo?: SemaProblema[];
  /** a végleg elutasított kulcsok (hiba szintű) és az indokuk; a többi kulcs íródik */
  elutasitva: Array<{ kulcs: string; uzenet: string }>;
  /** az egész jegyzet nem írható (csak olvasható, ütközés, mentési hiba) */
  tiltva?: string;
  pillanat?: string | null;
}

const uzenet = (e: unknown) => (e instanceof ApiHiba ? e.message : e instanceof Error ? e.message : String(e));

/** A műveletek alkalmazása a jegyzet frontmatterén, egyetlen cserével és mentéssel. */
export async function tulajdonsagokIr(
  ut: string,
  muveletek: TulajdonsagMuvelet[],
  megerosit = false,
  o: CellaOpciok = {},
): Promise<TobbEredmeny> {
  const dk: Dokumentumok = o.dk ?? szerkesztok.dokumentumok;
  const api: TulajdonsagApi = o.api ?? tulajdonsagApi();
  const tilt = (szoveg: string): TobbEredmeny => ({ ok: false, irva: [], elutasitva: [], tiltva: szoveg });
  let dok;
  try {
    dok = await dk.megnyit(ut);
  } catch (e) {
    return tilt(uzenet(e));
  }
  try {
    if (dok.csakOlvashato) return tilt(dok.csakOlvashato);
    if (dok.allapot === 'utkozes') return tilt(t('A jegyzet közben megváltozott a lemezen; előbb az ütközést kell feloldani.'));
    if (dok.allapot === 'eltunt') return tilt(t('A jegyzet közben eltűnt (törölték vagy áthelyezték).'));
    const blokk = fmBlokk(dok.szoveg);
    const kuldott = blokk?.szoveg ?? null;
    let fm = kuldott;
    const irva: string[] = [];
    const fuggo: SemaProblema[] = [];
    const elutasitva: Array<{ kulcs: string; uzenet: string }> = [];
    for (const m of muveletek) {
      const r = await api.modosit(
        ut,
        fm,
        m.ertek === undefined ? { muvelet: 'torol', kulcs: m.kulcs } : { muvelet: 'beallit', kulcs: m.kulcs, ertek: m.ertek, ...(m.tipus ? { tipus: m.tipus } : {}) },
        megerosit,
      );
      if (!r.ok) {
        if (r.megerositheto) fuggo.push(...r.problemak);
        else elutasitva.push({ kulcs: m.kulcs, uzenet: r.problemak[0]?.uzenet ?? t('A módosítás nem írható.') });
        continue;
      }
      if (r.fm_uj !== null && r.valtozas) {
        fm = r.fm_uj;
        irva.push(m.kulcs);
      }
    }
    if ((fmBlokk(dok.szoveg)?.szoveg ?? null) !== kuldott) {
      return tilt(t('A jegyzet közben megváltozott; a nézet frissül, próbáld újra.'));
    }
    // séma-sértés: a jegyzetbe semmi nem kerül, amíg a felhasználó nem erősít meg (egy kérdés jegyzetenként)
    if (fuggo.length) return { ok: false, irva: [], fuggo, elutasitva };
    if (!irva.length || fm === null) return { ok: true, irva: [], elutasitva };
    const c = blokkCsere(blokk, fm);
    if (c) {
      const cs = ChangeSet.of([c], dok.szoveg.length);
      dok.valtozott(cs, cs.apply(dok.szoveg), null, true); // a nyitott szerkesztő előzményébe: a ⌘Z egy lépésben visszahozza
    }
    // ha a jegyzet máshol nincs nyitva, a mentés pillanatképet készít (visszavonható); különben a szerkesztés része (⌘Z)
    const m = await dok.ment(dok.nezetSzam === 0 ? { pillanat: true } : {});
    if (!m.ok) return tilt(dok.hiba ?? t('A mentés nem sikerült; a változás nem került a fájlba.'));
    return { ok: true, irva, elutasitva, pillanat: m.pillanat ?? null };
  } catch (e) {
    return tilt(uzenet(e));
  } finally {
    await dk.elenged(dok);
  }
}
