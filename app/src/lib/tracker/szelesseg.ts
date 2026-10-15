// A grafikon tartályának szélessége (C27): a rajz 1:1 méretű, hogy a szöveg ne kicsinyedjen keskeny panelben.
// `ResizeObserver` nélkül (tesztkörnyezet) a rajz az alap szélességgel készül.

export function szelessegFigyel(node: HTMLElement, f: (szel: number) => void): { destroy(): void } {
  f(node.clientWidth);
  if (typeof ResizeObserver === 'undefined') return { destroy() {} };
  const figyelo = new ResizeObserver((bejegyzesek) => {
    for (const b of bejegyzesek) f(Math.round(b.contentRect.width));
  });
  figyelo.observe(node);
  return { destroy: () => figyelo.disconnect() };
}
