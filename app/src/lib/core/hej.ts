// A natív héj (Manifold.app) üzenetcsatornája: csak natív képességek (ARCHITECTURE 2., Héj ↔ felület).
// Böngészőben (fejlesztés, teszt) a hívás csendben elmarad.

export type HejUzenet =
  | { tipus: 'kesz' }
  // a munkaterület-választó (F5): a héj a vault-választó ablakot mutatja
  | { tipus: 'munkater-valaszto' }
  | { tipus: 'tema'; ertek: 'rendszer' | 'vilagos' | 'sotet' }
  | { tipus: 'megnyit'; url: string }
  // a naptár-engedély (C29): a héj a rendszer ablakát mutatja, és `window.manifold.naptarEngedely(…)`-val válaszol
  | { tipus: 'naptar-engedely'; esemeny: boolean; emlekezteto: boolean }
  | { tipus: 'naptar-allapot' }
  // a „leáll” réteg gombja (C29.7b): a héj a core-t azonnal leállítja és kilép (a második ⌘Q megfelelője)
  | { tipus: 'kenyszeritett-kilepes' }
  // a jegyzet natív helyi menüjének Manifold-parancsai (C32b): a lap a `contextmenu` esemény közben küldi, a héj a natív menü
  // végére fűzi (`willOpenMenu`), és a választást a `window.manifold.parancs(id)` hívással adja vissza
  // rendszerértesítés a macOS Értesítési központjába (E10): a héj az engedélyt az első küldés előtt kéri, az elutasítást tiszteli;
  // a kattintásra az app előre jön, és `window.manifold.ertesitesKattintas(azon)` fut. `kategoria`: 'hiba' | 'kesz' | 'jelzes'
  | { tipus: 'ertesites'; cim: string; szoveg: string; azon: string; kategoria: 'hiba' | 'kesz' | 'jelzes' }
  | { tipus: 'helyi-menu'; elemek: { id: string; nev: string; letiltva: boolean }[] };

interface WebkitAblak {
  webkit?: { messageHandlers?: { manifold?: { postMessage(u: unknown): void } } };
}

export function hejnek(u: HejUzenet): void {
  try {
    (window as unknown as WebkitAblak).webkit?.messageHandlers?.manifold?.postMessage(u);
  } catch {
    // a héj nélkül nincs kinek szólni
  }
}

export function hejbenFut(): boolean {
  return Boolean((window as unknown as WebkitAblak).webkit?.messageHandlers?.manifold);
}

/** A héj bejelentett képességei (a héj a lap betöltése előtt injektálja a `window.__MOS_HEJ__`-t): a régebbi héj nem hirdeti a
 *  `helyiMenu`-t, ezért a lap a saját menüjét tartja meg — a natív menü csak ott kapcsol be, ahol a héj tényleg fűzi a parancsokat. */
export function hejKepesseg(nev: 'helyiMenu'): boolean {
  return hejbenFut() && (window as unknown as { __MOS_HEJ__?: Record<string, unknown> }).__MOS_HEJ__?.[nev] === true;
}
