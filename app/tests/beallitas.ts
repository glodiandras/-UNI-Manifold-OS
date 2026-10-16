// A jsdom hiányzó böngésző-API-jai a komponenstesztekhez: matchMedia (csökkentett mozgás → 0 ms-os
// átmenetek) és Element.animate (a Svelte-átmenetek WAAPI-t használnak).
//
// A felület nyelve a tesztekben MAGYAR (F4): a `t()` a `hu` nyelven identitás (a kulcs maga a magyar szöveg), így a szöveg-assertek
// változatlanok. A termék alapnyelve az angol; a `globalThis`-jel a `vi.resetModules()` utáni friss modulpéldány is magyar marad.
import { nyelv } from '../src/lib/i18n/nyelv.svelte';

(globalThis as { __MANIFOLD_NYELV__?: string }).__MANIFOLD_NYELV__ = 'hu';
nyelv.beallit('hu');

if (typeof window !== 'undefined') {
  window.matchMedia ??= ((q: string) => ({
    matches: q.includes('prefers-reduced-motion'),
    media: q,
    onchange: null,
    addListener() {},
    removeListener() {},
    addEventListener() {},
    removeEventListener() {},
    dispatchEvent: () => false,
  })) as typeof window.matchMedia;

  Element.prototype.scrollIntoView ??= function () {}; // a jsdom nem görget (a fa és a keresőpanel sorra görget)

  Element.prototype.animate ??= function () {
    const a = {
      onfinish: null as null | (() => void),
      cancel() {},
      finish() {},
      play() {},
      pause() {},
      currentTime: 0,
      playState: 'finished',
      finished: Promise.resolve(),
      addEventListener() {},
      removeEventListener() {},
    };
    queueMicrotask(() => a.onfinish?.());
    return a as unknown as Animation;
  };
}

// A CodeMirror mérése (requestAnimationFrame) a jsdom-ban hiányzó Range-geometriát kéri.
if (typeof Range !== 'undefined') {
  Range.prototype.getClientRects ??= function () {
    return { length: 0, item: () => null, [Symbol.iterator]: function* () {} } as unknown as DOMRectList;
  };
  Range.prototype.getBoundingClientRect ??= () => new DOMRect();
}
