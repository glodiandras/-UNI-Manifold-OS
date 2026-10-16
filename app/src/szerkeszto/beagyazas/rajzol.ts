// A beágyazás renderelése (C10): `![[…]]` és a lebegő előnézet közös motorja. A feloldást, a típust és a
// fejezet-/blokk-szeletet a core adja (`linkek.beagyazas`); itt DOM készül.
//
// Típusok: jegyzet (egész, `#fejezet`, `#^blokk`), kép (`|300`, `|300x200`), videó (`#t=` másodperc / `mm:ss`),
// hang, PDF (`#page=N`). A canvas/base/ismeretlen típus helyőrző-chip (a C12/C14/C16 regisztrál).
// **Körkörös beágyazás**: a render-láncban (`ut#alcel`) már szereplő cél helyett „Körkörös beágyazás” jelzés;
// a mélységkorlát 6. Hiányzó cél: halvány jelzés és létrehozás gomb.

import { t } from '../../lib/i18n';
import { modulEngedelyezett } from '../../lib/beallitasok/allapot.svelte';
import { ApiHiba } from '../../lib/core/api';
import { linkek, type BeagyazasAdat } from '../../lib/vault/linkek.svelte';
import { fajlNev } from '../../lib/vault/fajlok.svelte';
import { ikonElem } from '../../lib/ikon/ikonElem';
import { TriangleAlert } from '../../lib/ikon/ikonok';
import { szerkesztok } from '../szerkesztok.svelte';
import { obsidianElemzo } from '../markdown/elemzo';
import { dokumentumRenderel } from '../olvaso/html';
import { LustaRajzolo } from '../olvaso/lusta';
import { linkFelirat, mediaHorgony, meretAliasbol, type LinkAdat } from '../linkek/adat';
import { ISMERT_KITERJESZTES, jegyzetLetrehoz, linkMegnyit, nyitasMod } from '../linkek/navigacio';
import { kepetNagyit, kepVodor } from './nagyito';
import { beagyazottFeladatValt } from './feladat';
import { kulsoKepElem } from './kulsoKep';
import { beagyazasRenderelok, jegyzetOsztalyRenderelok, type BeagyazasOpciok, type LancElem } from './regiszter';

export const MAX_MELYSEG = 6;
const PDF_MAGASSAG = 520;

function el<K extends keyof HTMLElementTagNameMap>(tag: K, osztaly?: string): HTMLElementTagNameMap[K] {
  const e = document.createElement(tag);
  if (osztaly) e.className = osztaly;
  return e;
}

/** Körkörös-e a beágyazás: a lánc már tartalmazza ezt a célt pontosan, vagy az egész jegyzetet kérjük, amelynek
 *  bármely szelete a láncban áll (az egész tartalmazza a szeletet, a szelet a beágyazást). A jegyzet saját
 *  fejezetének beágyazása addig nem körkörös, amíg a lánc nem ismétlődik. */
export function korkoros(lanc: LancElem[], ut: string, alcel: string | null): boolean {
  return lanc.some((k) => k.ut === ut && (alcel === null || k.alcel === alcel));
}

function uzenet(kont: HTMLElement, osztaly: string, szoveg: string): HTMLElement {
  kont.className = `beagyazas ${osztaly}`;
  kont.replaceChildren();
  const s = el('span', 'beagyazas-uzenet');
  s.textContent = szoveg;
  kont.appendChild(s);
  return s;
}

/** Egy beágyazás-elem újrarajzolásához szükséges állapot (04-embeds-07: célonkénti frissítés). A `ac` az aktuális betöltés
 *  megszakítója; a szülő jele (`o.jel`) erre fut tovább, így az újrarajzolás az előző, félbemaradt betöltést eldobja. */
interface ElemAllapot {
  link: LinkAdat;
  o: BeagyazasOpciok;
  ac: AbortController | null;
  leiratkozas: (() => void) | null;
}
const allapotok = new WeakMap<HTMLElement, ElemAllapot>();

/** A beágyazás elem azonnal visszaadva; a tartalom aszinkron töltődik bele. */
export function beagyazasElem(link: LinkAdat, o: BeagyazasOpciok): HTMLElement {
  const kont = el('span', 'beagyazas beagyazas-betolt');
  kont.dataset.cel = link.cel;
  if (link.alcel) kont.dataset.alcel = link.alcel;
  kont.title = link.kulso ? link.cel : `![[${link.cel}${link.alcel ? '#' + link.alcel : ''}]]`;
  if (link.kulso) {
    // 04-embeds-02: külső kép — automatikus hálózati kérés nincs; letöltés csak kattintásra, a core-on át
    kulsoKepElem(kont, link, o, (ut) => beagyazasElem({ ...link, cel: ut, alcel: null, kulso: false }, o));
  } else {
    allapotok.set(kont, { link, o, ac: null, leiratkozas: null });
    inditas(kont);
  }
  return kont;
}

function inditas(kont: HTMLElement): void {
  const a = allapotok.get(kont);
  if (!a) return;
  a.ac?.abort();
  a.leiratkozas?.();
  const ac = new AbortController();
  a.ac = ac;
  a.leiratkozas = null;
  const szulo = a.o.jel;
  if (szulo) {
    if (szulo.aborted) ac.abort();
    else {
      const tovabb = () => ac.abort();
      szulo.addEventListener('abort', tovabb, { once: true });
      a.leiratkozas = () => szulo.removeEventListener('abort', tovabb);
    }
  }
  void betolt(kont, a.link, { ...a.o, jel: ac.signal });
}

/** Érinti-e a tartalmi esemény ezt az elemet: a feloldott célja (`data-ut`) változott, vagy még nincs feloldott célja (hiányzó
 *  cél, betöltési hiba — egy új alias vagy a cél megjelenése feloldhatja). A betöltés alatt álló elem nem indul újra. */
function erintett(e: HTMLElement, utak: ReadonlySet<string> | null): boolean {
  if (!allapotok.has(e) || e.classList.contains('beagyazas-betolt')) return false;
  if (utak === null) return true;
  const ut = e.dataset.ut;
  return ut ? utak.has(ut) : true;
}

/** A `gyoker` alatti, a változás által érintett beágyazások újrarajzolása (a legkülső érintett elem; a belsőt az viszi).
 *  A nem érintett beágyazás DOM-ja (görgetés, lejátszó, PDF-oldal) megmarad. → az újrarajzolt elemek száma. */
export function beagyazasokFrissit(gyoker: HTMLElement, utak: ReadonlySet<string> | null): number {
  const jeloltek = [...(gyoker.matches('.beagyazas') ? [gyoker] : []), ...gyoker.querySelectorAll<HTMLElement>('.beagyazas')]
    .filter((e) => erintett(e, utak));
  const legkulso = jeloltek.filter((e) => !jeloltek.some((m) => m !== e && m.contains(e)));
  for (const e of legkulso) inditas(e);
  return legkulso.length;
}

/** A `gyoker` beágyazásai a saját céljuk tartalmi eseményére frissülnek (Olvasó, canvas-kártya). → leiratkozás. */
export function beagyazasFrissitesFigyel(gyoker: HTMLElement): () => void {
  return linkek.tartalomFigyel((utak) => { beagyazasokFrissit(gyoker, utak); });
}

async function betolt(kont: HTMLElement, link: LinkAdat, o: BeagyazasOpciok): Promise<void> {
  const lanc = o.lanc ?? [{ ut: o.forras, alcel: null }];
  const melyseg = o.melyseg ?? 0;
  const kesz = () => {
    if (!o.jel?.aborted) o.kesz?.();
  };
  let adat: BeagyazasAdat;
  try {
    const leker = () => linkek.beagyazas(o.forras, link.cel || o.forras, link.alcel);
    adat = await (o.sor ? o.sor.futtat(leker, o.jel) : leker());
  } catch (e) {
    if (o.jel?.aborted) return;
    delete kont.dataset.ut;
    uzenet(kont, 'beagyazas-hiba', t('A beágyazás nem tölthető be: {hiba}', { hiba: e instanceof ApiHiba ? e.message : String(e) }));
    kesz();
    return;
  }
  if (o.jel?.aborted) return;
  kont.classList.remove('beagyazas-betolt');
  if (adat.ut) kont.dataset.ut = adat.ut;
  else delete kont.dataset.ut;
  try {
    const modul = adat.tipus === 'pdf' ? 'pdf' : adat.tipus === 'base' ? 'bazis' : adat.tipus === 'canvas' ? 'canvas' :
      adat.tipus === 'video' || adat.tipus === 'hang' ? 'media' : null;
    if (modul && !modulEngedelyezett(modul)) {
      chip(adat, link, kont, o);
    } else if (adat.tipus === 'nincs' || !adat.ut) {
      hianyzo(kont, link, o);
    } else if (adat.tipus === 'jegyzet' && o.sorban) {
      chip(adat, link, kont, o);
    } else if (adat.tipus === 'jegyzet') {
      if (korkoros(lanc, adat.ut, link.alcel)) {
        const utvonal = [...lanc.map((k) => fajlNev(k.ut)), fajlNev(adat.ut)].join(' → ');
        uzenet(kont, 'beagyazas-hiba', t('Körkörös beágyazás: {utvonal}', { utvonal }));
      } else if (melyseg >= MAX_MELYSEG) {
        uzenet(kont, 'beagyazas-hiba', t('Túl mély beágyazás'));
      } else {
        const osztaly = !o.kompakt && !link.alcel ? jegyzetOsztalyRenderelok.keres(adat, link) : undefined;
        if (osztaly) await osztaly.render(adat, link, kont, o);        // a kísérőjegyzet (kvíz, kártyapakli) interaktív blokk
        else jegyzet(kont, adat, link, o, [...lanc, { ut: adat.ut, alcel: link.alcel }], melyseg);
      }
    } else {
      const r = beagyazasRenderelok.keres(adat.tipus) ?? alapRenderelo(adat.tipus);
      await r.render(adat, link, kont, o);
    }
  } catch (e) {
    uzenet(kont, 'beagyazas-hiba', t('A beágyazás nem rajzolható: {hiba}', { hiba: e instanceof Error ? e.message : String(e) }));
  }
  kesz();
}

// ---------------------------------------------------------------------- hiányzó cél

function hianyzo(kont: HTMLElement, link: LinkAdat, o: BeagyazasOpciok): void {
  kont.className = 'beagyazas beagyazas-hianyzo';
  kont.replaceChildren();
  const s = el('span', 'beagyazas-uzenet');
  s.textContent = t('Nem található: {cel}', { cel: link.cel });
  kont.appendChild(s);
  if (!ISMERT_KITERJESZTES.test(link.cel)) {
    const b = el('button', 'beagyazas-letrehoz');
    b.type = 'button';
    b.textContent = t('Létrehozás');
    b.addEventListener('click', async (ev) => {
      ev.preventDefault();
      ev.stopPropagation();
      const ut = await jegyzetLetrehoz(o.forras, link.cel);
      if (ut) {
        const cim = el('span', 'beagyazas-uzenet');
        cim.textContent = t('Létrehozva: {nev}', { nev: fajlNev(ut) });
        kont.replaceChildren(cim);
      }
    });
    kont.appendChild(b);
  }
}

// ---------------------------------------------------------------------- jegyzet

function jegyzet(kont: HTMLElement, adat: BeagyazasAdat, link: LinkAdat, o: BeagyazasOpciok, lanc: LancElem[], melyseg: number): void {
  kont.className = 'beagyazas beagyazas-jegyzet';
  kont.replaceChildren();
  if (adat.alcel_hiba) {
    const s = el('span', 'beagyazas-uzenet');
    s.textContent = t('Nem található: {nev}#{alcel}', { nev: fajlNev(adat.ut!), alcel: link.alcel ?? '' });
    kont.className = 'beagyazas beagyazas-hianyzo';
    kont.appendChild(s);
    return;
  }
  if (!o.kompakt) {
    const fej = el('a', 'beagyazas-cim');
    fej.setAttribute('role', 'link');
    fej.tabIndex = 0;
    fej.textContent = fajlNev(adat.ut!) + (link.alcel ? ` › ${link.alcel}` : '');
    const nyit = (e: MouseEvent | KeyboardEvent) => {
      e.preventDefault();
      e.stopPropagation();
      void linkMegnyit({ forras: o.forras, cel: link.cel, alcel: link.alcel }, nyitasMod(e));
    };
    fej.addEventListener('click', nyit);
    fej.addEventListener('auxclick', (e) => {
      if (e.button === 1) nyit(e); // középső gomb: új fül (02-links-08)
    });
    fej.addEventListener('keydown', (e) => {
      if (e.key === 'Enter') nyit(e);
    });
    kont.appendChild(fej);
  }
  const torzs = el('div', 'beagyazas-torzs md tipo');
  const szoveg = adat.szoveg ?? '';
  const fa = obsidianElemzo.parse(szoveg);
  torzs.appendChild(
    dokumentumRenderel(fa, {
      olvas: (a, b) => szoveg.slice(a, b),
      ut: adat.ut!,
      lusta: LustaRajzolo.azonnali(o.jel),
      elotag: `be${Math.random().toString(36).slice(2, 7)}`,
      beagyazas: { lanc, melyseg: melyseg + 1, kesz: o.kesz },
      csakOlvashato: o.csakOlvashato || o.kompakt,
    }),
  );
  feladatokKapcsol(torzs, adat, szoveg, o);
  if (!szoveg.trim()) {
    const u = el('span', 'beagyazas-uzenet');
    u.textContent = t('A jegyzet üres.');
    torzs.appendChild(u);
  }
  kont.appendChild(torzs);
}

function feladatokKapcsol(torzs: HTMLElement, adat: BeagyazasAdat, szoveg: string, o: BeagyazasOpciok): void {
  const kezd = adat.kezd;
  const szerkesztheto = !o.csakOlvashato && !o.kompakt && Number.isSafeInteger(kezd) && kezd! >= 1;
  // Csak a közvetlenül ebben a szeletben álló jelölők; a belső beágyazásnak saját kezelője van.
  for (const jel of torzs.querySelectorAll<HTMLInputElement>('input.feladat-jelolo')) {
    jel.disabled = !szerkesztheto;
    if (!szerkesztheto) jel.title = t('A feladatot a forrásjegyzetben szerkesztheted.');
  }
  let szelet = szoveg;
  let hiba: HTMLElement | null = null;
  torzs.addEventListener('change', (ev) => {
    const jel = ev.target as HTMLInputElement;
    if (!jel.matches('input.feladat-jelolo') || jel.closest('.beagyazas-torzs') !== torzs) return;
    ev.stopPropagation();
    const elozo = !jel.checked;
    if (!szerkesztheto || o.jel?.aborted) { jel.checked = elozo; return; }
    jel.disabled = true;
    void (async () => {
      let atirva = false;
      try {
        const d = await szerkesztok.dokumentumok.megnyit(adat.ut!);
        if (!d.mentetlen) await d.kulsoValtozas();
        if (o.jel?.aborted) { jel.checked = elozo; return; }
        const uj = beagyazottFeladatValt(d, kezd!, szelet, Number(jel.dataset.jelolo));
        if (uj === null) throw new Error(t('A beágyazott rész megváltozott. Nyisd meg a forrásjegyzetet, és próbáld újra.'));
        szelet = uj;
        atirva = true;
        const eredmeny = await d.ment({ pillanat: d.nezetSzam === 0 });
        if (!eredmeny.ok) throw new Error(t('A feladat mentése nem sikerült. A változás megvan; nyisd meg a forrásjegyzetet.'));
        hiba?.remove();
        hiba = null;
      } catch (e) {
        if (!atirva) jel.checked = elozo;
        if (!o.jel?.aborted) {
          hiba ??= el('span', 'beagyazas-feladat-hiba');
          hiba.setAttribute('role', 'status');
          hiba.replaceChildren(ikonElem(TriangleAlert, 14), document.createTextNode(e instanceof Error ? e.message : String(e)));
          torzs.appendChild(hiba);
          o.kesz?.();
        }
      } finally {
        jel.disabled = false;
      }
    })();
  });
}

// ---------------------------------------------------------------------- média és helyőrző

function alapRenderelo(tipus: BeagyazasAdat['tipus']) {
  switch (tipus) {
    case 'kep':
      return { tipus, render: kep };
    case 'video':
      return { tipus, render: video };
    case 'hang':
      return { tipus, render: hang };
    case 'pdf':
      return { tipus, render: pdf };
    default:
      return { tipus, render: chip };
  }
}

/** A kép megjelenítési szélessége (CSS px): a méretalias, különben a tartalom sávjának szélessége (a konténer a
 *  beszúrás pillanatában még nem biztos, hogy a DOM-ban áll: tartalék 800). */
function megjelenitettSzelesseg(kont: HTMLElement, meret: { szelesseg?: number } | null): number {
  if (meret?.szelesseg) return meret.szelesseg;
  const hely = kont.closest<HTMLElement>('.cm-line, .md, .link-elonezet-tartalom') ?? kont.parentElement;
  return hely?.clientWidth || 800;
}

/** Az eredeti kép nagyítása (kattintásra): a `w` nélküli média-URL, a nézegetőben. */
async function nagyitas(ut: string, img: HTMLElement): Promise<void> {
  kepetNagyit(await linkek.mediaUrl(ut), img.getAttribute('alt') ?? fajlNev(ut), img);
}

async function kep(adat: BeagyazasAdat, link: LinkAdat, kont: HTMLElement, o: BeagyazasOpciok): Promise<void> {
  const img = el('img', 'beagyazas-kep');
  const meret = meretAliasbol(link.alias);
  img.alt = link.alt ?? (!meret && link.alias ? link.alias : fajlNev(adat.ut!));
  img.loading = 'lazy';
  img.decoding = 'async'; // a dekódolás ne a fő szálon (a kicsinyített változat mellett is)
  if (meret?.szelesseg) img.width = meret.szelesseg;
  if (meret?.magassag) img.height = meret.magassag;
  img.addEventListener('load', () => o.kesz?.());
  img.addEventListener('error', () => {
    uzenet(kont, 'beagyazas-hiba', t('A kép nem tölthető be: {nev}', { nev: fajlNev(adat.ut!) }));
    o.kesz?.();
  });
  // a jegyzetben a megjelenített szélességnek megfelelő, kicsinyített változat (audit M9); az eredeti csak kattintásra
  const w = kepVodor(megjelenitettSzelesseg(kont, meret), window.devicePixelRatio || 1);
  img.src = await linkek.mediaUrl(adat.ut!, w);
  img.tabIndex = 0;
  img.setAttribute('role', 'button');
  img.setAttribute('aria-label', t('Kép nagyítása: {alt}', { alt: img.alt }));
  img.addEventListener('click', (e) => {
    e.preventDefault();
    void nagyitas(adat.ut!, img);
  });
  img.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' || e.key === ' ') {
      e.preventDefault();
      void nagyitas(adat.ut!, img);
    }
  });
  kont.className = 'beagyazas beagyazas-media';
  kont.replaceChildren(img);
}

/** A `#t=` nélküli videó kezdőpontja: a WebKit így az első képkockát mutatja, nem csak a lejátszás gombot. */
export const ELSO_KOCKA_MP = 0.001;

async function video(adat: BeagyazasAdat, link: LinkAdat, kont: HTMLElement, o: BeagyazasOpciok): Promise<void> {
  const v = el('video', 'beagyazas-video');
  v.controls = true;
  v.preload = 'metadata';
  v.setAttribute('playsinline', '');
  const { t } = mediaHorgony(link.alcel);
  const meret = meretAliasbol(link.alias);
  if (meret?.szelesseg) v.width = meret.szelesseg;
  // előnézet lejátszás előtt (E14): a `#t=0.001` miatt a WebKit kirajzolja az első képkockát, a core-poszter (ffmpeg) ezt
  // erősíti meg; ha a poszter nem készül (404), a `<video>` az első képkockára esik vissza
  v.poster = await linkek.posterUrl(adat.ut!, t || undefined);
  v.src = (await linkek.mediaUrl(adat.ut!)) + `#t=${t || ELSO_KOCKA_MP}`;
  if (t)
    v.addEventListener('loadedmetadata', () => {
      if (Math.abs(v.currentTime - t) > 1) v.currentTime = t;
    });
  v.addEventListener('loadedmetadata', () => o.kesz?.());
  kont.className = 'beagyazas beagyazas-media';
  kont.replaceChildren(v);
}

async function hang(adat: BeagyazasAdat, link: LinkAdat, kont: HTMLElement): Promise<void> {
  const a = el('audio', 'beagyazas-hang');
  a.controls = true;
  a.preload = 'metadata';
  const { t } = mediaHorgony(link.alcel);
  a.src = (await linkek.mediaUrl(adat.ut!)) + (t ? `#t=${t}` : '');
  kont.className = 'beagyazas beagyazas-media';
  kont.replaceChildren(a);
}

async function pdf(adat: BeagyazasAdat, link: LinkAdat, kont: HTMLElement): Promise<void> {
  const f = el('iframe', 'beagyazas-pdf');
  const { page, height } = mediaHorgony(link.alcel);
  const meret = meretAliasbol(link.alias);
  f.title = `${fajlNev(adat.ut!)}${page ? `, ${page}. oldal` : ''}`;
  f.loading = 'lazy';
  f.style.height = `${height ?? meret?.szelesseg ?? PDF_MAGASSAG}px`;
  f.src = (await linkek.mediaUrl(adat.ut!)) + (page ? `#page=${page}` : '');
  kont.className = 'beagyazas beagyazas-media';
  kont.replaceChildren(f);
}

export function chip(adat: BeagyazasAdat, link: LinkAdat, kont: HTMLElement, o: BeagyazasOpciok): void {
  kont.className = 'beagyazas beagyazas-chip';
  kont.replaceChildren();
  const a = el('a', 'beagyazas-cim');
  a.setAttribute('role', 'link');
  a.tabIndex = 0;
  a.textContent = linkFelirat({ ...link, alias: null }) || fajlNev(adat.ut!);
  const nyit = (e: MouseEvent | KeyboardEvent) => {
    e.preventDefault();
    e.stopPropagation();
    void linkMegnyit({ forras: o.forras, cel: link.cel, alcel: link.alcel }, nyitasMod(e));
  };
  a.addEventListener('click', nyit);
  a.addEventListener('auxclick', (e) => {
    if (e.button === 1) nyit(e); // középső gomb: új fül (02-links-08)
  });
  a.addEventListener('keydown', (e) => {
    if (e.key === 'Enter') nyit(e);
  });
  kont.appendChild(a);
}
