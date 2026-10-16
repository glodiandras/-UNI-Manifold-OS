// Billentyűakkordok: leírás („Mod+Shift+M”), illesztés a KeyboardEvent-re, megjelenítés (⌘⇧M).
//
// A `Mod` macOS-en a ⌘. Betűknél az `event.key` számít (a magyar QWERTZ-en is a felirat szerinti betű);
// ha az Option a betűt átírja (⌥P → π), az `event.code` betűje. Számoknál mindig az `event.code`.
// Kerüljük a magyar kiosztáson csak AltGr/Option-nel elérhető jeleket (\ [ ] { }).

import { t } from '../i18n';
export interface Akkord {
  mod: boolean;
  ctrl: boolean;
  alt: boolean;
  shift: boolean;
  kulcs: string; // kisbetű, számjegy, vagy név: ArrowRight, Tab, Enter, Escape, F6, …
}

const NEVEK: Record<string, string> = {
  esc: 'Escape',
  escape: 'Escape',
  enter: 'Enter',
  tab: 'Tab',
  space: 'Space',
  left: 'ArrowLeft',
  right: 'ArrowRight',
  up: 'ArrowUp',
  down: 'ArrowDown',
  arrowleft: 'ArrowLeft',
  arrowright: 'ArrowRight',
  arrowup: 'ArrowUp',
  arrowdown: 'ArrowDown',
  backspace: 'Backspace',
  delete: 'Delete',
  home: 'Home',
  end: 'End',
  pageup: 'PageUp',
  pagedown: 'PageDown',
};

function kulcsNev(k: string): string {
  const kis = k.toLowerCase();
  if (NEVEK[kis]) return NEVEK[kis];
  if (/^f\d{1,2}$/.test(kis)) return kis.toUpperCase();
  if (kis.length === 1) return kis;
  throw new Error(`ismeretlen billentyű: ${k}`); // i18n-ignore: programozói hiba
}

export function elemez(leiras: string): Akkord {
  const reszek = leiras.split('+').map((r) => r.trim());
  const a: Akkord = { mod: false, ctrl: false, alt: false, shift: false, kulcs: '' };
  for (const r of reszek.slice(0, -1)) {
    const k = r.toLowerCase();
    if (k === 'mod' || k === 'cmd' || k === 'meta') a.mod = true;
    else if (k === 'ctrl') a.ctrl = true;
    else if (k === 'alt' || k === 'opt') a.alt = true;
    else if (k === 'shift') a.shift = true;
    else throw new Error(`ismeretlen módosító: ${r} (${leiras})`); // i18n-ignore: programozói hiba
  }
  a.kulcs = kulcsNev(reszek[reszek.length - 1]);
  return a;
}

/** Egységes alak (a regiszter kulcsa): Mod+Ctrl+Alt+Shift+kulcs. */
export function kanonikus(a: Akkord): string {
  return [a.mod && 'Mod', a.ctrl && 'Ctrl', a.alt && 'Alt', a.shift && 'Shift', a.kulcs].filter(Boolean).join('+');
}

export function normalizalLeiras(leiras: string): string {
  return kanonikus(elemez(leiras));
}

/** Az esemény akkordja, vagy null, ha csak módosító billentyű. */
export function esemenybol(e: KeyboardEvent): Akkord | null {
  if (['Meta', 'Control', 'Alt', 'Shift', 'CapsLock', 'Dead'].includes(e.key)) return null;
  let kulcs: string;
  if (/^Digit\d$/.test(e.code)) kulcs = e.code.slice(5);
  else if (/^Numpad\d$/.test(e.code)) kulcs = e.code.slice(6);
  else if (e.key.length === 1 && /[a-z]/i.test(e.key)) kulcs = e.key.toLowerCase();
  else if (/^Key[A-Z]$/.test(e.code) && (e.altKey || e.key.length === 1)) kulcs = e.code.slice(3).toLowerCase();
  else if (e.key === ' ') kulcs = 'Space';
  else if (e.key.length === 1) kulcs = e.key;
  else {
    try {
      kulcs = kulcsNev(e.key);
    } catch {
      return null;
    }
  }
  return { mod: e.metaKey, ctrl: e.ctrlKey, alt: e.altKey, shift: e.shiftKey, kulcs };
}

const JEL: Record<string, string> = {
  ArrowLeft: '←',
  ArrowRight: '→',
  ArrowUp: '↑',
  ArrowDown: '↓',
  Enter: '↩',
  Tab: '⇥',
  Escape: 'esc',
  get Space() { return t('Szóköz'); },
  Backspace: '⌫',
  Delete: '⌦',
};

/** macOS-szokás szerinti jelek, a sorrend ⌃⌥⇧⌘: „Mod+Shift+M” → „⇧⌘M”. */
export function megjelenit(leiras: string): string {
  const a = elemez(leiras);
  const k = JEL[a.kulcs] ?? (a.kulcs.length === 1 ? a.kulcs.toUpperCase() : a.kulcs);
  return `${a.ctrl ? '⌃' : ''}${a.alt ? '⌥' : ''}${a.shift ? '⇧' : ''}${a.mod ? '⌘' : ''}${k}`;
}

/** Az `aria-keyshortcuts` értéke: „Meta+Shift+M”. */
export function ariaAlak(leiras: string): string {
  const a = elemez(leiras);
  const k = a.kulcs.length === 1 ? a.kulcs.toUpperCase() : a.kulcs;
  return [a.ctrl && 'Control', a.alt && 'Alt', a.shift && 'Shift', a.mod && 'Meta', k].filter(Boolean).join('+');
}

/** Szerkeszthető elemben áll-e a fókusz (ott a módosító nélküli billentyű a gépelésé). */
export function szerkesztheto(cel: EventTarget | null): boolean {
  if (!(cel instanceof HTMLElement)) return false;
  if (cel.isContentEditable) return true;
  if (cel instanceof HTMLTextAreaElement || cel instanceof HTMLSelectElement) return true;
  if (cel instanceof HTMLInputElement) {
    return !['button', 'checkbox', 'radio', 'range', 'submit', 'reset', 'color', 'file'].includes(cel.type);
  }
  return false;
}
