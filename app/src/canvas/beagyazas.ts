// A `![[x.canvas]]` beágyazás (C14): a canvas kicsinyített, csak olvasható képe (a kártyák kerete a nevükkel, a
// csoportok, az élek), kattintásra a canvas megnyílik. A tartalom a core fájl-API-jából jön, a rajz SVG.

import { kerdez } from '../lib/core/api';
import { fajlNev } from '../lib/vault/fajlok.svelte';
import type { BeagyazasRenderelo } from '../szerkeszto/beagyazas/regiszter';
import type { FajlOlvasas } from '../szerkeszto/dokumentum/api';
import { linkMegnyit, nyitasMod } from '../szerkeszto/linkek/navigacio';
import { befoglalo, elGeometria, nyilhegy } from './geometria';
import { beolvas, csomopontok, elek, kezdoVeg, szinCss, zaroVeg, type Csomopont } from './modell';
import { t } from '../lib/i18n';

const NS = 'http://www.w3.org/2000/svg';
export const BEAGYAZAS_MAGASSAG = 360;

function svg<K extends keyof SVGElementTagNameMap>(tag: K, attr: Record<string, string | number>): SVGElementTagNameMap[K] {
  const e = document.createElementNS(NS, tag);
  for (const [k, v] of Object.entries(attr)) e.setAttribute(k, String(v));
  return e;
}

/** Az első sor jelölés nélkül (fejezetjel, kiemelés, kód, link-zárójelek). */
export function sima(sor: string): string {
  return sor
    .replace(/^#+\s*/, '')
    .replace(/\[\[([^\]|]*)\|?([^\]]*)\]\]/g, (_m, cel: string, alias: string) => alias || cel)
    .replace(/(\*\*|__|==|~~|\*|_|`)/g, '');
}

function felirat(c: Csomopont): string {
  if (c.type === 'file') return fajlNev(String(c.file ?? ''));
  if (c.type === 'text') return sima(String(c.text ?? '').split('\n', 1)[0]);
  if (c.type === 'link') return String(c.url ?? '');
  if (c.type === 'group') return String(c.label ?? '');
  return c.type;
}

/** A canvas képe egy SVG-ben (a doboz kitöltve, arányosan). */
export function canvasKep(szoveg: string): SVGSVGElement | string {
  const b = beolvas(szoveg);
  if (!b.vaszon) return b.hiba ?? t('A canvas nem olvasható.');
  const v = b.vaszon;
  const d = befoglalo(csomopontok(v));
  const kep = svg('svg', { class: 'canvas-kep', role: 'img', preserveAspectRatio: 'xMidYMid meet' });
  if (!d) {
    kep.setAttribute('viewBox', '0 0 100 40');
    return kep;
  }
  const m = 40;
  kep.setAttribute('viewBox', `${d.x - m} ${d.y - m} ${d.width + 2 * m} ${d.height + 2 * m}`);
  const szerint = new Map(csomopontok(v).map((c) => [c.id, c]));
  for (const c of csomopontok(v)) {
    const szin = szinCss(c.color);
    const r = svg('rect', { x: c.x, y: c.y, width: c.width, height: c.height, rx: 8, class: `kep-node kep-${c.type}` });
    if (szin) r.style.setProperty('--szin', szin);
    kep.appendChild(r);
    const t = felirat(c);
    if (t) {
      const sz = svg('text', { x: c.x + 16, y: c.type === 'group' ? c.y - 12 : c.y + 40, class: `kep-felirat kep-felirat-${c.type}` });
      sz.textContent = t.length > 60 ? t.slice(0, 59) + '…' : t;
      kep.appendChild(sz);
    }
  }
  for (const e of elek(v)) {
    const a = szerint.get(e.fromNode);
    const bb = szerint.get(e.toNode);
    if (!a || !bb) continue;
    const g = elGeometria(a, e.fromSide, bb, e.toSide);
    const szin = szinCss(e.color);
    const ut = svg('path', { d: g.d, class: 'kep-el' });
    if (szin) ut.style.setProperty('--szin', szin);
    kep.appendChild(ut);
    for (const [van, hegy, irany] of [
      [zaroVeg(e) === 'arrow', g.veg, g.vegIrany],
      [kezdoVeg(e) === 'arrow', g.kezd, g.kezdIrany],
    ] as const) {
      if (!van) continue;
      const n = svg('polygon', { points: nyilhegy(hegy, irany, 24), class: 'kep-nyil' });
      if (szin) n.style.setProperty('--szin', szin);
      kep.appendChild(n);
    }
  }
  return kep;
}

export const canvasBeagyazasRenderelo: BeagyazasRenderelo = {
  tipus: 'canvas',
  async render(adat, link, kont, o) {
    const ut = adat.ut!;
    kont.className = 'beagyazas beagyazas-canvas';
    kont.replaceChildren();
    const fej = document.createElement('a');
    fej.className = 'beagyazas-cim';
    fej.setAttribute('role', 'link');
    fej.tabIndex = 0;
    fej.textContent = fajlNev(ut);
    const nyit = (e: MouseEvent | KeyboardEvent) => {
      e.preventDefault();
      e.stopPropagation();
      void linkMegnyit({ forras: o.forras, cel: link.cel, alcel: null }, nyitasMod(e));
    };
    fej.addEventListener('click', nyit);
    fej.addEventListener('keydown', (e) => e.key === 'Enter' && nyit(e));
    const test = document.createElement('div');
    test.className = 'beagyazas-canvas-kep';
    test.style.height = `${BEAGYAZAS_MAGASSAG}px`;
    test.title = t('Kattintásra megnyílik');
    test.addEventListener('click', nyit);
    kont.append(fej, test);
    const f = await kerdez<FajlOlvasas>(`/api/vault/fajl?ut=${encodeURIComponent(ut)}`, { idokorlat: 15000 });
    if (o.jel?.aborted) return;
    const kep = canvasKep(f.tartalom);
    if (typeof kep === 'string') {
      const h = document.createElement('span');
      h.className = 'beagyazas-uzenet';
      h.textContent = kep;
      test.replaceChildren(h);
    } else {
      kep.setAttribute('aria-label', `Canvas: ${fajlNev(ut)}`);
      test.replaceChildren(kep);
    }
  },
};
