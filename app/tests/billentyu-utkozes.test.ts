// C21 (T148, 2. audit A2-jovobeli-15): a parancs-regiszter billentyűi és a szerkesztő CodeMirror-keymapjei ütközés-próbája.
// A regiszter maga csak a saját parancsai közti ütközést fogja meg; a szerkesztőben a CodeMirror keymapje előbb fut, így egy
// regiszterbeli akkord, amelyet a CM is használ, a szerkesztőben csendben mást csinál (pl. a ⌘⇧L a `selectSelectionMatches`). Új
// ütközés csak indokolt kivételként (a lenti listában, okkal) kerülhet be.

import { describe, expect, it } from 'vitest';
import { closeBracketsKeymap, completionKeymap } from '@codemirror/autocomplete';
import { defaultKeymap, historyKeymap, indentWithTab } from '@codemirror/commands';
import { foldKeymap } from '@codemirror/language';
import { searchKeymap } from '@codemirror/search';
import type { KeyBinding } from '@codemirror/view';
import { kanonikus, normalizalLeiras, type Akkord } from '../src/lib/parancsok/billentyuk';

const FORRASOK = import.meta.glob('../src/**/*.{ts,svelte}', { query: '?raw', import: 'default', eager: true }) as Record<string, string>;

/** A CodeMirror kulcsleírása („Mod-Shift-l”, „Alt-ArrowUp”, „Shift-Mod-k”) a regiszter kanonikus alakjára (macOS: Mod = Meta = ⌘). */
export function cmAkkord(kulcs: string): string | null {
  const reszek = kulcs.split(/-(?!$)/);
  const nev = reszek.pop() ?? '';
  const a: Akkord = { mod: false, ctrl: false, alt: false, shift: false, kulcs: '' };
  for (const r of reszek) {
    if (/^(mod|cmd|meta|m)$/i.test(r)) a.mod = true;
    else if (/^(ctrl|control|c)$/i.test(r)) a.ctrl = true;
    else if (/^(alt|a)$/i.test(r)) a.alt = true;
    else if (/^(shift|s)$/i.test(r)) a.shift = true;
    else return null;
  }
  if (nev.length === 1) a.kulcs = nev.toLowerCase();
  else if (/^(Arrow(Left|Right|Up|Down)|Tab|Enter|Escape|Backspace|Delete|Home|End|PageUp|PageDown|F\d{1,2})$/.test(nev)) a.kulcs = nev;
  else if (nev === 'Space' || nev === ' ') a.kulcs = 'Space';
  else return null;
  return kanonikus(a);
}

function cmKulcsok(): Map<string, string> {
  const ki = new Map<string, string>();
  const keymapek: [string, readonly KeyBinding[]][] = [
    ['searchKeymap', searchKeymap], ['historyKeymap', historyKeymap], ['defaultKeymap', defaultKeymap],
    ['foldKeymap', foldKeymap], ['completionKeymap', completionKeymap], ['closeBracketsKeymap', closeBracketsKeymap],
    ['indentWithTab', [indentWithTab]],
  ];
  for (const [nev, km] of keymapek) {
    for (const b of km) {
      const k = b.mac ?? b.key;
      const a = k ? cmAkkord(k) : null;
      if (a && !ki.has(a)) ki.set(a, `${nev}: ${k}`);
    }
  }
  return ki;
}

/** A regiszter billentyű-leírásai a forrásban: a `billentyu: '…'` kulcs és a pozicionális alak (a szerkesztő
 *  `formaz(id, név, jel, 'Mod+B')` segédje) — különben a ⌘I ütközése a CM-mel láthatatlan maradna. */
const BILLENTYU_MINTAK = [
  /billentyu:\s*'([^'$]+)'/g,
  /formaz\(\s*'[^']*',\s*(?:tk\(\s*'[^']*'\s*\)|'[^']*'),\s*'[^']*',\s*'([^'$]+)'\s*\)/g,
];
function* billentyuLeirasok(forras: string): Generator<string> {
  for (const minta of BILLENTYU_MINTAK) for (const m of forras.matchAll(minta)) yield m[1];
}

function regiszterKulcsok(): Map<string, string> {
  const ki = new Map<string, string>();
  for (const [ut, forras] of Object.entries(FORRASOK)) {
    for (const leiras of billentyuLeirasok(forras)) {
      try {
        ki.set(normalizalLeiras(leiras), ut.replace('../src/', ''));
      } catch {
        /* nem akkord (pl. sablon-szöveg) */
      }
    }
  }
  return ki;
}

// Az indokolt kivételek: a regiszter parancsa a szerkesztőn KÍVÜL is él, vagy szándékosan ugyanazt teszi, mint a CM-é.
const KIVETELEK: Record<string, string> = {
  'Mod+f': 'a szerkesztő keresése maga a CM keresőpanelje (openSearchPanel) — ugyanaz a művelet',
  'Mod+Enter': 'a linkmegnyitás csak linken álló kurzornál érvényes; különben a CM üres sort beszúró parancsa fut',
  'Mod+Alt+ArrowDown':
    'az „Osztás lefelé” a szerkesztőn kívül él; a szerkesztőben a CM addCursorBelow-ja nyer (`szerkesztoNyer`, a kezelő ' +
    'kihagyja a CodeMirrorban; a parancsok.test.ts őrzi)',
  'Mod+i':
    'szándékos: a szerkesztőben a ⌘I a Dőlt (Obsidian-kiosztás), a CM selectParentSyntax-a helyett; csak fókuszált, írható ' +
    'szerkesztőben érvényes, máshol a CM-nek nincs szerepe',
};

describe('billentyű-ütközés a CodeMirror keymapjeivel (C21, T148)', () => {
  it('a fordítási jelölő nem rejtheti el a formázó gyorsbillentyűjét', () => {
    expect([...billentyuLeirasok("formaz('dolt', tk('Dőlt'), '*', 'Mod+I')")]).toEqual(['Mod+I']);
    expect([...billentyuLeirasok("formaz('dolt', 'Dőlt', '*', 'Mod+I')")]).toEqual(['Mod+I']);
  });

  it('a CM-leírás átalakítása', () => {
    expect(cmAkkord('Mod-Shift-l')).toBe('Mod+Shift+l');
    expect(cmAkkord('Shift-Mod-k')).toBe('Mod+Shift+k');
    expect(cmAkkord('Alt-ArrowUp')).toBe('Alt+ArrowUp');
    expect(cmAkkord('Mod-Alt-\\')).toBe('Mod+Alt+\\');
  });

  it('a ⌘⇧L foglalt a CM-ben, a ⌥⌘L szabad', () => {
    const cm = cmKulcsok();
    expect(cm.get('Mod+Shift+l')).toMatch(/searchKeymap/);
    expect(cm.has('Mod+Alt+l')).toBe(false);
    expect(regiszterKulcsok().get('Mod+Alt+l')).toBe('szerkeszto/index.ts');
  });

  it('nincs indokolatlan ütközés a regiszter és a szerkesztő keymapjei között', () => {
    const cm = cmKulcsok();
    const utkozes = [...regiszterKulcsok()].filter(([k]) => cm.has(k) && !(k in KIVETELEK)).map(([k, hol]) => `${k} (${hol} ↔ ${cm.get(k)})`);
    expect(utkozes).toEqual([]);
  });

  it('egy normalizált akkord a forrásban csak egyszer áll (a fenti Map-alapú gyűjtés nem nyelheti el, CX-005)', () => {
    const elofordulas = new Map<string, string[]>();
    for (const [ut, forras] of Object.entries(FORRASOK))
      for (const leiras of billentyuLeirasok(forras)) {
        let k: string;
        try {
          k = normalizalLeiras(leiras);
        } catch {
          continue;
        }
        elofordulas.set(k, [...(elofordulas.get(k) ?? []), ut]);
      }
    expect([...elofordulas].filter(([, hol]) => hol.length > 1)).toEqual([]);
  });

  it('a CX-005 akkordjai (⌥⌘← vissza, ⌥⌘→ előre, ⇧⌘T újranyitás, ⇧⌘2 osztás) a regiszterben vannak és a CM-ben szabadok', () => {
    const cm = cmKulcsok();
    const reg = regiszterKulcsok();
    for (const k of ['Mod+Alt+ArrowLeft', 'Mod+Alt+ArrowRight', 'Mod+Shift+t', 'Mod+Shift+2']) {
      expect(reg.get(k), k).toBe('alapParancsok.ts');
      expect(cm.has(k), k).toBe(false);
    }
  });

  it('az Asszisztens kézi hívása (J2): ⌘J és ⇧⌘J a regiszterben van, a CM-ben szabad', () => {
    const cm = cmKulcsok();
    const reg = regiszterKulcsok();
    for (const k of ['Mod+j', 'Mod+Shift+j']) {
      expect(reg.get(k), k).toBe('szerkeszto/index.ts');
      expect(cm.has(k), k).toBe(false);
    }
  });

  it('a pozicionális alak is látszik (⌘B, ⌘I, ⇧⌘H a szerkesztő formázó parancsai)', () => {
    const reg = regiszterKulcsok();
    for (const k of ['Mod+b', 'Mod+i', 'Mod+Shift+h']) expect(reg.get(k), k).toBe('szerkeszto/index.ts');
  });

  it('az „Osztás lefelé” a szerkesztőben a CM-nek enged (`szerkesztoNyer`)', () => {
    expect(FORRASOK['../src/alapParancsok.ts']).toMatch(/id: 'panel\.oszt-le'[^\n]*szerkesztoNyer: true/);
  });

  it('a kivétellista nem avul el', () => {
    const cm = cmKulcsok();
    const reg = regiszterKulcsok();
    expect(Object.keys(KIVETELEK).filter((k) => !(cm.has(k) && reg.has(k)))).toEqual([]);
  });
});
