// A kvízjegyzet beágyazása (C22a): a `![[… — Kvíz …]]` a jegyzetben a jegyzet szövege helyett kitölthető blokk (a Live
// Preview és az Olvasó közös beágyazás-motorján át). A lebegő előnézet és a `#fejezet` beágyazás a jegyzet szövegét mutatja.
//
// A `mount`-olt komponens a Svelte-kontextust nem örökli; a kvíznek nincs szüksége a héj objektumaira: a core-ral a
// `kviz/api.ts`, a trackerrel a `trackerKliens` beszél.

import { mount, unmount } from 'svelte';
import { trackerKliens } from '../lib/tracker/kliens.svelte';
import type { JegyzetOsztalyRenderelo } from '../szerkeszto/beagyazas/regiszter';
import { kvizUt } from './allando';
import KvizBlokk from './KvizBlokk.svelte';
import { KvizMenet } from './menet.svelte';

export const kvizRenderelo: JegyzetOsztalyRenderelo = {
  id: 'kviz',
  illeszkedik: (adat) => adat.tipus === 'jegyzet' && kvizUt(adat.ut),
  render(adat, _link, kont, o) {
    kont.className = 'beagyazas beagyazas-kviz';
    kont.style.display = 'block';
    kont.replaceChildren();
    const menet = new KvizMenet(adat.ut!, { tracker: (ut, d) => trackerKliens.esemeny('kviz_eredmeny', ut, d) });
    const komp = mount(KvizBlokk, { target: kont, props: { menet, forras: o.forras } });
    // a tartalom magassága a kitöltés közben változik: a Live Preview újramér
    let megfigyelo: ResizeObserver | null = null;
    if (typeof ResizeObserver !== 'undefined' && o.kesz) {
      megfigyelo = new ResizeObserver(() => o.kesz?.());
      megfigyelo.observe(kont);
    }
    const le = () => {
      megfigyelo?.disconnect();
      void unmount(komp);
    };
    o.jel?.addEventListener('abort', le, { once: true });
    void menet.betolt();
  },
};
