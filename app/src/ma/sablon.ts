// A „Sablon beszúrása” (C15): a core által kiértékelt sablon beillesztése a nyitott jegyzetbe. A kiértékelés a core-é
// (`POST /api/sablon/kiertekel`, egyetlen hely); itt csak az elhelyezés van: a szöveg a kurzornál, a kurzor a
// `{{cursor}}` helyén, és a frontmatter kezelése — a jegyzet tulajdonságai nem sérülhetnek:
//   - a sablonnak nincs frontmatterje: a szöveg a kijelölés helyére kerül;
//   - a sablonnak van, a jegyzetnek nincs: a tulajdonságok a jegyzet elejére kerülnek, a törzs a kurzornál;
//   - mindkettőnek van (C32b): a core összefésüli (`/api/vault/tulajdonsagok/osszefesul`: új kulcs hozzáadódik, a lista
//     egyesül, a meglévő érték nem íródik felül, a séma-sértő kulcs megerősítésre vár), a blokk cseréje a törzs
//     beszúrásával egy tranzakció; összefésülés nélkül (régi core, hiba) a sablon tulajdonságai kimaradnak.
// Az egész egy tranzakció, így a ⌘Z egy lépésben visszavon.

import type { ChangeSpec } from '@codemirror/state';
import { blokkCsere, fmBlokk } from '../szerkeszto/tulajdonsagok/fm';
import type { OsszefesulesEredmeny } from '../szerkeszto/tulajdonsagok/tipusok';
import type { SablonKimenet } from './tipusok';

// A frontmatter-határ a felület EGYETLEN illesztésével (`tulajdonsagok/fm.ts` `fmBlokk`, a core `FM_RE`-jének alakja, L39;
// C31, 2. audit T159): a sablon-beszúrás korábban saját, szigorúbb mintát használt (a záró `---` után sorvéget kért).

export interface BeszurasTerv {
  changes: ChangeSpec[];
  /** a kurzor helye a csere utáni dokumentumban */
  anchor: number;
  /** a sablon tulajdonságai kimaradtak, mert a jegyzetnek már van frontmatterje (és nem volt összefésülés) */
  frontmatterKihagyva: boolean;
}

export function frontmatterVan(szoveg: string): boolean {
  return fmBlokk(szoveg) !== null;
}

/** A beszúrás terve: `doc` a jegyzet szövege, `from`–`to` a kijelölés (a beszúrás helye); `osszefesules` a core eredménye
 *  (csak akkor kell, ha a sablonnak és a jegyzetnek is van frontmatterje). */
export function beszurasTerv(
  doc: string,
  from: number,
  to: number,
  k: SablonKimenet,
  osszefesules: Pick<OsszefesulesEredmeny, 'fm_uj' | 'valtozas'> | null = null,
): BeszurasTerv {
  let szoveg = k.szoveg;
  let kurzor = k.kurzor;
  let fm = '';
  let kihagyva = false;
  const changes: ChangeSpec[] = [];
  let eltolas = 0; // a törzs elé kerülő változtatások nettó hossza (a kurzorhoz)
  const m = k.frontmatter ? fmBlokk(szoveg) : null;
  if (m) {
    szoveg = szoveg.slice(m.ig);
    kurzor = kurzor === null || kurzor < m.ig ? null : kurzor - m.ig;
    const jegyzetFm = fmBlokk(doc);
    if (jegyzetFm) {
      // a törzs soha nem a jegyzet frontmatterébe kerül
      if (from < jegyzetFm.ig) {
        from = jegyzetFm.ig;
        to = Math.max(to, from);
      }
      if (osszefesules) {
        const c = osszefesules.valtozas && osszefesules.fm_uj !== null ? blokkCsere(jegyzetFm, osszefesules.fm_uj) : null;
        if (c) {
          changes.push(c);
          eltolas = c.insert.length - (c.to - c.from);
        }
      } else kihagyva = true;
    } else fm = m.szoveg.endsWith('\n') ? m.szoveg : m.szoveg + '\n';
  }
  if (fm) changes.push({ from: 0, insert: fm });
  changes.push({ from, to, insert: szoveg });
  const hely = from + (kurzor ?? szoveg.length);
  // a jegyzet elejére szúrt tulajdonságok az egész törzset (és a kurzort) eltolják az előttük álló hosszal
  return { changes, anchor: hely + fm.length + eltolas, frontmatterKihagyva: kihagyva };
}
