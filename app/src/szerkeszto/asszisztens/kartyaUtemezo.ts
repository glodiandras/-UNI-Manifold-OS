// A javaslat-kártya ütemezője a szerkesztőben (J3): gépelési szünetben (és a jegyzet megnyitása után egyszer) megkérdezi a
// core-t, van-e a tanult mintákból javaslat; ha van, átadja a kártyának. A kártya nem modális és nem kér fókuszt (CX-tartós
// döntés); itt a szerkesztő csak a „mikor” felel. Két kártya között legalább a core `varakozas_mp`-je telik el (a hangolás
// szorzójával: az elfogadott fajta gyakrabban, az elutasított ritkábban). Kikapcsolt Asszisztensnél semmit nem kérdez.
import { Facet, type Extension } from '@codemirror/state';
import { EditorView, ViewPlugin, type ViewUpdate } from '@codemirror/view';
import type { KartyaJavaslat, KartyaValasz } from '../../lib/asszisztens/tipusok';
import { kiegeszitesNyitva } from '../linkek/kiegeszites';
import { perjelNyitva } from '../notion/perjel';
import { folytatasAllapot } from './folytatas';
import { aktivJavaslatAllapot } from './javaslat';

export interface KartyaUtemezoBeallitas {
  ut: string;
  kapcsolo(): boolean;
  /** látszik-e már kártya (bárhol): ilyenkor nem kérdez újat */
  latszik(): boolean;
  ker(alkalom: 'megnyitas' | 'szunet', szoveg: string, jel: AbortSignal): Promise<KartyaValasz>;
  mutat(j: KartyaJavaslat, view: EditorView): void;
  /** a jegyzet bezárásakor (a nézet lebontása) a kártya is eltűnik */
  bezar?(view: EditorView): void;
  szunetMs?: number;
  megnyitasMs?: number;
}

export const kartyaUtemezoForras = Facet.define<KartyaUtemezoBeallitas, KartyaUtemezoBeallitas | null>({ combine: (v) => v[0] ?? null });

const MAX_SZOVEG = 200_000;
const MIN_KOZ_MS = 30_000;

const utemezo = ViewPlugin.fromClass(class {
  private ido: ReturnType<typeof setTimeout> | null = null;
  private vezerlo: AbortController | null = null;
  private kovetkezo = 0;
  private halott = false;
  constructor(readonly view: EditorView) {
    const b = view.state.facet(kartyaUtemezoForras);
    if (b) this.ido = setTimeout(() => void this.kuld('megnyitas'), b.megnyitasMs ?? 4000);
  }
  update(u: ViewUpdate) {
    if (!u.docChanged || !u.transactions.some((t) => t.isUserEvent('input') || t.isUserEvent('delete'))) return;
    this.vezerlo?.abort();
    if (this.ido) clearTimeout(this.ido);
    const b = u.state.facet(kartyaUtemezoForras);
    if (!b?.kapcsolo()) return;
    this.ido = setTimeout(() => void this.kuld('szunet'), b.szunetMs ?? 8000);
  }
  async kuld(alkalom: 'megnyitas' | 'szunet') {
    this.ido = null;
    const v = this.view, b = v.state.facet(kartyaUtemezoForras);
    if (!b || !b.kapcsolo() || b.latszik() || Date.now() < this.kovetkezo || v.state.readOnly || !v.hasFocus || v.composing) return;
    if (v.state.field(folytatasAllapot, false) || kiegeszitesNyitva(v.state) || perjelNyitva(v.state) || aktivJavaslatAllapot(v.state)) return;
    if (v.state.doc.length > MAX_SZOVEG) return;
    const doc = v.state.doc, vezerlo = new AbortController();
    this.vezerlo = vezerlo;
    try {
      const r = await b.ker(alkalom, doc.toString(), vezerlo.signal);
      const koz = Math.max(MIN_KOZ_MS, (r.varakozas_mp ?? 90) * 1000);
      this.kovetkezo = Date.now() + (r.javaslat ? koz : koz / 3);
      if (this.halott || vezerlo.signal.aborted || !b.kapcsolo() || v.state.doc !== doc || !r.javaslat || b.latszik()) return;
      b.mutat(r.javaslat, v);
    } catch {
      this.kovetkezo = Date.now() + MIN_KOZ_MS;
    } finally {
      if (this.vezerlo === vezerlo) this.vezerlo = null;
    }
  }
  destroy() {
    this.halott = true;
    this.vezerlo?.abort();
    if (this.ido) clearTimeout(this.ido);
    this.view.state.facet(kartyaUtemezoForras)?.bezar?.(this.view);
  }
});

export function kartyaUtemezo(): Extension {
  return utemezo;
}
