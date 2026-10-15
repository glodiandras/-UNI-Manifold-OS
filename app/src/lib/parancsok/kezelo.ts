// Az egyetlen globális billentyűfigyelő (capture fázis): az akkordot a regiszter parancsára fordítja.

import { modalisNyitva } from '../fokusz/hatokor';
import { esemenybol, kanonikus, szerkesztheto } from './billentyuk';
import type { Regiszter } from './regiszter';

export function kezel(e: KeyboardEvent, reg: Regiszter): boolean {
  if (e.isComposing || e.defaultPrevented) return false;
  const a = esemenybol(e);
  if (!a) return false;
  // Szerkeszthető mezőben a módosító nélküli (vagy csak Shift-es) billentyű a gépelésé.
  if (!a.mod && !a.ctrl && !a.alt && szerkesztheto(e.target) && !/^F\d+$/.test(a.kulcs)) return false;
  const p = reg.akkordhoz(kanonikus(a));
  if (!p) return false;
  if (modalisNyitva() && !p.atfedesben) return false;
  // a szerkesztőben a CodeMirror azonos akkordja nyer (a CM a buborékolásban kapja meg)
  if (p.szerkesztoNyer && e.target instanceof Element && e.target.closest('.cm-editor')) return false;
  if (!reg.elerheto(p)) return false;
  e.preventDefault();
  e.stopPropagation();
  reg.futtat(p.id, 'billentyu');
  return true;
}

export function telepit(reg: Regiszter, cel: Window = window): () => void {
  const f = (e: KeyboardEvent) => void kezel(e, reg);
  cel.addEventListener('keydown', f, { capture: true });
  return () => cel.removeEventListener('keydown', f, { capture: true });
}
