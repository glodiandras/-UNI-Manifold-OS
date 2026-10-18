// A canvas kijelölése (09-canvas-15): a JSON Canvas az azonosítót gyűjteményenként kéri egyedinek, ezért egy node és egy él
// osztozhat az id-n. A kijelölés kulcsa ezért gyűjtemény-előtagos (`n:` node, `e:` él); a DOM-attribútumok és a modell a
// nyers id-t használják, a kulcs csak a kijelölés halmazában él.

export const nKulcs = (id: string): string => `n:${id}`;
export const eKulcs = (id: string): string => `e:${id}`;

export interface KijeloltIdk {
  nodeok: Set<string>;
  elek: Set<string>;
}

/** A kijelölés kulcsaiból a node- és az él-azonosítók. */
export function kijeloltIdk(kijelolt: Iterable<string>): KijeloltIdk {
  const nodeok = new Set<string>();
  const elek = new Set<string>();
  for (const k of kijelolt) {
    if (k.startsWith('n:')) nodeok.add(k.slice(2));
    else if (k.startsWith('e:')) elek.add(k.slice(2));
  }
  return { nodeok, elek };
}
