// A kártyák tartalma (C14): DOM-rajzolók a kártya törzsébe. A szövegkártya az Olvasó rajzolójával (ugyanaz az
// elemző, mint a szerkesztőé), a jegyzetkártya a C10 beágyazás-motorjával (élő tartalom a core indexéből,
// körkörösség- és mélységvédelem), a kép a kicsinyített változattal (a megjelenített méret vödre), a hang és a
// videó natív elemmel. Minden rajzoló a lebontó függvényét adja vissza.

import { KeresSor } from '../lib/core/keresSor';
import { linkek } from '../lib/vault/linkek.svelte';
import { fajlNev, type FajlTipus } from '../lib/vault/fajlok.svelte';
import { beagyazasElem } from '../szerkeszto/beagyazas/rajzol';
import { kepVodor } from '../szerkeszto/beagyazas/nagyito';
import { obsidianElemzo } from '../szerkeszto/markdown/elemzo';
import { dokumentumRenderel } from '../szerkeszto/olvaso/html';
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

/** Markdown-szöveg az Olvasó tipográfiájával (a szövegkártya). */
export function szovegRajzol(kont: HTMLElement, szoveg: string, canvasUt: string): () => void {
  const lusta = LustaRajzolo.azonnali();
  const md = document.createElement('div');
  md.className = 'md tipo kartya-md';
  md.appendChild(
    dokumentumRenderel(obsidianElemzo.parse(szoveg), {
      olvas: (a, b) => szoveg.slice(a, b),
      ut: canvasUt,
      lusta,
      beagyazas: { lanc: [{ ut: canvasUt, alcel: null }], melyseg: 0 },
    }),
  );
  kont.replaceChildren(md);
  return () => lusta.leall();
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
  return () => vezerlo.abort();
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

/** A link-kártya: cím és domain (offline: nincs weboldal-előnézet). */
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
  kont.replaceChildren(d);
  return () => {};
}
