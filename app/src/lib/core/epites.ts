// A futó lap build-azonosítója: a build a `<meta name="manifold-epites">` címkébe írja (`vite.config.ts`, ugyanaz az érték, mint
// a `dist/epites.json`-é). A lap betöltésekor rögzül: az utólag kicserélt dist nem módosítja a már futó lapét.

/** A futó felület build-azonosítója (a forrás ujjlenyomata a build idején); fejlesztői szerveren és tesztben üres. */
export function futoFelulet(): string {
  return document.querySelector<HTMLMetaElement>('meta[name="manifold-epites"]')?.content ?? '';
}

export function futoEpitesLekerdezes(): string {
  const h = (window as unknown as { __manifoldHejEpites?: { hej?: string } }).__manifoldHejEpites;
  return new URLSearchParams({ futo: '1', felulet: futoFelulet(), hej: h?.hej ?? '' }).toString();
}

export interface EpitesResz {
  resz: string;
  friss: boolean;
  /** az azonosító első 12 jele; a még számolt (háttérben hash-elt) résznél üres vagy hiányzik */
  azonosito?: string | null;
}

export interface EpitesAllapotValasz {
  ok: boolean;
  /** a mag (core) forrás-ujjlenyomata; amíg a core a háttérben számolja: hiányzik vagy `null` */
  mag?: string | null;
  reszek: EpitesResz[];
}

/**
 * A lemezen álló dist újabb buildből való, mint a futó lap (újrafordítás futó app mellett): a lap lusta chunkjai (Mermaid,
 * JSXGraph, pdf.js) már nincsenek meg, újratöltés kell. Csak ha mindkét azonosító ismert.
 */
export function feluletUjabbAdiszken(a: EpitesAllapotValasz | null, futo = futoFelulet()): boolean {
  const dist = a?.reszek.find((r) => r.resz === 'felulet')?.azonosito;
  return !!futo && !!dist && !futo.startsWith(dist);
}
