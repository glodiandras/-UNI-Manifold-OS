// A „leáll” állapot (C29.7b, T121): a héj kilépéskor a `window.manifold.mentes()`-t hívja, és a core leállásáig vár. Ez
// alatt a felület nem szerkeszthető — a mentés után begépelt szöveg a core leállásával elveszne, és nem volna második
// mentés. A `mentes()` maga kapcsolja be (a héj nem felejtheti el), a héj a szöveget frissíti (`leallAllapot`), és a
// „Vissza a szerkesztéshez” ágon visszavonja (`null`). A megjelenítés a `hej/LeallVedelem.svelte`.

class LeallAllapot {
  /** A jelzőn látszó állapotszöveg; `null`: nincs leállás. */
  szoveg = $state<string | null>(null);

  get aktiv(): boolean {
    return this.szoveg !== null;
  }

  be(szoveg: string): void {
    this.szoveg = szoveg;
  }

  ki(): void {
    this.szoveg = null;
  }
}

export const leall = new LeallAllapot();
