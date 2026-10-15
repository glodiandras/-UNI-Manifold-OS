// A Notion-réteg bővítményei a Live Preview-hoz (C09): `/` menü, blokkfogó, lebegő eszköztár, a táblázat
// billentyűi és a mellette gépelt szöveg leválasztása (C10.7). A táblázat vizuális szerkesztője a
// blokkdíszítésekben (`elo/blokkok.ts`) áll a táblázat helyén.
// A fájlformátum nem változik: mindegyik közönséges Markdownt ír.

import type { Extension } from '@codemirror/state';
import { blokkfogoBovitmeny, linkNevForras } from './blokkfogo';
import { eszkoztarBovitmeny } from './eszkoztar';
import { perjelBovitmeny } from './perjel';
import { tablaBillentyuk, tablaVedo } from './tablazat/szerkeszto';

export { linkNevForras };

export function notionBovitmenyek(): Extension {
  return [perjelBovitmeny(), blokkfogoBovitmeny(), eszkoztarBovitmeny(), tablaBillentyuk, tablaVedo];
}
