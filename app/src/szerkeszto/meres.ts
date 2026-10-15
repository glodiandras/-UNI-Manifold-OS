// Gépelési késleltetés a valódi böngészőmotorban (C08 kapu: 5000 soros jegyzetben a p95 < 16 ms).
//
// A mért érték leütésenként a FELDOLGOZÁS: a billentyű eseményének idejétől addig, amíg a szerkesztő a
// változást feldolgozta és az elrendezés (stílus + layout) is elkészült — vagyis ami egy képkockán belül
// kell, hogy beférjen. A kijelző frissítésére várás nem része: 60 Hz-en az önmagában 0–16,7 ms, a
// leütés véletlen pillanatától függően. Tájékoztatásul a „képig” értéket is mérjük (leütés → a változást
// mutató képkocka festése utáni pillanat: rAF + MessageChannel), ez a várakozást is tartalmazza.
//
// Két mód (⌘P → „Fejlesztő: …”):
//   - valódi leütések: 200 leütésig (vagy kikapcsolásig) méri a gépelést az aktív jegyzetben;
//   - szintetikus: a jegyzet egy LEVÁLASZTOTT másolatán (a Dokumentumhoz nem csatol, nem ment) 300
//     beszúrást és törlést végez a látható rész közepén, a valódi bővítménykészlettel és szélességgel.
// Az eredmény értesítésben, a konzolban és a `window.__manifoldMeres`-ben.

import { StateEffect } from '@codemirror/state';
import { EditorView } from '@codemirror/view';
import { ertesitesek } from '../lib/ertesites/ertesites.svelte';

const MINTA = 200;

export interface Eloszlas {
  p50: number;
  p95: number;
  p99: number;
  max: number;
  atlag: number;
}

export interface MeresRiport {
  mod: 'valodi' | 'szintetikus';
  n: number;
  sorok: number;
  feldolgozas: Eloszlas;
  kepig: Eloszlas | null;
}

function percentilis(rendezett: number[], p: number): number {
  if (!rendezett.length) return 0;
  return rendezett[Math.min(rendezett.length - 1, Math.ceil((p / 100) * rendezett.length) - 1)];
}

export function eloszlas(idok: number[]): Eloszlas {
  const r = [...idok].sort((a, b) => a - b);
  const kerek = (x: number) => Math.round(x * 10) / 10;
  return {
    p50: kerek(percentilis(r, 50)),
    p95: kerek(percentilis(r, 95)),
    p99: kerek(percentilis(r, 99)),
    max: kerek(r[r.length - 1] ?? 0),
    atlag: kerek(r.reduce((a, b) => a + b, 0) / (r.length || 1)),
  };
}

function kozzetesz(r: MeresRiport) {
  (window as unknown as { __manifoldMeres?: MeresRiport }).__manifoldMeres = r;
  console.info('[gépelési késleltetés]', JSON.stringify(r));
  const f = r.feldolgozas;
  ertesitesek.ertesit({
    szint: f.p95 < 16 ? 'siker' : 'figyelmeztetes',
    cim: `Gépelés (${r.mod === 'valodi' ? 'valódi' : 'szintetikus'}): p95 ${f.p95} ms`,
    szoveg:
      `${r.n} leütés, ${r.sorok} sor · feldolgozás medián ${f.p50} ms, p99 ${f.p99} ms, max ${f.max} ms` +
      (r.kepig ? ` · képig (a kijelzőre várással) medián ${r.kepig.p50} ms, p95 ${r.kepig.p95} ms` : ''),
    idotartam: 0,
  });
}

/** A festés utáni pillanat: a következő rAF-ből küldött üzenet. */
function festesUtan(): Promise<number> {
  return new Promise((ok) =>
    requestAnimationFrame(() => {
      const cs = new MessageChannel();
      cs.port1.onmessage = () => {
        cs.port1.close();
        ok(performance.now());
      };
      cs.port2.postMessage(0);
    }),
  );
}

// ---------------------------------------------------------------------- valódi leütések

let fut: { leall: () => void } | null = null;

export function gepelesMeresKapcsol(view: EditorView): void {
  if (fut) {
    fut.leall();
    return;
  }
  const feldolgozas: number[] = [];
  const kepig: number[] = [];
  let fuggo: number[] = [];
  const kezel = (e: KeyboardEvent) => {
    if (e.metaKey || e.ctrlKey || (e.key.length !== 1 && e.key !== 'Backspace' && e.key !== 'Enter')) return;
    const most = performance.now();
    // a WebKit `timeStamp`-je a performance.now() időtengelyén áll; ha mégsem, a feldolgozás kezdete
    fuggo.push(Math.abs(most - e.timeStamp) < 1000 ? Math.min(e.timeStamp, most) : most);
  };
  const figyelo = EditorView.updateListener.of((u) => {
    if (!u.docChanged || !fuggo.length) return;
    const t0 = fuggo[0];
    fuggo = [];
    void u.view.contentDOM.offsetHeight; // a stílus és az elrendezés most (ami a képkockához kell)
    feldolgozas.push(performance.now() - t0);
    void festesUtan().then((t) => {
      kepig.push(t - t0);
      if (feldolgozas.length >= MINTA) leall();
    });
  });
  view.dispatch({ effects: StateEffect.appendConfig.of(figyelo) });
  view.contentDOM.addEventListener('keydown', kezel, { capture: true });
  const leall = () => {
    if (!fut) return;
    fut = null;
    view.contentDOM.removeEventListener('keydown', kezel, { capture: true });
    kozzetesz({
      mod: 'valodi',
      n: feldolgozas.length,
      sorok: view.state.doc.lines,
      feldolgozas: eloszlas(feldolgozas),
      kepig: eloszlas(kepig),
    });
  };
  fut = { leall };
  ertesitesek.ertesit({ szint: 'info', cim: 'Gépelési mérés indul', szoveg: `${MINTA} leütésig, vagy amíg újra ki nem kapcsolod.` });
}

// ---------------------------------------------------------------------- szintetikus (leválasztott másolat)

export async function szintetikusMeres(view: EditorView, n = 300): Promise<MeresRiport> {
  const kont = document.createElement('div');
  const r = view.dom.getBoundingClientRect();
  Object.assign(kont.style, {
    position: 'fixed',
    left: `${r.left}px`,
    top: `${r.top}px`,
    width: `${r.width}px`,
    height: `${r.height}px`,
    visibility: 'hidden',
    pointerEvents: 'none',
  });
  // a szerkesztő stílusa a `.szerkeszto` alatt él
  kont.className = 'szerkeszto';
  document.body.appendChild(kont);
  // ugyanaz az állapot és bővítménykészlet (a mód és a nyelv is), de saját nézet a Dokumentum nélkül:
  // a változásai sehová nem mentődnek
  const masolat = new EditorView({ state: view.state, parent: kont });
  masolat.scrollDOM.scrollTop = view.scrollDOM.scrollTop;
  await festesUtan();
  const kozep = masolat.lineBlockAtHeight(masolat.scrollDOM.scrollTop + r.height / 2);
  let pos = masolat.state.doc.lineAt(kozep.from).to;
  const feldolgozas: number[] = [];
  const kepig: number[] = [];
  for (let i = 0; i < n; i++) {
    const t0 = performance.now();
    const torles = i % 10 === 9;
    masolat.dispatch(
      torles
        ? { changes: { from: pos - 1, to: pos }, selection: { anchor: pos - 1 }, userEvent: 'delete.backward' }
        : { changes: { from: pos, insert: 'a' }, selection: { anchor: pos + 1 }, userEvent: 'input.type' },
    );
    pos += torles ? -1 : 1;
    void masolat.contentDOM.offsetHeight;
    feldolgozas.push(performance.now() - t0);
    kepig.push((await festesUtan()) - t0);
  }
  masolat.destroy();
  kont.remove();
  const riport: MeresRiport = {
    mod: 'szintetikus',
    n,
    sorok: view.state.doc.lines,
    feldolgozas: eloszlas(feldolgozas),
    kepig: eloszlas(kepig),
  };
  kozzetesz(riport);
  return riport;
}
