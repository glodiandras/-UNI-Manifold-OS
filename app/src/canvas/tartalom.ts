// A kártyák tartalma (C14): DOM-rajzolók a kártya törzsébe. A szövegkártya az Olvasó rajzolójával (ugyanaz az
// elemző, mint a szerkesztőé), a jegyzetkártya a C10 beágyazás-motorjával (élő tartalom a core indexéből,
// körkörösség- és mélységvédelem), a kép a kicsinyített változattal (a megjelenített méret vödre), a hang és a
// videó natív elemmel. Minden rajzoló a lebontó függvényét adja vissza. A jegyzet- és szövegkártya beágyazásai célonként
// frissülnek a tartalmi eseményre (a többi kártya DOM-ja marad).

import { KeresSor } from '../lib/core/keresSor';
import { linkek } from '../lib/vault/linkek.svelte';
import { fajlNev, type FajlTipus } from '../lib/vault/fajlok.svelte';
import { beagyazasElem, beagyazasFrissitesFigyel } from '../szerkeszto/beagyazas/rajzol';
import { kepVodor } from '../szerkeszto/beagyazas/nagyito';
import { obsidianElemzo } from '../szerkeszto/markdown/elemzo';
import { dokumentumRenderel } from '../szerkeszto/olvaso/html';
import { ikonElem } from '../lib/ikon/ikonElem';
import { ExternalLink } from '../lib/ikon/ikonok';
import { kulsoCim, kulsoLink } from '../szerkeszto/linkek/kulso';
import { LustaRajzolo } from '../szerkeszto/olvaso/lusta';
import { t } from '../lib/i18n';

const KEP = /\.(png|jpe?g|gif|webp|avif|svg|heic|heif|bmp|tiff?)$/i;
const VIDEO = /\.(mp4|m4v|mov|webm|mkv|ogv)$/i;
const HANG = /\.(mp3|m4a|wav|flac|ogg|opus|aac|3gp)$/i;

/** A fájl típusa a kiterjesztéséből (a fájlfa típusaival egyező nevek). */
export function fajlTipus(ut: string): FajlTipus {
  const k = ut.toLowerCase();
  if (k.endsWith('.md')) return 'md';
  if (k.endsWith('.canvas')) return 'canvas';
  if (k.endsWith('.base')) return 'base';
  if (k.endsWith('.pdf')) return 'pdf';
  if (KEP.test(k)) return 'kep';
  if (VIDEO.test(k)) return 'video';
  if (HANG.test(k)) return 'hang';
  return 'egyeb';
}

export interface SzovegOpciok {
  /** a canvas nem írható: a kártya feladat-jelölői le vannak tiltva (09-canvas-01), a `cim` magyarázza, mit kell tenni */
  csakOlvashato?: boolean;
  cim?: string;
}

/** Markdown-szöveg az Olvasó tipográfiájával (a szövegkártya). */
export function szovegRajzol(kont: HTMLElement, szoveg: string, canvasUt: string, o: SzovegOpciok = {}): () => void {
  const lusta = LustaRajzolo.azonnali();
  const md = document.createElement('div');
  md.className = 'md tipo kartya-md';
  md.appendChild(
    dokumentumRenderel(obsidianElemzo.parse(szoveg), {
      olvas: (a, b) => szoveg.slice(a, b),
      ut: canvasUt,
      lusta,
      beagyazas: { lanc: [{ ut: canvasUt, alcel: null }], melyseg: 0 },
      csakOlvashato: o.csakOlvashato === true,
    }),
  );
  if (o.csakOlvashato && o.cim)
    for (const j of md.querySelectorAll<HTMLInputElement>('input.feladat-jelolo')) if (!j.closest('.beagyazas-torzs')) j.title = o.cim;
  kont.replaceChildren(md);
  const le = beagyazasFrissitesFigyel(md);   // 04-embeds-07: a szövegkártya beágyazásai a céljuk változásakor frissülnek
  return () => { le(); lusta.leall(); };
}

/** A jegyzetkártyák tartalmának kérés-sora (C33, T184; a C14-terv „legfeljebb 6 párhuzamos kéréssel”): közös minden vászonnak. */
export const kartyaSor = new KeresSor(6);

/** A jegyzet élő tartalma (a `subpath` fejezet vagy blokk szelete); a lekérés a `kartyaSor`-on (≤ 6 egyidejű). */
export function jegyzetRajzol(kont: HTMLElement, ut: string, subpath: string | undefined, canvasUt: string): () => void {
  const vezerlo = new AbortController();
  const alcel = subpath?.replace(/^#/, '') || null;
  const md = document.createElement('div');
  md.className = 'md tipo kartya-md';
  md.appendChild(
    beagyazasElem(
      { cel: ut, alcel, alias: null, beagyazas: true, from: 0, to: 0 },
      { forras: canvasUt, lanc: [{ ut: canvasUt, alcel: null }], melyseg: 0, kompakt: true, jel: vezerlo.signal, sor: kartyaSor },
    ),
  );
  kont.replaceChildren(md);
  const le = beagyazasFrissitesFigyel(md);   // 04-embeds-07: a jegyzetkártya a jegyzet (vagy beágyazott célja) mentésekor frissül
  return () => { le(); vezerlo.abort(); };
}

/** PDF- és Bases-kártya (09-canvas-07/08): a jegyzetek közötti `![[x.pdf#page=N]]` / `![[x.base#Nézet]]` beágyazás motorja
 *  rajzolja, a kártya méretére nyújtva (a CSS). A modul-kapcsoló és a hiányzó-cél kezelés a beágyazás-motoré; ha a modul ki van
 *  kapcsolva, a motor chipet ad. A `subpath` a PDF-nél `#page=N`, a Basesnél a nézet neve. */
export function beagyazottRajzol(kont: HTMLElement, ut: string, subpath: string | undefined, canvasUt: string): () => void {
  const vezerlo = new AbortController();
  const alcel = subpath?.replace(/^#/, '') || null;
  const doboz = document.createElement('div');
  doboz.className = 'kartya-beagyazott';
  doboz.appendChild(
    beagyazasElem(
      { cel: ut, alcel, alias: null, beagyazas: true, from: 0, to: 0 },
      { forras: canvasUt, lanc: [{ ut: canvasUt, alcel: null }], melyseg: 0, kompakt: false, jel: vezerlo.signal, sor: kartyaSor },
    ),
  );
  kont.replaceChildren(doboz);
  const le = beagyazasFrissitesFigyel(doboz);
  return () => { le(); vezerlo.abort(); };
}

/** Kép a megjelenített szélességnek megfelelő vödörrel (`?w=`); a `kepernyoSzel` a kártya képernyőn mért szélessége. */
export function kepRajzol(kont: HTMLElement, ut: string, kepernyoSzel: number): () => void {
  let el = true;
  const img = document.createElement('img');
  img.className = 'kartya-kep';
  img.alt = fajlNev(ut);
  img.decoding = 'async';
  img.draggable = false;
  kont.replaceChildren(img);
  void linkek.mediaUrl(ut, kepVodor(kepernyoSzel, window.devicePixelRatio || 1)).then((u) => {
    if (el) img.src = u;
  });
  return () => {
    el = false;
  };
}

export function mediaRajzol(kont: HTMLElement, ut: string, tipus: 'video' | 'hang'): () => void {
  let el = true;
  const m = document.createElement(tipus === 'video' ? 'video' : 'audio');
  m.className = tipus === 'video' ? 'kartya-video' : 'kartya-hang';
  m.controls = true;
  m.preload = 'metadata';
  kont.replaceChildren(m);
  if (tipus === 'video') {
    // előnézet lejátszás előtt (E14): core-poszter + a WebKit első képkockája (`#t=0.001`)
    void linkek.posterUrl(ut).then((u) => {
      if (el) (m as HTMLVideoElement).poster = u;
    });
  }
  void linkek.mediaUrl(ut).then((u) => {
    if (el) m.src = tipus === 'video' ? `${u}#t=0.001` : u;
  });
  return () => {
    el = false;
    m.pause();
    m.removeAttribute('src');
  };
}

/** A link-kártya (D3: nincs hálózati kérés, nincs beágyazott oldal, nincs `iframe`): a domain és a teljes cím helyőrzőként, és
 *  egy kifejezett „Megnyitás a böngészőben” gomb, amely a rendszerböngészőben nyitja meg (csak `http`/`https`/`mailto`). */
export function linkRajzol(kont: HTMLElement, url: string): () => void {
  const d = document.createElement('div');
  d.className = 'kartya-link';
  const domain = document.createElement('span');
  domain.className = 'kartya-link-domain';
  const teljes = document.createElement('span');
  teljes.className = 'kartya-link-url';
  try {
    domain.textContent = new URL(url).hostname || url;
  } catch {
    domain.textContent = url || t('Üres link');
  }
  teljes.textContent = url;
  d.append(domain, teljes);
  if (url && kulsoCim(url)) {
    const b = document.createElement('button');
    b.type = 'button';
    b.className = 'kartya-link-nyit';
    const felirat = t('Open in browser');
    b.title = t('Opens the page in your system browser. Nothing is loaded in the canvas.');
    b.setAttribute('aria-label', `${felirat}: ${domain.textContent}`);
    b.append(ikonElem(ExternalLink, 14), document.createTextNode(felirat));
    b.addEventListener('click', (e) => {
      e.preventDefault();
      e.stopPropagation();
      kulsoLink(url);
    });
    d.append(b);
  }
  kont.replaceChildren(d);
  return () => {};
}
