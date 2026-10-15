// A Notion-réteg tesztjeinek közös segédei (C09): szerkesztőnézet jsdom-ban, gépelés, billentyű; a tiszta
// műveletek tesztjeihez az `allapot`, a hibátlan elemzés és a szintaxisfa szerkezet-összevetése (T125).

import { ensureSyntaxTree } from '@codemirror/language';
import { EditorState } from '@codemirror/state';
import { EditorView } from '@codemirror/view';
import type { Tree } from '@lezer/common';
import { expect } from 'vitest';
import { bovitmenyek, markdownNyelv } from '../src/szerkeszto/beallitas';
import { calloutAdat } from '../src/szerkeszto/markdown/callout';
import { obsidianElemzo } from '../src/szerkeszto/markdown/elemzo';

/**
 * A szöveg TELJES szintaxisfája. Az `ensureSyntaxTree(…)` visszaadott fáját kell bejárni: ha az időkorlátig az elemzés nem
 * készül el, `null` jön, és a `syntaxTree(state)` ilyenkor a részleges fát adná — terhelés alatt ettől ingadozott a
 * `notion-tablazat` teszt (T009: 1/7). Ha nem készül el, egyértelmű hiba, nem hamis „nincs táblázat”.
 */
export function teljesFa(state: EditorState, idoMs = 5000): Tree {
  const fa = ensureSyntaxTree(state, state.doc.length, idoMs);
  if (!fa) throw new Error(`a szintaxisfa ${idoMs} ms alatt nem készült el (a gép terhelt, vagy a dokumentum túl nagy)`);
  return fa;
}

const nezetek: EditorView[] = [];

export function nezet(doc: string, kurzor = doc.length, csakOlvashato = false): EditorView {
  const hely = document.createElement('div');
  document.body.appendChild(hely);
  const state = EditorState.create({
    doc,
    selection: { anchor: kurzor },
    extensions: bovitmenyek({ mod: 'elo', csakOlvashato, ut: 'Jegyzet.md', cimke: 'próba', linkNev: () => 'Jegyzet' }),
  });
  const v = new EditorView({ state, parent: hely });
  ensureSyntaxTree(v.state, v.state.doc.length, 5000);
  nezetek.push(v);
  return v;
}

/** Az `afterEach`-ből: a nézetek megszüntetése. */
export function tisztit(): void {
  while (nezetek.length) nezetek.pop()!.destroy();
  document.body.textContent = '';
}

/** Karakterenkénti gépelés a kijelölés helyére (a `/` menü és a beviteli esemény úgy látja, mint a billentyűt). */
export function gepel(v: EditorView, szoveg: string): void {
  for (const c of szoveg) {
    const r = v.state.selection.main;
    v.dispatch({ changes: { from: r.from, to: r.to, insert: c }, selection: { anchor: r.from + 1 }, userEvent: 'input.type' });
  }
}

export function billentyu(v: EditorView, key: string, opciok: KeyboardEventInit = {}): KeyboardEvent {
  const e = new KeyboardEvent('keydown', { key, bubbles: true, cancelable: true, ...opciok });
  v.contentDOM.dispatchEvent(e);
  return e;
}

// ---------------------------------------------------------------------- tiszta műveletek: állapot és szerkezet

/** Szerkesztőállapot a tiszta műveletekhez (nézet nélkül); `crlf` esetén a dokumentum sorvége `\r\n`. */
export function allapot(doc: string, crlf = false): EditorState {
  const s = EditorState.create({
    doc,
    extensions: [markdownNyelv(), ...(crlf ? [EditorState.lineSeparator.of('\r\n')] : [])],
  });
  ensureSyntaxTree(s, s.doc.length, 5000);
  return s;
}

/** A dokumentum hibátlanul elemződik: nincs hibacsomópont. Önmagában gyakorlatilag nem bukhat (a Lezer-markdown
 *  nem ad hibacsomópontot), ezért a `szerkezet`-összevetés a tényleges kapu. */
export function hibatlan(szoveg: string): boolean {
  let hiba = false;
  obsidianElemzo.parse(szoveg).iterate({
    enter(n) {
      if (n.type.isError) hiba = true;
    },
  });
  return !hiba;
}

/** Egy dokumentum szintaxisfájának ujjlenyomata: a legfelső szintű csomópontok nevei, a csomópont-hisztogram, és
 *  az idézet / callout / táblázat / Setext-fejezet szám (a teljes fában). */
export interface Szerkezet {
  felso: string[];
  db: Record<string, number>;
  /** a nem callout idézetek száma */
  idezet: number;
  callout: number;
  tabla: number;
  setext: number;
}

/** A szöveg szerkezete; hibacsomópontra dob. A szöveg sorvége `\n` legyen (CRLF-nél a hívó normalizál). */
export function szerkezet(lf: string): Szerkezet {
  const fa = obsidianElemzo.parse(lf);
  const olvas = (a: number, b: number) => lf.slice(a, b);
  const ki: Szerkezet = { felso: [], db: {}, idezet: 0, callout: 0, tabla: 0, setext: 0 };
  for (let c = fa.topNode.firstChild; c; c = c.nextSibling) ki.felso.push(c.name);
  fa.iterate({
    enter(n) {
      if (n.type.isError) throw new Error(`hibacsomópont a ${n.from}. pozíciónál: ${JSON.stringify(lf)}`);
      ki.db[n.name] = (ki.db[n.name] ?? 0) + 1;
      if (n.name === 'Blockquote') {
        if (calloutAdat(n.node, olvas)) ki.callout++;
        else ki.idezet++;
      } else if (n.name === 'Table') ki.tabla++;
      else if (n.name.startsWith('SetextHeading')) ki.setext++;
    },
  });
  return ki;
}

/** A két szöveg (vagy szerkezet) azonos szerkezetű: ugyanazok a legfelső szintű csomópontok, ugyanannyi
 *  idézet/callout/táblázat/Setext, és azonos csomópont-hisztogram. Az `uzenet` a bukás üzenetébe kerül. */
export function szerkezetEgyezik(ki: string | Szerkezet, elvart: string | Szerkezet, uzenet = ''): void {
  const k = typeof ki === 'string' ? szerkezet(ki) : ki;
  const e = typeof elvart === 'string' ? szerkezet(elvart) : elvart;
  const cimke = uzenet || (typeof ki === 'string' ? JSON.stringify(ki) : 'szerkezet');
  expect(k.felso, `${cimke}: legfelső szint`).toEqual(e.felso);
  expect([k.idezet, k.callout, k.tabla, k.setext], `${cimke}: idézet/callout/táblázat/setext`).toEqual([e.idezet, e.callout, e.tabla, e.setext]);
  expect(k.db, `${cimke}: csomópont-hisztogram`).toEqual(e.db);
}
