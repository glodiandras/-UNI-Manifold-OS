// A Live Preview (C08) állapotszinten: az aktív egység, a blokkszintű díszítések (táblázat, képlet,
// elválasztó, záró kerítés, összecsukott callout), és hogy a díszítés soha nem írja a szöveget (bájthűség).

import { ensureSyntaxTree } from '@codemirror/language';
import { EditorSelection, EditorState, Text } from '@codemirror/state';
import { Decoration, type DecorationSet } from '@codemirror/view';
import { describe, expect, it } from 'vitest';
import { bovitmenyek, markdownNyelv } from '../src/szerkeszto/beallitas';
import { aktiv, aktivBlokkok, aktivEgysegek } from '../src/szerkeszto/elo/aktivBlokk';
import { blokkMezo } from '../src/szerkeszto/elo/blokkok';
import { calloutHajtasValt } from '../src/szerkeszto/elo/hajtas';
import { ElvalasztoWidget, KepletElonezetWidget, KepletWidget } from '../src/szerkeszto/elo/widgetek';
import { TablaSzerkesztoWidget } from '../src/szerkeszto/notion/tablazat/szerkeszto';
import { korbefog } from '../src/szerkeszto/formazas';
import { ertesitesek } from '../src/lib/ertesites/ertesites.svelte';

const DOC = [
  '# Cím', //                                0
  '',
  'Bekezdés $x$ szöveg.', //                  2
  '',
  '| a | b |', //                            4
  '|---|---|',
  '| 1 | $|y|$ |',
  '',
  '$$', //                                   8
  '\\frac12',
  '$$',
  '',
  '---', //                                  12
  '',
  '```python', //                            14
  'print(1)',
  '```',
  '',
  '> [!warning]- Figyelem', //               18
  '> rejtett törzs',
  '',
  'Vége.', //                                21
].join('\n');

function allapot(doc = DOC, kurzorSor = 21, mod: 'elo' | 'forras' = 'elo') {
  const s = EditorState.create({
    doc,
    extensions: bovitmenyek({ mod, csakOlvashato: false, ut: 'proba.md', cimke: 'próba' }),
  });
  ensureSyntaxTree(s, s.doc.length, 5000);
  const pos = s.doc.line(kurzorSor + 1).from;
  return s.update({ selection: { anchor: pos } }).state;
}

function diszitesek(s: EditorState): { from: number; to: number; widget: string | null; block: boolean }[] {
  const ki: { from: number; to: number; widget: string | null; block: boolean }[] = [];
  const d: DecorationSet = s.field(blokkMezo);
  d.between(0, s.doc.length, (from, to, v: Decoration) => {
    const spec = v.spec as { widget?: object; block?: boolean };
    ki.push({ from, to, widget: spec.widget ? spec.widget.constructor.name : null, block: !!spec.block });
  });
  return ki;
}

function sorTartomany(s: EditorState, a: number, b = a) {
  return { from: s.doc.line(a + 1).from, to: s.doc.line(b + 1).to };
}

describe('aktív egység', () => {
  it('a kurzort tartalmazó levélblokk, teljes sorokra', () => {
    const s = allapot(DOC, 2);
    expect(aktivEgysegek(s)).toEqual([sorTartomany(s, 2)]);
    const t = allapot(DOC, 5);
    expect(aktivEgysegek(t)).toEqual([sorTartomany(t, 4, 6)]);
  });

  it('a kijelölés minden érintett egysége; a callout fejléce és törzse külön', () => {
    const s = allapot();
    const k = s.update({ selection: EditorSelection.range(s.doc.line(3).from, s.doc.line(6).from + 2) }).state;
    // a szomszédos egységek (a köztük álló üres sorral) egy tartománnyá vonódnak össze
    expect(aktivEgysegek(k)).toEqual([{ from: k.doc.line(3).from, to: k.doc.line(7).to }]);
    expect(aktiv(aktivEgysegek(k), k.doc.line(1).from, k.doc.line(1).to)).toBe(false);
    expect(aktivEgysegek(allapot(DOC, 18))).toEqual([sorTartomany(s, 18)]);
    expect(aktivEgysegek(allapot(DOC, 19))).toEqual([sorTartomany(s, 19)]);
  });
});

describe('blokkszintű díszítések', () => {
  it('nem aktív állapotban: képlet, elválasztó widget; a záró kerítés és a csukott törzs rejtve; a táblázat mindig a vizuális szerkesztő', () => {
    const s = allapot();
    const d = diszitesek(s);
    expect(d).toContainEqual({ ...sorTartomany(s, 4, 6), widget: TablaSzerkesztoWidget.name, block: true });
    expect(d).toContainEqual({ ...sorTartomany(s, 8, 10), widget: KepletWidget.name, block: true });
    expect(d).toContainEqual({ ...sorTartomany(s, 12), widget: ElvalasztoWidget.name, block: true });
    expect(d).toContainEqual({ ...sorTartomany(s, 16), widget: null, block: true });
    expect(d).toContainEqual({ ...sorTartomany(s, 19), widget: null, block: true });
  });

  it('az aktív képletblokk forrásként látszik, alatta élő előnézet; a táblázat az aktív egységben is a vizuális szerkesztő marad (C09)', () => {
    const t = diszitesek(allapot(DOC, 5));
    expect(t.some((x) => x.widget === TablaSzerkesztoWidget.name)).toBe(true);
    const k = diszitesek(allapot(DOC, 9));
    expect(k.some((x) => x.widget === KepletWidget.name)).toBe(false);
    expect(k.some((x) => x.widget === KepletElonezetWidget.name)).toBe(true);
  });

  it('a callout kibontása nézet-állapot: a törzs megjelenik, a szöveg nem változik', () => {
    const s = allapot();
    const kulcs = s.doc.line(19).from;
    const nyitva = s.update({ effects: calloutHajtasValt.of({ pos: kulcs, csukva: false }) }).state;
    expect(diszitesek(nyitva).some((x) => x.from === s.doc.line(20).from)).toBe(false);
    expect(nyitva.doc.toString()).toBe(DOC);
  });

  it('a Forrás-módban nincs blokkszintű díszítés (a mező nincs is jelen)', () => {
    const s = allapot(DOC, 21, 'forras');
    expect(s.field(blokkMezo, false)).toBeUndefined();
    expect(s.field(aktivBlokkok, false)).toBeUndefined();
  });
});

describe('bájthűség: a szerkesztő állapota a szöveget változatlanul adja vissza', () => {
  const minta = [
    DOC,
    'sor vége nélkül',
    '\ttabulátor és NBSP és​nulla szélességű',
    'ékezet NFD-ben, ő NFC-ben\n',
    '---\nTags: [a]\n---\n',
    '\n\n\nüres sorok\n\n',
    '﻿BOM-mal kezdődik\n',
    '> [!note]\n> $$\n> x\n> $$\n',
  ];

  it.each(minta.map((m) => [m]))('%j', (m) => {
    const s = allapot(m, 0);
    expect(s.doc.toString()).toBe(m);
    // egy beírás és visszatörlés után is
    const a = s.update({ changes: { from: 1, insert: 'X' } }).state;
    const b = a.update({ changes: { from: 1, to: 2 } }).state;
    expect(b.doc.toString()).toBe(m);
  });

  it('a CRLF-es fájl a szerkesztőben LF-es sorokkal él (nincs `lineSeparator`), a visszaírás `\\r\\n`-nel bájtra azonos (T118)', () => {
    const crlf = '# Cím\r\n\r\nszöveg\r\nmásik\r\n';
    const s = EditorState.create({
      doc: Text.of(crlf.split(/\r\n?|\n/)), // ahogy a `Dokumentum` adja
      extensions: bovitmenyek({ mod: 'elo', csakOlvashato: false, ut: 'a.md', cimke: 'a' }),
    });
    expect(s.doc.lines).toBe(5);
    expect(s.lineBreak).toBe('\n');
    expect(s.doc.sliceString(0, s.doc.length, '\r\n')).toBe(crlf);
    // a beillesztett (LF-, CR- vagy CRLF-es) szöveg sorokra bomlik, nem marad magányos sortörés a sorban
    expect(s.update({ changes: { from: 0, insert: 'a\nb' } }).state.doc.lines).toBe(6);
    expect(s.update(s.replaceSelection('x\r\ny\rz')).state.doc.lines).toBe(7);
  });
});

describe('formázás (⌘B, ⌘I, ⌘⇧H)', () => {
  function nezet(doc: string, from: number, to = from, readOnly = false) {
    let state = EditorState.create({ doc, selection: EditorSelection.range(from, to), extensions: EditorState.readOnly.of(readOnly) });
    return {
      get state() {
        return state;
      },
      dispatch(tr: Parameters<EditorState['update']>[0] | ReturnType<EditorState['update']>) {
        state = 'state' in tr ? tr.state : state.update(tr).state;
      },
    } as unknown as import('@codemirror/view').EditorView;
  }

  it('körbefog, a már körbefogottat leveszi, üres kijelölésnél a jelölők közé áll', () => {
    const v = nezet('egy szó itt', 4, 7);
    korbefog(v, '**');
    expect(v.state.doc.toString()).toBe('egy **szó** itt');
    expect(v.state.selection.main).toMatchObject({ from: 6, to: 9 });
    korbefog(v, '**');
    expect(v.state.doc.toString()).toBe('egy szó itt');
    const u = nezet('ab', 1);
    korbefog(u, '==');
    expect(u.state.doc.toString()).toBe('a====b');
    expect(u.state.selection.main.head).toBe(3);
    const k = nezet('**x**', 0, 5);
    korbefog(k, '**');
    expect(k.state.doc.toString()).toBe('x');
  });

  it('csak olvasható állapotban nem ír', () => {
    const v = nezet('abc', 0, 3, true);
    expect(korbefog(v, '*')).toBe(false);
    expect(v.state.doc.toString()).toBe('abc');
  });

  // A kézi kör F4-e (C10.7): az üres kijelölésű kiemelés önálló `====` sora a fölötte álló szövegsort
  // setext-fejléccé tette (a Newton-jegyzetben a kép sora lett H1).
  function mdNezet(doc: string, kurzor: number) {
    let state = EditorState.create({ doc, selection: EditorSelection.cursor(kurzor), extensions: markdownNyelv() });
    return {
      get state() {
        return state;
      },
      dispatch(tr: Parameters<EditorState['update']>[0] | ReturnType<EditorState['update']>) {
        state = 'state' in tr ? tr.state : state.update(tr).state;
      },
    } as unknown as import('@codemirror/view').EditorView;
  }

  function csomopontok(s: EditorState): Set<string> {
    const nevek = new Set<string>();
    ensureSyntaxTree(s, s.doc.length, 5000)!.iterate({ enter: (n) => void nevek.add(n.name) });
    return nevek;
  }

  it('szövegsor alatti üres sorban a ==== nem lesz setext-aláhúzás: új bekezdésbe kerül, a kurzor középen (F4)', () => {
    for (const [doc, vart] of [
      ['szöveg\n', 'szöveg\n\n===='],
      ['![[IMG_1578.JPG]]\n', '![[IMG_1578.JPG]]\n\n===='],
      ['> szöveg\n> ', '> szöveg\n>\n> ===='],
      ['- elem\n  ', '- elem\n\n  ===='],
    ]) {
      const v = mdNezet(doc, doc.length);
      korbefog(v, '==');
      expect(v.state.doc.toString(), doc).toBe(vart);
      expect([...csomopontok(v.state)].filter((n) => n.startsWith('SetextHeading')), doc).toEqual([]);
      const k = v.state.selection.main.head;
      expect(k, doc).toBe(vart.length - 2);
      v.dispatch({ changes: { from: k, insert: 'x' }, selection: { anchor: k + 1 } });
      expect(csomopontok(v.state).has('Highlight'), doc).toBe(true);
    }
  });

  it('nem üres sorban és dokumentum elején a viselkedés változatlan', () => {
    const v = mdNezet('szöveg\nab', 8);
    korbefog(v, '==');
    expect(v.state.doc.toString()).toBe('szöveg\na====b');
    const u = mdNezet('', 0);
    korbefog(u, '==');
    expect(u.state.doc.toString()).toBe('====');
    expect(u.state.selection.main.head).toBe(2);
  });

  it('üres sorban a ~~ és a ** nem nyit kódkerítést / vízszintes vonalat: kijelölt helyőrző a jelölők között (C32)', () => {
    for (const [doc, kurzor, jel, vart] of [
      ['', 0, '~~', '~~szöveg~~'],
      ['Előtte\n\n', 8, '~~', 'Előtte\n\n~~szöveg~~'],
      ['> ', 2, '~~', '> ~~szöveg~~'],
      ['', 0, '**', '**szöveg**'],
    ] as const) {
      const v = mdNezet(doc, kurzor);
      korbefog(v, jel);
      expect(v.state.doc.toString(), `${jel} ${JSON.stringify(doc)}`).toBe(vart);
      const r = v.state.selection.main;
      expect(v.state.sliceDoc(r.from, r.to)).toBe('szöveg');
    }
    const s = mdNezet('ab', 1); // szöveg mellett nincs helyőrző
    korbefog(s, '~~');
    expect(s.state.doc.toString()).toBe('a~~~~b');
  });

  it('a ==kiemelés== beszúrása figyelmeztet (a munkaterület jegyzetszabálya), a levétele nem', () => {
    ertesitesek.lista.splice(0);
    const v = mdNezet('egy szó', 4);
    v.dispatch({ selection: EditorSelection.range(4, 7) });
    korbefog(v, '==');
    expect(v.state.doc.toString()).toBe('egy ==szó==');
    expect(ertesitesek.lista.at(-1)?.cim).toContain('==kiemelés==');
    ertesitesek.lista.splice(0);
    korbefog(v, '==');
    expect(v.state.doc.toString()).toBe('egy szó');
    expect(ertesitesek.lista).toHaveLength(0);
    korbefog(v, '**');
    expect(ertesitesek.lista).toHaveLength(0);
  });
});
