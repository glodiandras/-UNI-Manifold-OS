// A kártya-kísérőjegyzet beágyazása (C23b): a `![[… — kártyák]]` a jegyzetben (a `## Gyakorlás` alatt) a jegyzet szövege
// helyett interaktív pakli — a kísérőjegyzet esedékes kártyái (a Live Preview és az Olvasó közös beágyazás-motorján át).
// Az Obsidianban ugyanez olvasható szöveg marad (összecsukott `[!card]-` calloutok).

import { mount, unmount } from 'svelte';
import { trackerKliens } from '../lib/tracker/kliens.svelte';
import type { JegyzetOsztalyRenderelo } from '../szerkeszto/beagyazas/regiszter';
import { kartyaUt } from './allando';
import { IsmetlesMenet } from './menet.svelte';
import Pakli from './Pakli.svelte';

export function trackerKuld(ut: string | null, adat: { jegy: number; kartya_id: string; ms?: number }): void {
  trackerKliens.esemeny('kartya_valasz', ut ?? undefined, adat);
}

export const kartyaRenderelo: JegyzetOsztalyRenderelo = {
  id: 'kartya',
  illeszkedik: (adat) => adat.tipus === 'jegyzet' && kartyaUt(adat.ut),
  render(adat, _link, kont, o) {
    kont.className = 'beagyazas beagyazas-kartya';
    kont.style.display = 'block';
    kont.replaceChildren();
    const menet = new IsmetlesMenet({ tipus: 'pakli', ut: adat.ut! }, { tracker: trackerKuld });
    const cim = (adat.ut ?? '').split('/').at(-1)?.replace(/\.md$/i, '') ?? '';
    const komp = mount(Pakli, { target: kont, props: { menet, forras: o.forras, cim } });
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
