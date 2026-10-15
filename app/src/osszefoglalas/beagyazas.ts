// Az összefoglaló-kísérőjegyzet beágyazása (C26b): a `![[… — összefoglaló]]` a jegyzetben (a `## Gyakorlás` alatt) a jegyzet
// szövege helyett az állítások és a forrás-linkek, sodródás-jelzéssel (a Live Preview és az Olvasó közös beágyazás-motorján át).
// Az Obsidianban ugyanez olvasható szöveg marad (számozott lista, behúzott idézettel). A lebegő előnézet és a `#fejezet`
// beágyazás a jegyzet szövegét mutatja.

import { mount, unmount } from 'svelte';
import type { JegyzetOsztalyRenderelo } from '../szerkeszto/beagyazas/regiszter';
import { osszefoglaloUt } from './allando';
import Osszefoglalo from './Osszefoglalo.svelte';

export const osszefoglaloRenderelo: JegyzetOsztalyRenderelo = {
  id: 'osszefoglalo',
  illeszkedik: (adat) => adat.tipus === 'jegyzet' && osszefoglaloUt(adat.ut),
  render(adat, _link, kont, o) {
    kont.className = 'beagyazas beagyazas-osszefoglalo';
    kont.style.display = 'block';
    kont.replaceChildren();
    const ut = adat.ut!;
    const cim = ut.split('/').at(-1)?.replace(/\.md$/i, '') ?? '';
    const komp = mount(Osszefoglalo, { target: kont, props: { ut, forras: o.forras, cim } });
    // a tartalom magassága a betöltés és az idézetek nyitása közben változik: a Live Preview újramér
    let megfigyelo: ResizeObserver | null = null;
    if (typeof ResizeObserver !== 'undefined' && o.kesz) {
      megfigyelo = new ResizeObserver(() => o.kesz?.());
      megfigyelo.observe(kont);
    }
    o.jel?.addEventListener(
      'abort',
      () => {
        megfigyelo?.disconnect();
        void unmount(komp);
      },
      { once: true },
    );
  },
};
