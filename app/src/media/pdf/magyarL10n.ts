// A pdf.js néző magyar akadálymentes címkéi (C32b): saját `l10n` a `GenericL10n` angol tartaléka helyett. A pdf.js a nézőben és a
// jegyzet-rétegben (oldal-tájoló, megjegyzés-ikon, dátum, szerkesztő-címkék) `data-l10n-id` attribútumokkal kér szöveget; a
// `GenericL10n` a `locale/<nyelv>/viewer.ftl`-t kérné a hálózatról (nincs: offline), így angol marad. Itt az interfész (a viewer a
// `l10n.translate/get/pause/resume/destroy` hívásokat használja) kis, helyi megvalósítása áll, Fluent-elemző nélkül: egy tábla
// azonosító → érték és attribútumok. A tábla lefedettségét teszt őrzi a vendorált könyvtár azonosítóira (`magyar-l10n.test.ts`):
// egy új pdf.js új azonosítót hozva a teszt elbukik, amíg nincs lefordítva vagy a kivétel-listán. Hálózat, eval, script nincs.

import { locale, nyelv, t, tk } from '../../lib/i18n';

type Args = Record<string, unknown>;
type Szoveg = string | ((a: Args) => string);

interface Bejegyzes {
  ertek?: Szoveg;
  attr?: Record<string, Szoveg>;
}

const ANNOTACIO_TIPUS: Record<string, string> = {
  Comment: tk('Megjegyzés'),
  Key: tk('Kulcs'),
  Note: tk('Jegyzet'),
  Help: tk('Súgó'),
  NewParagraph: tk('Új bekezdés'),
  Paragraph: tk('Bekezdés'),
  Insert: tk('Beszúrás'),
};

const datumIdo = (a: Args): string => {
  const d = new Date(Number(a.dateObj));
  return Number.isNaN(d.getTime()) ? '' : new Intl.DateTimeFormat(locale(), { dateStyle: 'short', timeStyle: 'medium' }).format(d);
};

const cimke = (aria: Szoveg): Bejegyzes => ({ attr: { 'aria-label': aria } });
const cim = (t: Szoveg): Bejegyzes => ({ attr: { title: t } });
const cimEsCimke = (t: Szoveg): Bejegyzes => ({ attr: { title: t, 'aria-label': t } });

/** Azonosító → magyar szöveg (a pdf.js `viewer.ftl` angol szövegeinek párja; csak a néző és a jegyzet-réteg azonosítói). */
export const MAGYAR: Readonly<Record<string, Bejegyzes>> = {
  'pdfjs-page-landmark': cimke((a) => t('{page}. oldal', { page: String(a.page ?? '') })),
  'pdfjs-text-annotation-type': { attr: { alt: (a) => t('[{tipus} megjegyzés]', { tipus: ANNOTACIO_TIPUS[String(a.type)] ? t(ANNOTACIO_TIPUS[String(a.type)]) : String(a.type) }) } },
  'pdfjs-annotation-date-time-string': { ertek: datumIdo },
  'pdfjs-show-comment-button': cim(tk('Megjegyzés megjelenítése')),
  'pdfjs-comment-floating-button': cimEsCimke(tk('Megjegyzés')),
  'pdfjs-comment-floating-button-label': { ertek: tk('Megjegyzés') },
  'pdfjs-highlight-floating-button1': cimEsCimke(tk('Kiemelés')),
  'pdfjs-highlight-floating-button-label': { ertek: tk('Kiemelés') },
  'pdfjs-editor-add-comment-button': cim(tk('Megjegyzés hozzáadása')),
  'pdfjs-free-text2': { attr: { 'aria-label': tk('Szövegszerkesztő'), 'default-content': tk('Kezdj el gépelni…') } },
  'pdfjs-editor-highlight-editor': cimke(tk('Kiemelés-szerkesztő')),
  'pdfjs-editor-ink-editor': cimke(tk('Rajz-szerkesztő')),
  'pdfjs-editor-stamp-editor': cimke(tk('Kép-szerkesztő')),
  'pdfjs-editor-signature-editor1': { attr: { 'aria-description': (a) => t('Aláírás-szerkesztő: {leiras}', { leiras: String(a.description ?? '') }) } },
  'pdfjs-editor-remove-ink-button': cim(tk('Rajz eltávolítása')),
  'pdfjs-editor-remove-freetext-button': cim(tk('Szöveg eltávolítása')),
  'pdfjs-editor-remove-stamp-button': cim(tk('Kép eltávolítása')),
  'pdfjs-editor-remove-highlight-button': cim(tk('Kiemelés eltávolítása')),
  'pdfjs-editor-remove-signature-button': cim(tk('Aláírás eltávolítása')),
  'pdfjs-editor-color-picker-free-text-input': cim(tk('Szövegszín módosítása')),
  'pdfjs-editor-color-picker-ink-input': cim(tk('Rajzszín módosítása')),
  'pdfjs-editor-colorpicker-button': cim(tk('Szín módosítása')),
  'pdfjs-editor-colorpicker-dropdown': cimke(tk('Színek')),
  'pdfjs-editor-colorpicker-yellow': cim(tk('Sárga')),
  'pdfjs-editor-colorpicker-green': cim(tk('Zöld')),
  'pdfjs-editor-colorpicker-blue': cim(tk('Kék')),
  'pdfjs-editor-colorpicker-pink': cim(tk('Rózsaszín')),
  'pdfjs-editor-colorpicker-red': cim(tk('Piros')),
  'pdfjs-editor-resizer-top-left': cimke(tk('Bal felső sarok — átméretezés')),
  'pdfjs-editor-resizer-top-middle': cimke(tk('Felső közép — átméretezés')),
  'pdfjs-editor-resizer-top-right': cimke(tk('Jobb felső sarok — átméretezés')),
  'pdfjs-editor-resizer-middle-right': cimke(tk('Jobb közép — átméretezés')),
  'pdfjs-editor-resizer-bottom-right': cimke(tk('Jobb alsó sarok — átméretezés')),
  'pdfjs-editor-resizer-bottom-middle': cimke(tk('Alsó közép — átméretezés')),
  'pdfjs-editor-resizer-bottom-left': cimke(tk('Bal alsó sarok — átméretezés')),
  'pdfjs-editor-resizer-middle-left': cimke(tk('Bal közép — átméretezés')),
  'pdfjs-editor-highlight-added-alert': { ertek: tk('Kiemelés hozzáadva') },
  'pdfjs-editor-freetext-added-alert': { ertek: tk('Szöveg hozzáadva') },
  'pdfjs-editor-ink-added-alert': { ertek: tk('Rajz hozzáadva') },
  'pdfjs-editor-stamp-added-alert': { ertek: tk('Kép hozzáadva') },
  'pdfjs-editor-signature-added-alert': { ertek: tk('Aláírás hozzáadva') },
  'pdfjs-editor-alt-text-button': cimke(tk('Helyettesítő szöveg')),
  'pdfjs-editor-alt-text-button-label': { ertek: tk('Helyettesítő szöveg') },
  'pdfjs-editor-alt-text-edit-button': cimke(tk('Helyettesítő szöveg szerkesztése')),
  'pdfjs-editor-alt-text-decorative-tooltip': { ertek: tk('Díszítőelemnek jelölve') },
  'pdfjs-editor-new-alt-text-added-button': cimke(tk('Helyettesítő szöveg hozzáadva')),
  'pdfjs-editor-new-alt-text-added-button-label': { ertek: tk('Helyettesítő szöveg hozzáadva') },
  'pdfjs-editor-new-alt-text-missing-button': cimke(tk('Hiányzó helyettesítő szöveg')),
  'pdfjs-editor-new-alt-text-missing-button-label': { ertek: tk('Hiányzó helyettesítő szöveg') },
  'pdfjs-editor-new-alt-text-to-review-button': cimke(tk('Helyettesítő szöveg ellenőrzése')),
  'pdfjs-editor-new-alt-text-to-review-button-label': { ertek: tk('Helyettesítő szöveg ellenőrzése') },
  'pdfjs-editor-new-alt-text-generated-alt-text-with-disclaimer': { ertek: (a) => t('Automatikusan készült: {szoveg}', { szoveg: String(a.generatedAltText ?? '') }) },
};

/** A tartalmilag nem használt (a nézőnek nem látható) azonosítók: nincs ilyen felület, ezért nincs fordítás — a teszt ezt a
 *  listát és a táblát együtt veti össze a könyvtár azonosítóival. */
export const KIVETEL: readonly string[] = [];

const SABLON = /\{\s*\$(\w+)\s*\}/g;

function szoveg(s: Szoveg, args: Args): string {
  return typeof s === 'function' ? s(args) : t(s).replace(SABLON, (_, k: string) => String(args[k] ?? ''));
}

function argok(elem: Element): Args {
  const nyers = elem.getAttribute('data-l10n-args');
  if (!nyers) return {};
  try {
    const a: unknown = JSON.parse(nyers);
    return a && typeof a === 'object' ? (a as Args) : {};
  } catch {
    return {};
  }
}

/**
 * A pdf.js `L10n` interfészének magyar megvalósítása. A viewer a gyökér-elemeket (`translate`) átadja, és a bennük később
 * létrejövő `data-l10n-id` elemeket is lefordítja — ezt itt egy `MutationObserver` végzi (mint a `DOMLocalization`).
 */
export class MagyarL10n {
  private readonly gyokerek = new Set<Element>();
  private figyelo: MutationObserver | null = null;
  private szunet = 0;

  getLanguage(): string {
    return nyelv.kod;
  }

  getDirection(): 'ltr' {
    return 'ltr';
  }

  async get(ids: string | string[], args: Args | null = null, fallback?: string): Promise<string | (string | undefined)[] | undefined> {
    const ertek = (id: string): string | undefined => {
      const e = MAGYAR[id]?.ertek;
      return e === undefined ? undefined : szoveg(e, args ?? {});
    };
    if (Array.isArray(ids)) return ids.map(ertek);
    return ertek(ids) || fallback;
  }

  async translate(elem: Element): Promise<void> {
    this.gyokerek.add(elem);
    this.forditFa(elem);
    this.figyel();
  }

  async translateOnce(elem: Element): Promise<void> {
    this.fordit(elem);
  }

  async destroy(): Promise<void> {
    this.figyelo?.disconnect();
    this.figyelo = null;
    this.gyokerek.clear();
  }

  pause(): void {
    if (this.szunet++ === 0) this.figyelo?.disconnect();
  }

  resume(): void {
    if (this.szunet > 0 && --this.szunet === 0) {
      this.gyokerek.forEach((g) => this.forditFa(g));
      this.figyel();
    }
  }

  /** Egy elem fordítása a `data-l10n-id` szerint (ismeretlen azonosító: érintetlen). */
  fordit(elem: Element): void {
    const id = elem.getAttribute('data-l10n-id');
    const b = id ? MAGYAR[id] : undefined;
    if (!b) return;
    const a = argok(elem);
    if (b.ertek !== undefined) {
      const t = szoveg(b.ertek, a);
      if (elem.textContent !== t) elem.textContent = t;
    }
    for (const [nev, s] of Object.entries(b.attr ?? {})) {
      const t = szoveg(s, a);
      if (elem.getAttribute(nev) !== t) elem.setAttribute(nev, t);
    }
  }

  private forditFa(gyoker: Element): void {
    if (gyoker.hasAttribute('data-l10n-id')) this.fordit(gyoker);
    gyoker.querySelectorAll('[data-l10n-id]').forEach((e) => this.fordit(e));
  }

  private figyel(): void {
    if (this.szunet > 0 || typeof MutationObserver === 'undefined') return;
    this.figyelo ??= new MutationObserver((valtozasok) => {
      for (const v of valtozasok) {
        if (v.type === 'attributes') this.fordit(v.target as Element);
        else
          v.addedNodes.forEach((n) => {
            if (n.nodeType === 1) this.forditFa(n as Element);
          });
      }
    });
    this.figyelo.disconnect();
    this.gyokerek.forEach((g) => this.figyelo!.observe(g, { subtree: true, childList: true, attributes: true, attributeFilter: ['data-l10n-id', 'data-l10n-args'] }));
  }
}
