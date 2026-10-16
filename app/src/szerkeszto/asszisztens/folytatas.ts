// A szellemszöveg és a kézi hívás (CX-011, J2): a javaslat díszítés, elfogadásig nem dokumentumtartalom; soha nem kér fókuszt.
// Három mód: `folytat` (gépelési szünetben magától is, a kurzor után), `kifejt` (a kijelölés után), `osszefoglal` (a kijelölés
// helyére). Tab elfogadja — egyetlen tranzakció, a ⌘Z egy lépés —, Esc eldobja. A nem mért (próba) javaslat „próba” jelet kap
// (D9), és ugyanúgy csak elfogadásra kerül a jegyzetbe. A gyakoriságot a core hangolása (`allas`) szabja: néma helyzetben a
// szünet nem kér javaslatot (a kézi hívás igen).
import { t, tk } from '../../lib/i18n';
import { Facet, Prec, StateEffect, StateField, type Extension } from '@codemirror/state';
import { isolateHistory } from '@codemirror/commands';
import { Decoration, EditorView, ViewPlugin, WidgetType, type ViewUpdate } from '@codemirror/view';
import { kerdez } from '../../lib/core/api';
import { kiegeszitesNyitva } from '../linkek/kiegeszites';
import { perjelNyitva } from '../notion/perjel';
import { aktivJavaslatAllapot } from './javaslat';

export type FolytatasMod = 'folytat' | 'kifejt' | 'osszefoglal';
export interface FolytatasAllas { szint: 'batrabb' | 'alap' | 'ritkabb' | 'nema'; szorzo: number | null }
export interface FolytatasValasz { szoveg: string; ok?: string; forras?: string; proba?: boolean; nema?: boolean; allas?: FolytatasAllas | null }
export interface FolytatasKeres { azon: string; elotte: string; utana: string; mod: FolytatasMod; kijeloles: string; kezi: boolean }
export interface FolytatasBeallitas {
  kapcsolo(): boolean;
  ker(d: FolytatasKeres, jel: AbortSignal): Promise<FolytatasValasz>;
  /** `kifejezett`: a látott javaslatot a felhasználó Esc-kel vetette el (különben: átírta, elhagyta — kis súlyú jel) */
  dontes(azon: string, elfogad: boolean, kifejezett?: boolean): Promise<unknown>;
  jelzes?(szoveg: string): void;
  vartMs?: number;
}
export const folytatasForras = Facet.define<FolytatasBeallitas, FolytatasBeallitas | null>({ combine: v => v[0] ?? null });
/** Kézi hívás; `null` = a régi alak: folytatás a kurzornál. */
export const folytatasKezi = StateEffect.define<{ mod: FolytatasMod } | null>();
export const folytatasUrit = StateEffect.define<null>();

export interface FolytatasEredmeny {
  azon: string; mod: FolytatasMod; hely: number; szoveg: string; forras?: string; proba: boolean;
  /** az összefoglalás a kijelölés helyére kerül */
  csere: { from: number; to: number } | null;
}
const eredmeny = StateEffect.define<FolytatasEredmeny | null>();
export const folytatasAllapot = StateField.define<FolytatasEredmeny | null>({
  create: () => null,
  update(v, tr) {
    if (tr.docChanged || tr.selection || tr.effects.some(e => e.is(folytatasUrit))) v = null;
    for (const e of tr.effects) if (e.is(eredmeny)) v = e.value;
    return v;
  },
  provide: f => EditorView.decorations.from(f, a => {
    if (!a) return Decoration.none;
    const d = [Decoration.widget({ widget: new Szellem(a.szoveg, a.mod, a.proba, a.forras), side: 1 }).range(a.hely)];
    if (a.csere && a.csere.to > a.csere.from) d.unshift(Decoration.mark({ class: 'cm-folytatas-csere' }).range(a.csere.from, a.csere.to));
    return Decoration.set(d, true);
  }),
});

const MOD_NEV: Record<FolytatasMod, string> = { folytat: tk('Folytatás'), kifejt: tk('Kifejtés'), osszefoglal: tk('Összefoglalás') };

class Szellem extends WidgetType {
  constructor(readonly szoveg: string, readonly mod: FolytatasMod, readonly proba: boolean, readonly forras?: string) { super(); }
  eq(m: Szellem) { return this.szoveg === m.szoveg && this.forras === m.forras && this.mod === m.mod && this.proba === m.proba; }
  toDOM() {
    const s = document.createElement('span');
    s.className = 'cm-folytatas';
    s.contentEditable = 'false';
    const mit = this.mod === 'osszefoglal' ? t('Tab: csere') : t('Tab: elfogad');
    s.title = t('{mod} · {forras}{proba} · {mit} · Esc: elvet', { mod: t(MOD_NEV[this.mod]), forras: this.forras ?? t('Asszisztens'), proba: this.proba ? ' · ' + t('próba (nem mért modell)') : '', mit });
    s.setAttribute('aria-label', s.title);
    if (this.proba || this.mod !== 'folytat') {
      const j = s.appendChild(document.createElement('span'));
      j.className = 'cm-folytatas-jel';
      j.textContent = [this.mod !== 'folytat' ? t(MOD_NEV[this.mod]).toLowerCase() : '', this.proba ? t('próba') : ''].filter(Boolean).join(' · ');
    }
    s.appendChild(document.createTextNode(this.mod === 'folytat' ? this.szoveg : ` ${this.szoveg}`));
    return s;
  }
  ignoreEvent() { return true; }
}

const NEMA_SZUNET_MS = 10 * 60_000;

const utemezo = ViewPlugin.fromClass(class {
  private ido: ReturnType<typeof setTimeout> | null = null;
  private keres: { azon: string; vezerlo: AbortController } | null = null;
  private generacio = 0;
  private halott = false;
  private szunet = 0;
  private szorzo = 1;
  constructor(readonly view: EditorView) {}
  megszakit() {
    this.generacio++;
    if (this.ido) clearTimeout(this.ido);
    this.ido = null;
    if (this.keres) {
      this.keres.vezerlo.abort();
      void this.view.state.facet(folytatasForras)?.dontes(this.keres.azon, false, false).catch(() => {});
      this.keres = null;
    }
  }
  update(u: ViewUpdate) {
    // a látott javaslat, amelyet a felhasználó átírt vagy elhagyott (nem Tab, nem Esc): kis súlyú jel a hangolásnak
    const volt = u.startState.field(folytatasAllapot), van = u.state.field(folytatasAllapot);
    if (volt && van !== volt && !u.transactions.some(t => t.effects.some(e => e.is(eredmeny))))
      void u.state.facet(folytatasForras)?.dontes(volt.azon, false, false).catch(() => {});
    let kezi: FolytatasMod | null = null;
    for (const t of u.transactions) for (const e of t.effects) if (e.is(folytatasKezi)) kezi = e.value?.mod ?? 'folytat';
    const urit = u.transactions.some(t => t.effects.some(e => e.is(folytatasUrit)));
    if (u.docChanged || u.selectionSet || u.focusChanged || kezi || urit) this.megszakit();
    const b = u.state.facet(folytatasForras);
    if (!b?.kapcsolo() || u.state.readOnly || !u.view.hasFocus || urit) return;
    if (kezi) {
      const mod = kezi;
      this.ido = setTimeout(() => void this.kuld(mod, true), 0);
    } else if (u.docChanged && Date.now() >= this.szunet && u.transactions.some(t => t.isUserEvent('input.type'))) {
      this.ido = setTimeout(() => void this.kuld('folytat', false), Math.round((b.vartMs ?? 1400) * this.szorzo));
    }
  }
  async kuld(mod: FolytatasMod, kezi: boolean) {
    this.ido = null;
    const v = this.view, b = v.state.facet(folytatasForras), s = v.state.selection;
    if (!b?.kapcsolo() || v.state.readOnly || !v.hasFocus || v.composing || s.ranges.length !== 1) return;
    if (kiegeszitesNyitva(v.state) || perjelNyitva(v.state) || aktivJavaslatAllapot(v.state)) return;
    const doc = v.state.doc, gen = this.generacio, sel = s.main;
    if (mod === 'folytat' ? !sel.empty || doc.lineAt(sel.head).to !== sel.head : sel.empty) {
      if (kezi) b.jelzes?.(mod === 'folytat' ? t('A folytatás a sor végén, kijelölés nélkül kérhető.') : t('Jelöld ki a szöveget.'));
      return;
    }
    const hely = mod === 'folytat' ? sel.head : sel.to;
    const kijeloles = mod === 'folytat' ? '' : doc.sliceString(sel.from, sel.to).slice(0, 4000);
    const azon = crypto.randomUUID(), vezerlo = new AbortController();
    this.keres = { azon, vezerlo };
    try {
      const r = await b.ker({ azon, mod, kijeloles, kezi, elotte: doc.sliceString(Math.max(0, (mod === 'folytat' ? hely : sel.from) - 6000), mod === 'folytat' ? hely : sel.from),
        utana: doc.sliceString(hely, Math.min(doc.length, hely + 2000)) }, vezerlo.signal);
      if (r.allas) this.szorzo = r.allas.szint === 'nema' ? 1 : Math.min(8, Math.max(0.6, r.allas.szorzo ?? 1));
      if (this.halott || gen !== this.generacio || vezerlo.signal.aborted || !b.kapcsolo() || v.state.doc !== doc || !v.hasFocus) return;
      if (r.szoveg) {
        v.dispatch({ effects: eredmeny.of({ azon, mod, hely, szoveg: r.szoveg.slice(0, mod === 'folytat' ? 800 : 2000), forras: r.forras,
          proba: !!r.proba, csere: mod === 'osszefoglal' ? { from: sel.from, to: sel.to } : null }) });
      } else {
        this.szunet = Date.now() + (r.nema ? NEMA_SZUNET_MS : 60_000);
        if (kezi && r.ok) b.jelzes?.(r.ok);
      }
    } catch { this.szunet = Date.now() + 60_000; if (kezi && !vezerlo.signal.aborted) b.jelzes?.(t('A kiegészítés most nem érhető el.')); }
    finally { if (this.keres?.azon === azon) this.keres = null; }
  }
  destroy() { this.halott = true; this.megszakit(); }
});

/** Az elfogadás egyetlen tranzakciója: folytatás/kifejtés beszúrás, összefoglalás csere; a ⌘Z egy lépésben visszavonja. */
export function folytatasElfogad(v: EditorView): boolean {
  const a = v.state.field(folytatasAllapot, false);
  if (!a) return false;
  const changes = a.csere ? { from: a.csere.from, to: a.csere.to, insert: a.szoveg }
    : { from: a.hely, insert: a.mod === 'kifejt' && !/\s$/.test(v.state.doc.sliceString(a.hely - 1, a.hely)) ? ` ${a.szoveg}` : a.szoveg };
  const veg = changes.from + changes.insert.length;
  v.dispatch({ changes, selection: { anchor: veg }, effects: eredmeny.of(null), annotations: isolateHistory.of('full'), userEvent: 'input.complete' });
  void v.state.facet(folytatasForras)?.dontes(a.azon, true).catch(() => {});
  return true;
}

export function folytatasBovitmeny(): Extension {
  return [folytatasAllapot, utemezo, Prec.highest(EditorView.domEventHandlers({
    keydown(e, v) {
      if (!['Tab', 'Escape'].includes(e.key) || e.shiftKey || e.altKey || e.metaKey || e.ctrlKey || e.isComposing) return false;
      const a = v.state.field(folytatasAllapot), b = v.state.facet(folytatasForras);
      if (!a || !b?.kapcsolo() || v.state.readOnly || v.composing || kiegeszitesNyitva(v.state) || perjelNyitva(v.state)) return false;
      e.preventDefault();
      if (e.key === 'Tab') return folytatasElfogad(v);
      v.dispatch({ effects: eredmeny.of(null) });
      void b.dontes(a.azon, false, true).catch(() => {});
      return true;
    },
    blur(_e, v) { if (v.state.field(folytatasAllapot)) v.dispatch({ effects: folytatasUrit.of(null) }); return false; },
  })), EditorView.baseTheme({
    '.cm-folytatas': { color: 'var(--szoveg-halvany)', opacity: '0.65', whiteSpace: 'pre-wrap', pointerEvents: 'auto' },
    '.cm-folytatas-jel': { fontSize: 'var(--betu-kicsi)', border: '1px solid var(--keret)', borderRadius: 'var(--kerekites)',
      padding: '0 var(--t-1)', marginInline: 'var(--t-1)', fontStyle: 'normal' },
    '.cm-folytatas-csere': { textDecoration: 'line-through', textDecorationColor: 'var(--szoveg-halvany)' },
  })];
}

/** A kézi hívás (⌘J): kijelölés nélkül folytatás, kijelöléssel kifejtés. */
export function folytatasKeziMod(v: EditorView): FolytatasMod {
  return v.state.selection.main.empty ? 'folytat' : 'kifejt';
}

export const folytatasKliens = {
  ker: (d: FolytatasKeres, jel: AbortSignal) => kerdez<FolytatasValasz>('/api/asszisztens/kiegeszites', { metodus: 'POST', torzs: d, jel, idokorlat: 35000 }),
  dontes: (azon: string, elfogad: boolean, kifejezett = false) => kerdez(`/api/asszisztens/kiegeszites/${elfogad ? 'elfogad' : 'elvet'}`,
    { metodus: 'POST', torzs: elfogad ? { azon } : { azon, kifejezett }, idokorlat: 5000 }),
};
