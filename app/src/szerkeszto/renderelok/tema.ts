// A tényleges téma (a `<html data-tema>` rögzítése, különben a rendszer) és a tokenek kiszámolt színe a
// nem-CSS rajzolóknak (Mermaid). Témaváltáskor a feliratkozók újrarajzolnak.

export function sotetTema(): boolean {
  const t = document.documentElement.dataset.tema;
  if (t === 'sotet') return true;
  if (t === 'vilagos') return false;
  return typeof matchMedia === 'function' && matchMedia('(prefers-color-scheme: dark)').matches;
}

/** Egy szín-token értéke `#rrggbb` alakban (a `light-dark()` a jelenlegi témában feloldva). */
export function tokenSzin(token: string): string {
  const e = document.createElement('span');
  e.style.color = `var(${token})`;
  e.style.display = 'none';
  document.body.appendChild(e);
  const c = getComputedStyle(e).color;
  e.remove();
  const m = /rgba?\((\d+)[, ]+(\d+)[, ]+(\d+)/.exec(c);
  if (!m) return c;
  return '#' + [m[1], m[2], m[3]].map((x) => Number(x).toString(16).padStart(2, '0')).join('');
}

/** Feliratkozás a témaváltásra (a `data-tema` és a rendszer beállítása). Leiratkozót ad. */
export function temaFigyelo(f: () => void): () => void {
  const mo = new MutationObserver(f);
  mo.observe(document.documentElement, { attributes: true, attributeFilter: ['data-tema'] });
  const mq = typeof matchMedia === 'function' ? matchMedia('(prefers-color-scheme: dark)') : null;
  mq?.addEventListener('change', f);
  return () => {
    mo.disconnect();
    mq?.removeEventListener('change', f);
  };
}
