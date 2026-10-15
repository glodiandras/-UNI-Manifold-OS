// A beágyazott kép nagyítása (C11a, audit M9): a jegyzetben a kép a megjelenített szélességnek megfelelő, kicsinyített
// változat (`/media/…?w=N`); az **eredetit** csak kattintásra töltjük be, ebben a nézegetőben. Bezáráskor az elem
// eltűnik, így a nagy bitmap memóriája felszabadul. Egy modális réteg: Esc és a háttérre kattintás zár, a fókusz
// a bezáró gombra kerül (csapda: az egyetlen fókuszálható elem), és bezáráskor a kiindulóra tér vissza.

import { ikonElem } from '../../lib/ikon/ikonElem';
import { X } from '../../lib/ikon/ikonok';

/** A megjelenített szélességhez (CSS px × képpontsűrűség) tartozó vödör — a core vödreivel egyezik (`core/kepek.py`). */
export const KEP_VODROK = [400, 800, 1600] as const;

export function kepVodor(cssPx: number, dpr = 1): number {
  const px = Math.ceil(cssPx * (dpr > 0 ? dpr : 1));
  return KEP_VODROK.find((v) => v >= px) ?? KEP_VODROK[KEP_VODROK.length - 1];
}

let nyitott: (() => void) | null = null;

/** Megnyitja a nézegetőt az eredeti képpel; → a bezáró függvény. Egyszerre egy nézegető van. */
export function kepetNagyit(src: string, nev: string, kiindulo?: HTMLElement | null): () => void {
  nyitott?.();
  const fedo = document.createElement('div');
  fedo.className = 'nagyito';
  fedo.setAttribute('role', 'dialog');
  fedo.setAttribute('aria-modal', 'true');
  fedo.setAttribute('aria-label', `Kép: ${nev}`);
  const img = document.createElement('img');
  img.className = 'nagyito-kep';
  img.alt = nev;
  img.decoding = 'async';
  img.src = src;
  const bezar = document.createElement('button');
  bezar.type = 'button';
  bezar.className = 'nagyito-bezar';
  bezar.setAttribute('aria-label', 'Bezárás');
  bezar.title = 'Bezárás (Esc)';
  bezar.appendChild(ikonElem(X, 20));
  fedo.append(img, bezar);

  const zar = () => {
    if (!fedo.isConnected && nyitott !== zar) return;
    window.removeEventListener('keydown', billentyu, true);
    fedo.remove();
    if (nyitott === zar) nyitott = null;
    kiindulo?.focus?.({ preventScroll: true });
  };
  const billentyu = (e: KeyboardEvent) => {
    if (e.key === 'Escape') {
      e.preventDefault();
      e.stopPropagation();
      zar();
    } else if (e.key === 'Tab') {
      e.preventDefault();
      bezar.focus();
    }
  };
  fedo.addEventListener('click', (e) => {
    if (e.target !== img) zar(); // a háttér és a gomb zár; a képre kattintás nem
  });
  window.addEventListener('keydown', billentyu, true);
  document.body.appendChild(fedo);
  bezar.focus({ preventScroll: true });
  nyitott = zar;
  return zar;
}
