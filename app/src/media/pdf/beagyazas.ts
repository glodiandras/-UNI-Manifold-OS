// A beágyazott PDF (C16, E14): `![[x.pdf#page=N]]` — fix magasságú (520 px, vagy `|N`) doboz a pdf.js-szel, benne az ÖSSZES
// lap függőlegesen görgethetően, a doboz szélességéhez igazítva (retina-élesen). Fejléc: név, „N / M” lapszám-mező (beírható,
// Enterre ugrik), ‹ ›, „Megnyitás” (a teljes olvasóban, az aktuális lapon); a `#page=N` a kezdő lap.
// Lusta: a doboz csak láthatóvá váláskor tölt (egy jegyzetben sok PDF-beágyazás lehet), a lapok csak a látható sávban és
// annak szomszédságában rajzolódnak; a távoli lap vászna felszabadul (memória). A doboz végén a görgetés a jegyzetnek adódik át.
// A dokumentumot a doboz élete alatt tartja (a közös gyorsítótár a lezárás után még 30 s-ig őrzi).

import { t } from '../../lib/i18n';
import type { BeagyazasAdat } from '../../lib/vault/linkek.svelte';
import { fajlNev } from '../../lib/vault/fajlok.svelte';
import type { BeagyazasOpciok, BeagyazasRenderelo } from '../../szerkeszto/beagyazas/regiszter';
import { mediaHorgony, meretAliasbol, type LinkAdat } from '../../szerkeszto/linkek/adat';
import { linkMegnyit, nyitasMod } from '../../szerkeszto/linkek/navigacio';
import { nyit } from './dokumentum';

export const PDF_MAGASSAG = 520;
const KOMPAKT_MAGASSAG = 320;
/** A becsült oldalarány (A4 álló), amíg az első lap mérete ismeretlen. */
const ALAP_ARANY = Math.SQRT2;
/** A látható sáv körül ennyivel (a doboz magasságának hányada) tágabb sávban rajzolódnak a lapok. */
const SZOMSZED = '60% 0px';

function el<K extends keyof HTMLElementTagNameMap>(tag: K, osztaly?: string): HTMLElementTagNameMap[K] {
  const e = document.createElement(tag);
  if (osztaly) e.className = osztaly;
  return e;
}

function gomb(szoveg: string, cimke: string, f: (e: MouseEvent) => void): HTMLButtonElement {
  const b = el('button', 'pdf-be-gomb');
  b.type = 'button';
  b.textContent = szoveg;
  b.title = cimke;
  b.setAttribute('aria-label', cimke);
  b.addEventListener('click', (e) => {
    e.preventDefault();
    e.stopPropagation();
    f(e);
  });
  return b;
}

/** A futó rajzolás megszakítója: a következő rajzolás előtt meghívódik (T067). */
export interface RajzolasTarto {
  feladat: { cancel(): void } | null;
}

/** A pdf.js a megszakított rajzolás ígéretét `RenderingCancelledException`-nel utasítja el: ez nem hiba. */
export function megszakitva(e: unknown): boolean {
  return !!e && typeof e === 'object' && (e as { name?: unknown }).name === 'RenderingCancelledException';
}

/** Egy lap rajzolása. Az ugyanarra a vászonra induló rajzolásokat a hívó sorba rendezi (`rajzoloSor`), így a pdf.js
 *  „Cannot use the same canvas during multiple render() operations” hibája nem állhat elő. */
export async function lapRajzol(ut: string, n: number, vaszon: HTMLCanvasElement, szelesseg: number, tarto?: RajzolasTarto): Promise<number> {
  const h = await nyit(ut);
  try {
    const cel = Math.max(1, Math.min(h.dok.numPages, n));
    const lap = await h.dok.getPage(cel);
    const alap = lap.getViewport({ scale: 1 });
    const dpr = Math.min(2, window.devicePixelRatio || 1);
    const vp = lap.getViewport({ scale: (szelesseg * dpr) / alap.width });
    vaszon.width = Math.round(vp.width);
    vaszon.height = Math.round(vp.height);
    vaszon.style.width = `${szelesseg}px`;
    vaszon.style.height = `${Math.round(vp.height / dpr)}px`;
    const feladat = lap.render({ canvas: vaszon, viewport: vp });
    if (tarto) tarto.feladat = feladat;
    try {
      await feladat.promise;
    } finally {
      if (tarto?.feladat === feladat) tarto.feladat = null;
    }
    return h.dok.numPages;
  } finally {
    h.elenged();
  }
}

/** Sorba rendezett rajzolás egy vászonra: az új kérés megszakítja a futót (`cancel()`), és csak utána indul; a közben
 *  elavult kérés (újabb jött) ki sem indul. A `fut` a legutóbbi kérés sorszáma. */
export function rajzoloSor(egy: (sajat: number, tarto: RajzolasTarto) => Promise<void>) {
  const tarto: RajzolasTarto = { feladat: null };
  let lanc: Promise<void> = Promise.resolve();
  let fut = 0;
  return {
    get fut() {
      return fut;
    },
    kerj(): Promise<void> {
      const sajat = ++fut;
      tarto.feladat?.cancel();
      lanc = lanc.then(() => (sajat === fut ? egy(sajat, tarto) : undefined)).catch(() => undefined);
      return lanc;
    },
    megszakit(): void {
      fut++;
      tarto.feladat?.cancel();
    },
  };
}

interface Lap {
  n: number;
  doboz: HTMLElement;
  vaszon: HTMLCanvasElement | null;
  /** magasság / szélesség: az első lapé becslésnek, a rajzolt lapé pontos */
  arany: number | null;
  megszakit: (() => void) | null;
}

function render(adat: BeagyazasAdat, link: LinkAdat, kont: HTMLElement, o: BeagyazasOpciok): void {
  const ut = adat.ut!;
  const meret = meretAliasbol(link.alias);
  const kezdo = mediaHorgony(link.alcel).page ?? 1;
  let oldal = kezdo;
  let osszes = 0;
  kont.className = 'beagyazas beagyazas-media beagyazas-pdf-nezo';
  kont.replaceChildren();

  const megnyit = (e: MouseEvent | KeyboardEvent) =>
    void linkMegnyit({ forras: o.forras, cel: link.cel, alcel: `page=${oldal}` }, nyitasMod(e) === 'aktiv' ? 'ujful' : nyitasMod(e));

  const fej = el('span', 'pdf-be-fej');
  const cim = el('a', 'beagyazas-cim');
  cim.setAttribute('role', 'link');
  cim.tabIndex = 0;
  cim.textContent = fajlNev(ut);
  cim.addEventListener('click', (e) => {
    e.preventDefault();
    e.stopPropagation();
    megnyit(e);
  });
  cim.addEventListener('keydown', (e) => {
    if (e.key === 'Enter') megnyit(e);
  });
  const mezo = el('input', 'pdf-be-oldal');
  mezo.type = 'text';
  mezo.inputMode = 'numeric';
  mezo.value = String(oldal);
  mezo.setAttribute('aria-label', t('Oldalszám'));
  const osszesJel = el('span', 'pdf-be-osszes');
  const elozo = gomb('‹', t('Előző oldal'), () => ugrik(oldal - 1));
  const kov = gomb('›', t('Következő oldal'), () => ugrik(oldal + 1));
  fej.append(cim, el('span', 'pdf-be-hely'), elozo, mezo, osszesJel, kov, gomb(t('Megnyitás'), t('Megnyitás a teljes olvasóban ezen az oldalon'), megnyit));

  const test = el('div', 'pdf-be-test');
  test.style.height = `${meret?.szelesseg ?? (o.kompakt ? KOMPAKT_MAGASSAG : PDF_MAGASSAG)}px`;
  test.tabIndex = 0;
  test.setAttribute('role', 'group');
  test.setAttribute('aria-label', t('{nev}, görgethető lapok', { nev: fajlNev(ut) }));
  const uzenet = el('span', 'beagyazas-uzenet');
  uzenet.textContent = t('A PDF betöltése…');
  test.appendChild(uzenet);
  kont.append(fej, test);

  const felirat = () => {
    if (document.activeElement !== mezo) mezo.value = String(oldal);
    osszesJel.textContent = osszes ? `/ ${osszes}` : '';
    elozo.disabled = oldal <= 1;
    kov.disabled = osszes > 0 && oldal >= osszes;
  };
  felirat();

  const hiba = (e: unknown) => {
    kont.className = 'beagyazas beagyazas-hiba';
    const u = el('span', 'beagyazas-uzenet');
    u.textContent = t('A PDF nem tölthető be: {hiba}', { hiba: e instanceof Error ? e.message : String(e) }) + ' ';
    kont.replaceChildren(u, gomb(t('Megnyitás'), t('Megnyitás a teljes olvasóban'), megnyit));
    o.kesz?.();
  };

  const lapok: Lap[] = [];
  let szel = 0;
  let alapArany = ALAP_ARANY;
  let tartas: { elenged(): void } | null = null;
  let lapFigyelo: IntersectionObserver | null = null;
  let atmeretezo: ResizeObserver | null = null;
  let kerekIdo = 0;

  const meretez = (lap: Lap) => {
    lap.doboz.style.width = `${szel}px`;
    lap.doboz.style.height = `${Math.round(szel * (lap.arany ?? alapArany))}px`;
  };

  const felszabadit = (lap: Lap) => {
    lap.megszakit?.();
    lap.megszakit = null;
    if (lap.vaszon) {
      lap.vaszon.width = 0; // a bitmap memóriája azonnal felszabadul
      lap.vaszon.height = 0;
      lap.vaszon.remove();
      lap.vaszon = null;
    }
    lap.doboz.replaceChildren();
    void nyit(ut)
      .then((h) => {
        void h.dok
          .getPage(lap.n)
          .then((p) => p.cleanup())
          .catch(() => {})
          .finally(() => h.elenged());
      })
      .catch(() => {});
  };

  const rajzol = (lap: Lap) => {
    lap.megszakit?.();
    const vaszon = el('canvas', 'pdf-be-lap');
    vaszon.setAttribute('role', 'img');
    vaszon.setAttribute('aria-label', t('{nev}, {n}. oldal', { nev: fajlNev(ut), n: lap.n }));
    const sor = rajzoloSor(async (sajat, tarto) => {
      try {
        await lapRajzol(ut, lap.n, vaszon, szel, tarto);
        if (sajat !== sor.fut || o.jel?.aborted) return;
        // a pontos magasság: a fölötte álló lapok változása ne tolja el a nézetet
        const regi = lap.doboz.offsetHeight;
        lap.arany = (parseFloat(vaszon.style.height) || 0) / szel || lap.arany;
        meretez(lap);
        const delta = lap.doboz.offsetHeight - regi;
        if (delta && lap.doboz.offsetTop + regi <= test.scrollTop + 1) test.scrollTop += delta;
        lap.vaszon = vaszon;
        lap.doboz.replaceChildren(vaszon);
      } catch (e) {
        if (megszakitva(e) || sajat !== sor.fut || o.jel?.aborted) return;
        const u = el('span', 'beagyazas-uzenet');
        u.textContent = t('A(z) {n}. oldal nem rajzolható.', { n: lap.n });
        lap.doboz.replaceChildren(u);
      }
    });
    lap.megszakit = () => sor.megszakit();
    void sor.kerj();
  };

  const ugrik = (n: number) => {
    if (!lapok.length) return;
    const cel = Math.max(1, Math.min(lapok.length, Math.round(n) || 1));
    test.scrollTop = lapok[cel - 1].doboz.offsetTop;
    oldal = cel;
    felirat();
  };

  // az aktuális oldal: az utolsó, amelynek teteje a nézet felső harmadánál nem lejjebb van
  const oldalSzamol = () => {
    kerekIdo = 0;
    const hatar = test.scrollTop + test.clientHeight / 3;
    let uj = 1;
    for (const l of lapok) {
      if (l.doboz.offsetTop <= hatar) uj = l.n;
      else break;
    }
    if (uj !== oldal) {
      oldal = uj;
      felirat();
    }
  };

  mezo.addEventListener('keydown', (e) => {
    e.stopPropagation();
    if (e.key === 'Enter') {
      e.preventDefault();
      ugrik(parseInt(mezo.value, 10));
      mezo.blur();
    } else if (e.key === 'Escape') {
      mezo.value = String(oldal);
      mezo.blur();
    }
  });
  mezo.addEventListener('focus', () => mezo.select());
  mezo.addEventListener('blur', () => {
    mezo.value = String(oldal);
  });

  const inditas = async () => {
    szel = Math.max(200, Math.floor((test.clientWidth || 640) - 2));
    try {
      const h = await nyit(ut);
      if (o.jel?.aborted) {
        h.elenged();
        return;
      }
      tartas = h;
      osszes = h.dok.numPages;
      const elso = await h.dok.getPage(1);
      const vp = elso.getViewport({ scale: 1 });
      if (vp.width > 0) alapArany = vp.height / vp.width;
      if (o.jel?.aborted) return;
    } catch (e) {
      if (!o.jel?.aborted) hiba(e);
      return;
    }
    uzenet.remove();
    oldal = Math.max(1, Math.min(osszes, kezdo));
    for (let n = 1; n <= osszes; n++) {
      const doboz = el('div', 'pdf-be-lapdoboz');
      doboz.dataset.oldal = String(n);
      const lap: Lap = { n, doboz, vaszon: null, arany: null, megszakit: null };
      meretez(lap);
      lapok.push(lap);
      test.appendChild(doboz);
    }
    felirat();
    lapFigyelo = new IntersectionObserver(
      (bejegyzesek) => {
        for (const b of bejegyzesek) {
          const lap = lapok[Number((b.target as HTMLElement).dataset.oldal) - 1];
          if (!lap) continue;
          if (b.isIntersecting) {
            if (!lap.vaszon && !lap.megszakit) rajzol(lap);
          } else if (lap.vaszon || lap.megszakit) {
            felszabadit(lap);
          }
        }
      },
      { root: test, rootMargin: SZOMSZED },
    );
    for (const l of lapok) lapFigyelo.observe(l.doboz);
    test.addEventListener('scroll', () => {
      if (!kerekIdo) kerekIdo = requestAnimationFrame(oldalSzamol);
    });
    if (oldal > 1) ugrik(oldal);
    // a szélesség változására (ablak, panel) a lapok újraméreteződnek és a rajzoltak újrarajzolódnak
    atmeretezo = new ResizeObserver(() => {
      const w = Math.max(200, Math.floor(test.clientWidth - 2));
      if (Math.abs(w - szel) < 24) return;
      szel = w;
      for (const l of lapok) {
        meretez(l);
        if (l.vaszon || l.megszakit) rajzol(l);
      }
    });
    atmeretezo.observe(test);
    o.kesz?.();
  };

  // lusta: a dokumentum a doboz láthatóvá válásakor töltődik
  const figyelo = new IntersectionObserver((b) => {
    if (!b.some((x) => x.isIntersecting)) return;
    figyelo.disconnect();
    void inditas();
  });
  figyelo.observe(kont);
  o.jel?.addEventListener('abort', () => {
    figyelo.disconnect();
    lapFigyelo?.disconnect();
    atmeretezo?.disconnect();
    if (kerekIdo) cancelAnimationFrame(kerekIdo);
    for (const l of lapok) l.megszakit?.();
    tartas?.elenged();
    tartas = null;
  });
}

export const pdfBeagyazasRenderelo: BeagyazasRenderelo = { tipus: 'pdf', render };
