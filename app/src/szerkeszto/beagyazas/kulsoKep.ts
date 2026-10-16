// 04-embeds-02 / 01-rendering-04: külső kép (`![](https://…)`). A D3 szerint futásidőben nincs hálózat, kivéve a kifejezett
// letöltést: a kép alapból NEM töltődik (nincs <img src="https://…">, a CSP `img-src` nem lazul), helyette helyőrző és
// „Download image” gomb. A letöltést a core végzi (`POST /api/vault/import {url, forras}`, `core/kulso_kep.py`: csak https,
// SSRF-védelem, méret-/idő-/típuskorlát) a beállított csatolmány-mappába; utána a helyi fájl látszik. A jegyzet linkjét csak a
// felhasználó kifejezett „Use downloaded file in note” választása írja át, a jegyzet Dokumentumán (CAS-os mentés, pillanatkép).

import { ChangeSet } from '@codemirror/state';
import type { SyntaxNode } from '@lezer/common';
import { t } from '../../lib/i18n';
import { hibaUzenet, kerdez } from '../../lib/core/api';
import { ikonElem } from '../../lib/ikon/ikonElem';
import { ImageDown, TriangleAlert } from '../../lib/ikon/ikonok';
import { linkek } from '../../lib/vault/linkek.svelte';
import { obsidianElemzo } from '../markdown/elemzo';
import { kepAdat, type LinkAdat } from '../linkek/adat';
import { szerkesztok } from '../szerkesztok.svelte';
import type { BeagyazasOpciok } from './regiszter';

export interface LetoltesEredmeny {
  ut: string;
  meglevo?: boolean;
  figyelmeztetes?: string | null;
}

/** Az ebben a munkamenetben már letöltött külső képek (link → vault-út): az újrarajzolt helyőrző a helyi fájlt mutatja. */
const letoltott = new Map<string, string>();

/** Teszteknek: a munkamenet-emlékezet ürítése. */
export function letoltottUrit(): void {
  letoltott.clear();
}

/** A kép letöltése a core-ral (csak kattintásra hívódik). */
export function kepLetolt(url: string, forras: string): Promise<LetoltesEredmeny> {
  return kerdez<LetoltesEredmeny>('/api/vault/import', { metodus: 'POST', torzs: { url, forras }, idokorlat: 60000 });
}

function gomb(szoveg: string, osztaly = ''): HTMLButtonElement {
  const b = document.createElement('button');
  b.type = 'button';
  b.className = `beagyazas-letrehoz${osztaly ? ' ' + osztaly : ''}`;
  b.textContent = szoveg;
  return b;
}

function sor(osztaly: string, ikon: typeof ImageDown | null, szoveg: string, szerep?: 'status' | 'alert'): HTMLElement {
  const s = document.createElement('span');
  s.className = osztaly;
  if (szerep) s.setAttribute('role', szerep);
  if (ikon) s.appendChild(ikonElem(ikon, 14));
  const sz = document.createElement('span');
  sz.className = 'beagyazas-uzenet';
  sz.textContent = szoveg;
  s.appendChild(sz);
  return s;
}

/** A külső kép eleme: helyőrző letöltés-gombbal, vagy (letöltés után) a helyi fájl beágyazása. A `helyi` a helyi út
 *  beágyazás-elemét rajzolja (a rajzoló motor közös renderelője). */
export function kulsoKepElem(kont: HTMLElement, link: LinkAdat, o: BeagyazasOpciok, helyi: (ut: string) => HTMLElement): void {
  const url = link.cel;
  const nev = link.alt || url;
  const ismert = letoltott.get(url);
  if (ismert) {
    kesz(kont, link, o, ismert, helyi);
    return;
  }
  kont.className = 'beagyazas beagyazas-kulso';
  kont.replaceChildren(sor('beagyazas-kulso-sor', ImageDown, t('Külső kép: {nev}. A megjelenítéshez előbb töltsd le.', { nev })));
  // a lebegő előnézetben és csak olvasható nézetben a vault nem íródik: csak a jelzés látszik
  if (o.kompakt || o.csakOlvashato || !/^https:\/\//i.test(url)) return;
  const b = gomb(t('Kép letöltése'), 'beagyazas-kulso-letolt');
  b.title = t('Letöltés innen: {url}', { url });
  let hiba: HTMLElement | null = null;
  b.addEventListener('click', (ev) => {
    ev.preventDefault();
    ev.stopPropagation();
    if (b.disabled) return;
    b.disabled = true;
    b.textContent = t('Letöltés…');
    kont.setAttribute('aria-busy', 'true');
    hiba?.remove();
    hiba = null;
    void kepLetolt(url, o.forras).then(
      (r) => {
        kont.removeAttribute('aria-busy');
        if (o.jel?.aborted) return;
        letoltott.set(url, r.ut);
        kesz(kont, link, o, r.ut, helyi, r.figyelmeztetes ?? null);
        o.kesz?.();
      },
      (e) => {
        kont.removeAttribute('aria-busy');
        if (o.jel?.aborted) return;
        b.disabled = false;
        b.textContent = t('Letöltés újra');
        hiba = sor('beagyazas-kulso-hiba', TriangleAlert, t('A kép nem tölthető le: {hiba}', { hiba: hibaUzenet(e) }), 'alert');
        kont.appendChild(hiba);
        o.kesz?.();
      },
    );
  });
  kont.appendChild(b);
}

function kesz(kont: HTMLElement, link: LinkAdat, o: BeagyazasOpciok, ut: string, helyi: (ut: string) => HTMLElement,
  figyelmeztetes: string | null = null): void {
  kont.className = 'beagyazas beagyazas-kulso-kesz';
  kont.replaceChildren(helyi(ut));
  if (figyelmeztetes) kont.appendChild(sor('beagyazas-kulso-sor', TriangleAlert, figyelmeztetes, 'status'));
  if (o.kompakt || o.csakOlvashato || !/\.md$/i.test(o.forras)) return;
  const b = gomb(t('Helyi fájl használata a jegyzetben'), 'beagyazas-kulso-atir');
  b.title = t('A jegyzet linkje erre a fájlra mutasson: {ut}', { ut });
  let allapot: HTMLElement | null = null;
  b.addEventListener('click', (ev) => {
    ev.preventDefault();
    ev.stopPropagation();
    if (b.disabled) return;
    b.disabled = true;
    allapot?.remove();
    void kepLinkAtir(o.forras, link.cel, ut).then(
      (n) => {
        if (o.jel?.aborted) return;
        b.remove();
        allapot = sor('beagyazas-kulso-sor', null, t('A jegyzet linkje frissítve ({n}).', { n }), 'status');
        kont.appendChild(allapot);
        o.kesz?.();
      },
      (e) => {
        if (o.jel?.aborted) return;
        b.disabled = false;
        allapot = sor('beagyazas-kulso-hiba', TriangleAlert, t('A link nem írható át: {hiba}', { hiba: hibaUzenet(e) }), 'alert');
        kont.appendChild(allapot);
        o.kesz?.();
      },
    );
  });
  kont.appendChild(b);
}

function urlCsomopont(n: SyntaxNode): SyntaxNode | null {
  for (let c = n.firstChild; c; c = c.nextSibling) if (c.name === 'URL') return c;
  return null;
}

/** A szöveg azon Markdown-képeinek URL-része, amelyek pontosan erre a külső linkre mutatnak (a szintaxisfa szerint: kódblokk,
 *  komment és nem-kép link nem érintett). Az alt-szöveg és a méret megmarad. */
export function kepLinkValtozasok(szoveg: string, url: string, ujCel: string): { from: number; to: number; insert: string }[] {
  const ki: { from: number; to: number; insert: string }[] = [];
  const olvas = (a: number, b: number) => szoveg.slice(a, b);
  obsidianElemzo.parse(szoveg).iterate({
    enter: (n) => {
      if (n.name !== 'Image') return;
      const a = kepAdat(n.node, olvas);
      const u = urlCsomopont(n.node);
      if (a?.kulso && a.cel === url && u) ki.push({ from: u.from, to: u.to, insert: ujCel });
      return false;
    },
  });
  return ki;
}

/** A Markdown-cél írható alakja: a core kész md-célja, ha adott; különben szóköz/zárójel esetén `<…>`. */
function mdCel(cel: string, md: string | undefined): string {
  if (md) return md;
  return /[\s()<>]/.test(cel) ? `<${cel}>` : cel;
}

/** A `forras` jegyzet `url` képlinkjeinek átírása a letöltött `ut` fájlra (a beállított link-formátum md-célja). A jegyzet
 *  közös Dokumentumán megy (a nyitott nézetek látják, egy visszavonási lépés), majd CAS-os mentés. → az átírt linkek száma. */
export async function kepLinkAtir(forras: string, url: string, ut: string): Promise<number> {
  const cel = await linkek.linkCelAdat(ut, forras);
  const ujCel = mdCel(cel.cel, cel.md);
  const d = await szerkesztok.dokumentumok.megnyit(forras);
  if (!d.mentetlen) await d.kulsoValtozas();
  if (d.csakOlvashato || d.allapot === 'utkozes' || d.allapot === 'eltunt')
    throw new Error(t('A jegyzet most nem szerkeszthető. Nyisd meg, és oldd fel az ütközést.'));
  const valtozasok = kepLinkValtozasok(d.szoveg.toString(), url, ujCel);
  if (!valtozasok.length) throw new Error(t('A link már nincs a jegyzetben.'));
  const cs = ChangeSet.of(valtozasok, d.szoveg.length);
  d.valtozott(cs, cs.apply(d.szoveg), null, true);
  const eredmeny = await d.ment({ pillanat: d.nezetSzam === 0 });
  if (!eredmeny.ok) throw new Error(t('A mentés nem sikerült. A változás megvan; nyisd meg a jegyzetet.'));
  if (d.nezetSzam === 0) void szerkesztok.dokumentumok.elenged(d);
  return valtozasok.length;
}
