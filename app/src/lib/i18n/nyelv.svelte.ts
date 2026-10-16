// A felület nyelve (F4, PLAN P2): egyetlen reaktív érték. A termék alapnyelve az angol; a tesztek a `tests/beallitas.ts`-ben
// `hu`-ra állítják (a `hu` identitás: a kulcs maga a magyar szöveg, így a ~1 700 szöveg-assert változatlan marad).
//
// A mentett nyelv a `felulet.json` `nyelv` kulcsából jön (`nyelvBetolt`, a `main.ts` hívja a mount előtt); ismeretlen vagy
// hiányzó érték: az alapnyelv. A `<html lang>` a váltással együtt állítódik (képernyőolvasó, helyesírás-ellenőrzés).

export type Nyelv = 'hu' | 'en';

/** A támogatott felületi nyelvek; új nyelv = ide egy kód + egy `en/` mintájú `lib/i18n/<kód>/` szótármappa. */
export const NYELVEK: readonly Nyelv[] = ['hu', 'en'];

/** A termék alapnyelve (PLAN P2: csak angol az első verzióban). */
export const ALAP_NYELV: Nyelv = 'en';

/** Az `Intl.*` hívások nyelvi címkéje nyelvenként (dátum, szám, rendezés): a magyar a korábbi `hu-HU`; az angol 24 órás, nap-hónap
 *  sorrendű (en-GB), mert a naptár és az óra-formátum a hétfő-első, 24 órás elrendezéshez készült. */
const LOCALE: Record<Nyelv, string> = { hu: 'hu-HU', en: 'en-GB' };

export function nyelvKod(x: unknown): Nyelv | null {
  return typeof x === 'string' && (NYELVEK as readonly string[]).includes(x) ? (x as Nyelv) : null;
}

/** A tesztek alapnyelve: a `tests/beallitas.ts` a `globalThis`-re teszi (`hu`), így a `vi.resetModules()` utáni friss modulpéldány is
 *  magyar. A termékben nincs ilyen érték: az alapnyelv az angol. */
const INDULO: Nyelv = nyelvKod((globalThis as { __MANIFOLD_NYELV__?: unknown }).__MANIFOLD_NYELV__) ?? ALAP_NYELV;

export class NyelvAllapot {
  /** Az aktív felületi nyelv; a `t()`/`tp()` ezt olvassa, így a Svelte magától újrarajzol. */
  kod = $state<Nyelv>(INDULO);

  /** Az `Intl.DateTimeFormat` / `Intl.NumberFormat` / `Intl.Collator` nyelvi címkéje (a hívás helyén, hogy váltáskor frissüljön). */
  get locale(): string {
    return LOCALE[this.kod];
  }

  /** Nyelv beállítása; ismeretlen kódra nem változik (hamisat ad). A `<html lang>` is követi. */
  beallit(kod: unknown): boolean {
    const k = nyelvKod(kod);
    if (!k) return false;
    this.kod = k;
    if (typeof document !== 'undefined') document.documentElement.lang = k;
    return true;
  }
}

export const nyelv = new NyelvAllapot();

/** A mentett felület-állapotból (`felulet.json`) a `nyelv` kulcs; hiányzó vagy ismeretlen érték: az alapnyelv marad. */
export function nyelvBetolt(allapot: unknown): Nyelv {
  const mentett = allapot && typeof allapot === 'object' ? (allapot as { nyelv?: unknown }).nyelv : undefined;
  nyelv.beallit(nyelvKod(mentett) ?? ALAP_NYELV);
  return nyelv.kod;
}
