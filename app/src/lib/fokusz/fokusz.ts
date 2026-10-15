// Fókuszkezelés: csapda a modális rétegben (a megnyitó elem visszakapja a fókuszt), F6-os régióváltás, és a
// fókusz visszaadása, amikor a héj ablaka visszajön (rejtés, appváltás; C10.7).

const FOKUSZALHATO =
  'a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), ' +
  '[tabindex]:not([tabindex="-1"]), [contenteditable="true"]';

function lathato(el: HTMLElement): boolean {
  if (el.closest('[inert], [hidden]')) return false;
  // elrendezés nélküli környezetben (jsdom) nincs mit mérni
  return el.getClientRects().length > 0 || document.documentElement.getClientRects().length === 0;
}

export function fokuszalhatok(gyoker: HTMLElement): HTMLElement[] {
  return [...gyoker.querySelectorAll<HTMLElement>(FOKUSZALHATO)].filter(lathato);
}

/** Az épp fókuszált elem (a megnyitó) — a komponens inicializálásakor kell elkérni, a gyermekek
 *  autofókusza előtt. */
export function fokuszban(): HTMLElement | null {
  return document.activeElement instanceof HTMLElement && document.activeElement !== document.body
    ? document.activeElement
    : null;
}

/** Svelte-akció: a Tab a csomóponton belül marad; megszűnéskor a fókusz visszatér a megnyitóra. */
export function csapda(node: HTMLElement, megnyito: HTMLElement | null = null) {
  const elozo = megnyito;
  const kezel = (e: KeyboardEvent) => {
    if (e.key !== 'Tab') return;
    const f = fokuszalhatok(node);
    if (!f.length) {
      e.preventDefault();
      return;
    }
    const elso = f[0];
    const utolso = f[f.length - 1];
    const akt = document.activeElement;
    if (e.shiftKey && (akt === elso || !node.contains(akt))) {
      e.preventDefault();
      utolso.focus();
    } else if (!e.shiftKey && (akt === utolso || !node.contains(akt))) {
      e.preventDefault();
      elso.focus();
    }
  };
  node.addEventListener('keydown', kezel);
  return {
    destroy() {
      node.removeEventListener('keydown', kezel);
      visszaad(elozo);
    },
  };
}

/** A fókusz visszaadása; ha az elem már nincs a lapon, a munkaterület kapja. */
export function visszaad(el: HTMLElement | null): void {
  queueMicrotask(() => {
    if (el?.isConnected && lathato(el)) el.focus({ preventScroll: true });
    else regioFokusz('munkaterulet');
  });
}

/** A régiók a DOM sorrendjében: `data-regio` (oldalsáv → munkaterület → jobb panel → állapotsor). A rejtett régió
 *  (`data-regio-rejtett`: a rejtett oldalsáv, jobb panel, állapotsor; C38) is sorra kerül: belépéskor megjelenik. */
export function regiok(): HTMLElement[] {
  return [...document.querySelectorAll<HTMLElement>('[data-regio]')].filter(
    (r) => r.hasAttribute('data-regio-rejtett') || lathato(r),
  );
}

export function regioFokusz(nev: string): boolean {
  const r = document.querySelector<HTMLElement>(`[data-regio="${nev}"]`);
  return r ? fokuszRegio(r) : false;
}

function fokuszRegio(r: HTMLElement): boolean {
  // a rejtett régió előbb megjelenik (a komponens a `regio-megjelenit` eseményre szinkron vált; C38)
  if (r.hasAttribute('data-regio-rejtett')) r.dispatchEvent(new CustomEvent('regio-megjelenit'));
  const cel = r.querySelector<HTMLElement>('[data-regio-fokusz]') ?? fokuszalhatok(r)[0] ?? r;
  if (cel === r && !r.hasAttribute('tabindex')) r.tabIndex = -1;
  cel.focus({ preventScroll: true });
  return document.activeElement === cel;
}

/** F6 / ⇧F6: a következő / előző régió, körbe. */
export function regioLep(irany: 1 | -1): void {
  const rs = regiok();
  if (!rs.length) return;
  const most = rs.findIndex((r) => r.contains(document.activeElement));
  const kov = most < 0 ? (irany > 0 ? 0 : rs.length - 1) : (most + irany + rs.length) % rs.length;
  fokuszRegio(rs[kov]);
}

let utolso: HTMLElement | null = null;

/** Az utolsó fókuszált elem követése (a `fokuszVisszaallit`-nak). A leiratkozót adja vissza. */
export function utolsoFokuszKovet(): () => void {
  const f = (e: FocusEvent) => {
    if (e.target instanceof HTMLElement && e.target !== document.body) utolso = e.target;
  };
  document.addEventListener('focusin', f);
  return () => {
    document.removeEventListener('focusin', f);
    utolso = null;
  };
}

/** A héj hívja, amikor az ablak visszajön (`window.manifold.fokusz`): ha a fókusz elveszett (a `body`-n áll),
 *  az utolsó fókuszált elem kapja vissza, ha még a lapon van és látszik; különben a munkaterület. Igaz, ha
 *  állított. */
export function fokuszVisszaallit(): boolean {
  if (fokuszban()) return false;
  if (utolso?.isConnected && lathato(utolso)) {
    utolso.focus({ preventScroll: true });
    if (document.activeElement === utolso) return true;
  }
  return regioFokusz('munkaterulet');
}
