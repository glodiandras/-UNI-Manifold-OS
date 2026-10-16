// Linkeletlen említés → link, egy kattintással (C10). A másik jegyzet szerkesztése a `Dokumentum` úton megy
// (hash-alapú mentés, a nyitott szerkesztők élőben megkapják, ugyanaz a pillanatkép-szabály, mint a gépelésnél):
// nem új core-írás. A pozíció az indexből jön (a mentett szövegre); ha a sor közben megváltozott, nem írunk.

import { t as tx } from '../../lib/i18n';
import { ChangeSet } from '@codemirror/state';
import { ApiHiba } from '../../lib/core/api';
import { ertesitesek } from '../../lib/ertesites/ertesites.svelte';
import { fajlNev } from '../../lib/vault/fajlok.svelte';
import { linkek } from '../../lib/vault/linkek.svelte';
import type { Emlites } from '../../lib/vault/kapcsolatok.svelte';
import { szerkesztok } from '../szerkesztok.svelte';
import { emlitesLink } from '../asszisztens/javaslatSegedek';

/** A kódpont-szeletelés (a core kódpontban számol, a CodeMirror UTF-16-ban). */
const cp = (s: string, a: number, b?: number) => Array.from(s).slice(a, b).join('');

export { emlitesLink };

/** Az említés linkké alakítása a `forras` jegyzetben. Igaz, ha megtörtént; hibánál értesítés. */
export async function emlitesLinkel(celUt: string, forras: string, t: Emlites): Promise<boolean> {
  let dok;
  try {
    dok = await szerkesztok.dokumentumok.megnyit(forras);
  } catch (e) {
    ertesitesek.ertesit({ szint: 'hiba', cim: tx('A jegyzet nem nyitható meg'), szoveg: e instanceof ApiHiba ? e.message : String(e) });
    return false;
  }
  try {
    if (dok.csakOlvashato || dok.allapot === 'utkozes' || dok.allapot === 'eltunt') {
      ertesitesek.ertesit({ szint: 'figyelmeztetes', cim: tx('A jegyzet most nem írható'), szoveg: dok.csakOlvashato ?? forras });
      return false;
    }
    const szoveg = dok.szoveg;
    if (t.sor < 1 || t.sor > szoveg.lines) return elavult();
    const sor = szoveg.line(t.sor);
    if (cp(sor.text, 0, 400) !== t.szoveg) return elavult(); // a sor közben megváltozott
    const emlitett = cp(sor.text, t.oszlop, t.oszlop + t.hossz);
    if (!emlitett) return elavult();
    const cel = await linkek.linkCel(celUt, forras);
    if (dok.szoveg !== szoveg) return elavult(); // közben gépelt
    const kezd = sor.from + cp(sor.text, 0, t.oszlop).length;
    const cs = ChangeSet.of({ from: kezd, to: kezd + emlitett.length, insert: emlitesLink(cel, fajlNev(celUt), emlitett) }, szoveg.length);
    dok.valtozott(cs, cs.apply(szoveg), null, true); // nyitott szerkesztőnél az előzménybe kerül: a ⌘Z visszahozza (C29.7b)
    const eredmeny = await dok.ment();
    if (!eredmeny.ok) {
      ertesitesek.ertesit({ szint: 'hiba', cim: tx('A link nem mentődött'), szoveg: dok.hiba ?? forras });
      return false;
    }
    return true;
  } catch (e) {
    ertesitesek.ertesit({ szint: 'hiba', cim: tx('A link nem írható be'), szoveg: e instanceof Error ? e.message : String(e) });
    return false;
  } finally {
    await szerkesztok.dokumentumok.elenged(dok); // a nyitott szerkesztő-nézet tartja életben, különben lezár és kikerül
  }
}

function elavult(): false {
  ertesitesek.ertesit({ szint: 'figyelmeztetes', cim: tx('A jegyzet közben megváltozott'), szoveg: tx('A lista frissül, próbáld újra.'), idotartam: 4000 });
  return false;
}
