// Linkjavaslat gépelés közben (C30b-mag; CHATKALAUZ C30b 1–2. pont, T064): a nyitott szöveg linkeletlen említései (a
// `POST /api/asszisztens/emlitesek` core API-ja, modell nélkül) halvány aláhúzással; **Tab = link beszúrása, Esc = elvet**.
//
// Gépelés-kapu (a javaslat nem lassíthatja a gépelést):
//   - a gépelés útvonalán csak a dekorációk átvezetése fut (`mapPos`, legfeljebb 50 javaslat, szó-érvényesség);
//   - a core-kérés a legutolsó szerkesztés után `vartMs` csenddel indul (ütemező időzítő), a szöveg a kérés pillanatában
//     épül, a válasz feldolgozása csak akkor, ha a dokumentum közben nem változott (különben eldobva);
//   - a nyitás nem kér (csak szerkesztés után), a némított fajta és a kikapcsolt Asszisztens semmit nem kér.
//
// Hasonlósági szűrő (C30b, K205 (b)): a lexikai válasz után, ugyanabban a csend-ablakban a javaslatok céljait a C25c
// `POST /api/kereses/hasonlosag`-ával (modell nélkül, a vektortárból) szűri: a core küszöbe (`hasonlosag`, a statisztika
// szorzójával együtt) alatti pontú cél nem javaslat; a pont nélküli cél, a nincs-vektor állapot és a hiba a lexikai javaslatot
// változatlanul hagyja. Csak szűrő — a sorrend a kurzorhoz közelségé.
//
// A Tab csak *látható és aktív* javaslatnál hat (a kurzor rajta áll, vagy az utána legfeljebb `AKTIV_TAVOLSAG` kódegységgel,
// ugyanabban a sorban), a szerkesztő írható, a kijelölés egy üres kurzor, nincs IME-kompozíció és módosító billentyű, és
// nincs nyitott `[[` / `/` menü; különben a Tab a megszokott behúzás, az Esc a megszokott. A döntés a statisztikába csak
// a fajtával és a döntéssel megy (útvonal és szöveg nélkül; a core a Tracker- és az Asszisztens-kapcsoló alatt számolja).

import { type EditorState, type Extension, Facet, Prec, StateEffect, StateField, type Text } from '@codemirror/state';
import { Decoration, type DecorationSet, EditorView, type PluginValue, ViewPlugin, type ViewUpdate } from '@codemirror/view';
import { asszisztensApi } from '../../lib/asszisztens/api';
import type { EmlitesValasz, HasonlosagValasz, JavaslatKuszob } from '../../lib/asszisztens/tipusok';
import { fajlNev } from '../../lib/vault/fajlok.svelte';
import { kiegeszitesNyitva } from '../linkek/kiegeszites';
import { perjelNyitva } from '../notion/perjel';
import {
  aktivJavaslat,
  bekezdesHatar,
  emlitesLink,
  ervenyesSzo,
  hasonlosagSzuro,
  type Javaslat,
  javaslatokBol,
  kuszobSzabaly,
  MAX_KARAKTER,
  VART_ALAP_MS,
} from './javaslatSegedek';

/** A bővítmény külső függőségei (a szerkesztő komponens adja; a tesztben álkliens). */
export interface JavaslatKliens {
  emlitesek(ut: string, szoveg: string, jel: AbortSignal): Promise<EmlitesValasz>;
  dontes(dontes: 'elfogad' | 'elutasit'): Promise<unknown>;
  kuszob(): Promise<JavaslatKuszob | null>;
  /** C30b (K205 (b)): a jegyzet és a lexikai javaslatok céljainak C25c-hasonlósága, modell nélkül. Hiányzik vagy hibázik, vagy
   *  `allapot != ok` (nincs vektor): a javaslat a lexikai marad. */
  hasonlosag?(ut: string, celok: string[], jel: AbortSignal): Promise<HasonlosagValasz>;
}

export interface JavaslatBeallitas {
  ut: string;
  /** az Asszisztens-kapcsoló élő értéke (10., 27(c) döntés: ki → minden néma) */
  kapcsolo(): boolean;
  /** a beírandó link-cél (a core legrövidebb egyértelmű alakja, L42) a cél jegyzet útjából */
  linkCel(celUt: string): Promise<string>;
  kliens: JavaslatKliens;
}

export const javaslatBeallitas = Facet.define<JavaslatBeallitas, JavaslatBeallitas | null>({ combine: (v) => v[0] ?? null });

/** A valódi core-kliens (a küszöb a statisztikából, 60 s-ig gyorsítótárazva a bővítményben). */
export const alapKliens: JavaslatKliens = {
  emlitesek: (ut, szoveg, jel) => asszisztensApi.emlitesek(ut, szoveg, jel),
  dontes: (d) => asszisztensApi.dontes('emlites', d),
  kuszob: async () => {
    const sor = (await asszisztensApi.statisztika()).fajtak.emlites;
    return typeof sor.hasonlosag_kuszob === 'number' ? { ...sor.kuszob, hasonlosag: sor.hasonlosag_kuszob } : sor.kuszob;
  },
  hasonlosag: (ut, celok, jel) => asszisztensApi.hasonlosag(ut, celok, jel),
};

// ---------------------------------------------------------------------- állapot

interface Allapot {
  lista: Javaslat[];
  elutasitott: Set<string>;
  max: number;
  aktiv: Javaslat | null;
  dekor: DecorationSet;
}

const URES: Allapot = { lista: [], elutasitott: new Set(), max: 0, aktiv: null, dekor: Decoration.none };

/** A core válasza (javaslatok a mai dokumentumra). Kívülről a teszt és a mérés használja; élesben a bővítmény maga adja. */
export const javaslatBeerkezett = StateEffect.define<{ lista: Javaslat[]; max: number }>();
const beerkezett = javaslatBeerkezett;
const elutasit = StateEffect.define<string>();
/** Az Asszisztens kikapcsolása vagy a fajta némítása: az aláhúzások eltűnnek. */
export const javaslatUrit = StateEffect.define<null>();

const KOZEPSO = Decoration.mark({ class: 'cm-javaslat' });
const AKTIV = Decoration.mark({
  class: 'cm-javaslat cm-javaslat-aktiv',
  attributes: { title: 'Tab: link beszúrása · Esc: elvet' },
});

function felepit(allapot: Allapot, doc: Text, fej: number): Allapot {
  if (!allapot.lista.length) return allapot.aktiv || allapot.dekor !== Decoration.none ? { ...allapot, aktiv: null, dekor: Decoration.none } : allapot;
  const [a, b] = bekezdesHatar(doc, fej);
  const lathato = allapot.lista
    .filter((j) => j.from >= a && j.to <= b)
    .sort((x, y) => Math.abs(x.from - fej) - Math.abs(y.from - fej))
    .slice(0, allapot.max);
  const aktiv = aktivJavaslat(lathato, doc, fej);
  const dekor = Decoration.set(
    lathato.sort((x, y) => x.from - y.from).map((j) => (j === aktiv ? AKTIV : KOZEPSO).range(j.from, j.to)),
  );
  return { ...allapot, aktiv, dekor };
}

const mezo = StateField.define<Allapot>({
  create: () => URES,
  update(ertek, tr) {
    let allapot = ertek;
    let ujra = tr.docChanged || !!tr.selection;
    for (const e of tr.effects) {
      if (e.is(javaslatUrit)) {
        allapot = { ...URES, elutasitott: allapot.elutasitott };
        ujra = true;
      } else if (e.is(beerkezett)) {
        allapot = { ...allapot, lista: e.value.lista.filter((j) => !allapot.elutasitott.has(j.kulcs)), max: e.value.max };
        ujra = true;
      } else if (e.is(elutasit)) {
        const kulcsok = new Set(allapot.elutasitott).add(e.value);
        allapot = { ...allapot, elutasitott: kulcsok, lista: allapot.lista.filter((j) => j.kulcs !== e.value) };
        ujra = true;
      }
    }
    if (tr.docChanged && allapot.lista.length) {
      // a gépelés útvonala: csak az átvezetés és az érvényesség (a szó még ugyanaz, önálló szó)
      const lista: Javaslat[] = [];
      for (const j of allapot.lista) {
        const from = tr.changes.mapPos(j.from, 1);
        const to = tr.changes.mapPos(j.to, -1);
        if (ervenyesSzo(tr.newDoc, from, to, j.szoveg)) lista.push(from === j.from && to === j.to ? j : { ...j, from, to });
      }
      allapot = { ...allapot, lista };
    }
    return ujra ? felepit(allapot, tr.state.doc, tr.state.selection.main.head) : allapot;
  },
  provide: (f) => EditorView.decorations.from(f, (s) => s.dekor),
});

/** A jelenleg aktív (látható, a kurzorhoz tartozó) javaslat, vagy `null`. */
export function aktivJavaslatAllapot(state: EditorState): Javaslat | null {
  return state.field(mezo, false)?.aktiv ?? null;
}

/** A látható javaslatok (a teszteknek és a hibakeresésnek). */
export function lathatoJavaslatok(state: EditorState): readonly Javaslat[] {
  return state.field(mezo, false)?.lista ?? [];
}

// ---------------------------------------------------------------------- ütemezés és kérés

const KUSZOB_ERVENYES_MS = 60_000;
/** A hasonlósági pontok érvényessége (a vektortár a mentett jegyzetre épül, és csak a háttérben frissül), és a „nincs vektor”
 *  válasz után ennyi ideig nem kérdez újra. */
const HASONLOSAG_ERVENYES_MS = 60_000;

class Utemezo implements PluginValue {
  private idozito: ReturnType<typeof setTimeout> | null = null;
  private vezerlo: AbortController | null = null;
  private megszunt = false;
  private kovId = 0;
  private kuszob: { ertek: JavaslatKuszob | null; ido: number } | null = null;
  private vartMs = VART_ALAP_MS;
  private pontok = new Map<string, number | null>();
  private pontokIdo = 0;
  private pontokLe = 0;

  constructor(private view: EditorView) {}

  update(u: ViewUpdate): void {
    if (!u.docChanged) return;
    const cfg = u.state.facet(javaslatBeallitas);
    if (!cfg) return;
    if (this.idozito) clearTimeout(this.idozito);
    this.idozito = null;
    // a külső kérés a gépelés útvonalán kívül indul: csak egy időzítő áll be, a szöveg a csend végén épül
    if (cfg.kapcsolo() && !u.state.readOnly) this.idozito = setTimeout(() => void this.kuld(), this.vartMs);
  }

  destroy(): void {
    this.megszunt = true;
    if (this.idozito) clearTimeout(this.idozito);
    this.vezerlo?.abort();
  }

  private async kuszobKap(cfg: JavaslatBeallitas): Promise<JavaslatKuszob | null> {
    const most = Date.now();
    if (this.kuszob && most - this.kuszob.ido < KUSZOB_ERVENYES_MS) return this.kuszob.ertek;
    let ertek: JavaslatKuszob | null = null;
    try {
      ertek = await cfg.kliens.kuszob();
    } catch {
      ertek = null; // a küszöb nem érhető el: alap
    }
    this.kuszob = { ertek, ido: Date.now() };
    return ertek;
  }

  /** A javaslatok céljainak hasonlósága a jegyzethez (C30b): az utolsó `HASONLOSAG_ERVENYES_MS` pontjai gyorsítótárban, csak
   *  a hiányzó célok kérése. `null`: nincs szűrés (nincs vektor, nincs kliens-képesség, hiba) — a lexikai javaslat marad,
   *  és a core-t egy ideig nem zaklatja. */
  private async hasonlosagKap(
    cfg: JavaslatBeallitas,
    valasz: EmlitesValasz,
    jel: AbortSignal,
  ): Promise<ReadonlyMap<string, number | null> | null> {
    const kliens = cfg.kliens;
    if (!kliens.hasonlosag) return null;
    const most = Date.now();
    if (most < this.pontokLe) return null;
    if (most - this.pontokIdo > HASONLOSAG_ERVENYES_MS) {
      this.pontok.clear();
      this.pontokIdo = most;
    }
    const celok = [...new Set(valasz.emlitesek.filter((m) => !m.tobbertelmu && m.cel).map((m) => m.cel as string))];
    const hianyzo = celok.filter((c) => !this.pontok.has(c));
    if (!hianyzo.length) return this.pontok;
    try {
      const v = await kliens.hasonlosag(cfg.ut, hianyzo, jel);
      if (v.allapot !== 'ok') {
        this.pontokLe = Date.now() + HASONLOSAG_ERVENYES_MS;
        return null;
      }
      for (const c of hianyzo) this.pontok.set(c, v.pontok?.[c] ?? null);
    } catch {
      if (!jel.aborted) this.pontokLe = Date.now() + HASONLOSAG_ERVENYES_MS;
      return null; // a hasonlóság nem létfontosságú: a javaslat marad lexikai
    }
    return this.pontok;
  }

  /** A küszöb újraolvasása a következő kérésnél (egy döntés után). */
  kuszobErvenytelen(): void {
    this.kuszob = null;
  }

  private async kuld(): Promise<void> {
    this.idozito = null;
    const view = this.view;
    const cfg = view.state.facet(javaslatBeallitas);
    if (this.megszunt || !cfg || !cfg.kapcsolo() || view.state.readOnly) return;
    const szabaly = kuszobSzabaly(await this.kuszobKap(cfg));
    this.vartMs = szabaly.vartMs;
    if (this.megszunt || !cfg.kapcsolo()) return;
    if (szabaly.tilt) {
      if (view.state.field(mezo, false)?.lista.length) view.dispatch({ effects: javaslatUrit.of(null) });
      return;
    }
    const doc = view.state.doc;
    if (doc.length > MAX_KARAKTER) return;
    this.vezerlo?.abort();
    const vezerlo = (this.vezerlo = new AbortController());
    let valasz: EmlitesValasz;
    try {
      valasz = await cfg.kliens.emlitesek(cfg.ut, doc.toString(), vezerlo.signal);
    } catch {
      return; // a javaslat nem létfontosságú: hibánál nincs aláhúzás, a következő szerkesztés újra próbál
    }
    // a hasonlóság szűrője (C30b): csak ha a core küszöböt adott; a hibája vagy a hiánya a lexikai javaslatot hagyja
    const pontok = szabaly.hasonlosag !== undefined ? await this.hasonlosagKap(cfg, valasz, vezerlo.signal) : null;
    // elavult válasz: a dokumentum közben változott (a gépelő a következő csendnél újra kérdez), vagy kikapcsolták
    if (this.megszunt || vezerlo.signal.aborted || view.state.doc !== doc || !cfg.kapcsolo()) return;
    if (!valasz.kapcsolo) {
      if (view.state.field(mezo, false)?.lista.length) view.dispatch({ effects: javaslatUrit.of(null) });
      return;
    }
    const elutasitott = view.state.field(mezo, false)?.elutasitott ?? new Set<string>();
    const lista = javaslatokBol(valasz, view.state, elutasitott, () => ++this.kovId, hasonlosagSzuro(pontok, szabaly.hasonlosag));
    view.dispatch({ effects: beerkezett.of({ lista, max: szabaly.max }) });
  }
}

const utemezoPlugin = ViewPlugin.fromClass(Utemezo);

// ---------------------------------------------------------------------- Tab és Esc

async function elfogad(view: EditorView, a: Javaslat): Promise<void> {
  const cfg = view.state.facet(javaslatBeallitas);
  if (!cfg) return;
  let cel: string;
  try {
    cel = await cfg.linkCel(a.celUt);
  } catch {
    return; // a cél nem oldható fel: a javaslat marad, a Tab nem ír
  }
  // a feloldás alatt gépelhetett: a javaslat mai helyét az állapot adja, érvénytelenné vált javaslatra nem írunk
  const mai = view.state.field(mezo, false)?.lista.find((j) => j.id === a.id);
  if (!mai || !ervenyesSzo(view.state.doc, mai.from, mai.to, mai.szoveg) || view.state.readOnly) return;
  const beszur = emlitesLink(cel, fajlNev(a.celUt), mai.szoveg);
  const fej = view.state.selection.main.head;
  view.dispatch({
    changes: { from: mai.from, to: mai.to, insert: beszur },
    ...(fej <= mai.to ? { selection: { anchor: mai.from + beszur.length } } : {}),
    userEvent: 'input.complete', // nem összevonható a gépeléssel: egy ⌘Z lépés
    scrollIntoView: true,
  });
  void cfg.kliens.dontes('elfogad').catch(() => undefined);
  view.plugin(utemezoPlugin)?.kuszobErvenytelen();
}

function elvet(view: EditorView, a: Javaslat): void {
  const cfg = view.state.facet(javaslatBeallitas);
  view.dispatch({ effects: elutasit.of(a.kulcs) });
  void cfg?.kliens.dontes('elutasit').catch(() => undefined);
  view.plugin(utemezoPlugin)?.kuszobErvenytelen();
}

/** Prec.highest: a javaslat Tabja és Escape-je megelőzi a behúzást és a többi billentyű-kezelőt — de csak látható, aktív
 *  javaslatnál (egyébként `false`, és a többi kezelő megy a dolgára). */
const billentyuk = Prec.highest(
  EditorView.domEventHandlers({
    keydown(e, view) {
      if (e.key !== 'Tab' && e.key !== 'Escape') return false;
      if (e.isComposing || e.altKey || e.ctrlKey || e.metaKey || e.shiftKey) return false;
      const cfg = view.state.facet(javaslatBeallitas);
      if (!cfg || !cfg.kapcsolo() || view.state.readOnly) return false;
      if (kiegeszitesNyitva(view.state) || perjelNyitva(view.state)) return false; // a menü kezeli a Tabot és az Esc-et
      const a = aktivJavaslatAllapot(view.state);
      if (!a) return false;
      const s = view.state.selection;
      if (s.ranges.length !== 1 || !s.main.empty) return false;
      e.preventDefault();
      if (e.key === 'Tab') void elfogad(view, a);
      else elvet(view, a);
      return true;
    },
  }),
);

/** A linkjavaslat bővítménye. A `javaslatBeallitas` Facet nélkül tétlen. */
export function javaslatBovitmeny(): Extension {
  return [mezo, utemezoPlugin, billentyuk];
}
