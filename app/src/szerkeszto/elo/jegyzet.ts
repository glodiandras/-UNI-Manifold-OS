// A szerkesztett jegyzet vault-relatív útja a CodeMirror-állapotban (a kódblokk-renderelők kapják meg).

import { Facet } from '@codemirror/state';

export const jegyzetUtja = Facet.define<string | null, string | null>({
  combine: (ertekek) => ertekek[0] ?? null,
});
