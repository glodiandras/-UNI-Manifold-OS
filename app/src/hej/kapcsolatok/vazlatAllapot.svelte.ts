// A Vázlat összecsukott fejezetei jegyzetenként (11-graph-06): csak memóriában él (nem kerül a felület mentésébe), a
// jegyzetek közti váltás után is megmarad. A kulcs a fejezet szintje, szövege és előfordulása (`szerkeszto/vazlat.ts`), így a
// szintváltozás új kulcsot ad, és az állapot magától elavul. A jegyzetek száma korlátos.

import { SvelteMap } from 'svelte/reactivity';

const MAX_JEGYZET = 200;
const URES: ReadonlySet<string> = new Set();

class VazlatAllapot {
  private readonly m = new SvelteMap<string, ReadonlySet<string>>();

  kap(ut: string): ReadonlySet<string> {
    return this.m.get(ut) ?? URES;
  }

  allit(ut: string, kulcsok: Iterable<string>): void {
    const s = new Set(kulcsok);
    this.m.delete(ut); // a legfrissebb a map végére kerül (a korlát a legrégebbit dobja)
    if (!s.size) return;
    this.m.set(ut, s);
    while (this.m.size > MAX_JEGYZET) this.m.delete(this.m.keys().next().value as string);
  }

  valt(ut: string, kulcs: string): void {
    const s = new Set(this.kap(ut));
    if (!s.delete(kulcs)) s.add(kulcs);
    this.allit(ut, s);
  }

  torol(): void {
    this.m.clear();
  }
}

export const vazlatAllapot = new VazlatAllapot();
