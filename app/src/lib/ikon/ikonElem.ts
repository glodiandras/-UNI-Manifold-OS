// Lucide-ikon DOM-elemként, a Svelte-komponensen kívüli helyekre (a szerkesztő widgetjei, az olvasó). Ugyanaz
// a rajzolat, mint az `Ikon.svelte`-é: díszítő (aria-hidden), 1,75-ös vonal (20 px-nél 1,6).

import type { IconNode } from 'lucide';

const SVG = 'http://www.w3.org/2000/svg';

export function ikonElem(ikon: IconNode, meret: 14 | 16 | 20 = 16): SVGSVGElement {
  const svg = document.createElementNS(SVG, 'svg');
  for (const [k, v] of Object.entries({
    class: 'ikon',
    width: meret,
    height: meret,
    viewBox: '0 0 24 24',
    fill: 'none',
    stroke: 'currentColor',
    'stroke-width': meret === 20 ? 1.6 : 1.75,
    'stroke-linecap': 'round',
    'stroke-linejoin': 'round',
    'aria-hidden': 'true',
    focusable: 'false',
  }))
    svg.setAttribute(k, String(v));
  for (const [tag, attrs] of ikon) {
    const e = document.createElementNS(SVG, tag);
    for (const [k, v] of Object.entries(attrs)) if (v !== undefined) e.setAttribute(k, String(v));
    svg.appendChild(e);
  }
  return svg;
}
