// A Bases a jegyzetben (C12): a ```` ```base ```` kódblokk és a `![[x.base]]` / `![[x.base#Nézet]]` beágyazás.
//
// - **Blokk**: interaktív kódblokk-renderelő (a Live Preview-ban a blokk saját vezérlőkkel él, a forrás a „Forrás”
//   gombbal nyílik; a blokk szövege a befoglaló jegyzet egyetlen tranzakciójával íródik). Az Olvasóban a rögzített
//   forrással rajzol (a beállítás csak memóriában változik).
// - **Beágyazás**: a `.base` fájl a `Dokumentum`-án át (a beállítás a fájlba íródik), a `this` a befoglaló jegyzet.
//   Sor közepén és a lebegő előnézetben csak link-chip.
//
// A `mount`-olt komponens nem örökli a Svelte-kontextust, ezért a környezet explicit átadódik.

import { mount, unmount } from 'svelte';
import { KORNYEZET_KULCS, type Kornyezet } from '../lib/kornyezet';
import { chip } from '../szerkeszto/beagyazas/rajzol';
import type { BeagyazasRenderelo } from '../szerkeszto/beagyazas/regiszter';
import type { KodRenderelo } from '../szerkeszto/renderelok/regiszter';
import BazisNezet from './BazisNezet.svelte';
import { blokkForras, fajlForras, type BlokkForras } from './forras';

function kontextus(k: Kornyezet): Map<unknown, unknown> {
  return new Map<unknown, unknown>([[KORNYEZET_KULCS, k]]);
}

/** Egy kirajzolt blokk forrása a `cel` elemhez kötve (a `frissit` ebből éri el). */
const FORRASOK = new WeakMap<HTMLElement, BlokkForras>();

export function bazisKodRenderelo(k: Kornyezet): KodRenderelo {
  return {
    nyelv: 'base',
    interaktiv: true,
    becsultMagassag: (forras) => Math.min(480, 130 + 30 * Math.max(3, forras.split('\n').length)),
    render(forras, cel, kk) {
      const f = blokkForras(kk.ut, forras, kk.blokk);
      FORRASOK.set(cel, f);
      cel.replaceChildren();
      const komp = mount(BazisNezet, {
        target: cel,
        props: { forras: f, kapcsolat: k.kapcsolat, kompakt: true, forrasGomb: kk.blokk ? () => kk.blokk!.forrasba() : undefined },
        context: kontextus(k),
      });
      return () => {
        void unmount(komp);
        FORRASOK.delete(cel);
        void f.lezar();
      };
    },
    frissit(cel, forras) {
      const f = FORRASOK.get(cel);
      if (!f) return false;
      f.beallit(forras);
      return true;
    },
  };
}

export function bazisBeagyazasRenderelo(k: Kornyezet): BeagyazasRenderelo {
  return {
    tipus: 'base',
    async render(adat, link, kont, o) {
      if (o.sorban || o.kompakt) return chip(adat, link, kont, o);
      const f = await fajlForras(adat.ut!, { ez: o.forras });
      if (o.jel?.aborted) {
        void f.lezar();
        return;
      }
      kont.className = 'beagyazas beagyazas-base';
      kont.style.display = 'block';
      kont.replaceChildren();
      const komp = mount(BazisNezet, {
        target: kont,
        props: { forras: f, kapcsolat: k.kapcsolat, kompakt: true, nezet: link.alcel ?? null },
        context: kontextus(k),
      });
      // a tartalom magassága a betöltés után változik: a Live Preview újramér
      let megfigyelo: ResizeObserver | null = null;
      if (typeof ResizeObserver !== 'undefined' && o.kesz) {
        megfigyelo = new ResizeObserver(() => o.kesz?.());
        megfigyelo.observe(kont);
      }
      const le = () => {
        megfigyelo?.disconnect();
        void unmount(komp);
        void f.lezar();
      };
      if (o.jel) o.jel.addEventListener('abort', le, { once: true });
    },
  };
}
