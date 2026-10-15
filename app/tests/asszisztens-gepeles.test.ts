// A gépelési késleltetés kapuja (C30b-mag): a linkjavaslat a gépelés útvonalán csak a dekorációk átvezetését végzi. A teszt
// a bővítmény SAJÁT tranzakciónkénti költségét méri javaslatok nélkül és 50 javaslattal egy 5000 soros jegyzetben:
//   - állapot-szinten (`state.update`: a StateField átvezetése, az érvényesség, a bekezdés-határ, a dekoráció-építés);
//   - nézet-szinten egy csak a bővítményt és a Markdown-nyelvet hordozó nézetben (a dekoráció a DOM-ig).
// A teljes Live Preview 5000 soron jsdom-ban nem használható alap (itt ~400 ms/leütés layout és méretezés nélkül): a valódi
// motorban a `szintetikusMeres` (⌘P → Fejlesztő) a K-tétel próbája, a NAPLO ott méri a végeredményt.

import { EditorState } from '@codemirror/state';
import { EditorView } from '@codemirror/view';
import { afterEach, describe, expect, it, vi } from 'vitest';
import {
  javaslatBeallitas,
  javaslatBeerkezett,
  javaslatBovitmeny,
  type JavaslatKliens,
  lathatoJavaslatok,
} from '../src/szerkeszto/asszisztens/javaslat';
import type { Javaslat } from '../src/szerkeszto/asszisztens/javaslatSegedek';

afterEach(() => {
  vi.useRealTimers();
  document.body.textContent = '';
});

const KEZD_SOR = 2500;
const KLIENS: JavaslatKliens = {
  emlitesek: async () => ({ ut: 'J.md', emlitesek: [], kapcsolo: true }),
  dontes: async () => ({ fogadva: true }),
  kuszob: async () => ({ szint: 'alap', szorzo: 1 }),
};

function jegyzet(javaslatSor: (i: number) => boolean): string {
  const sorok: string[] = [];
  for (let i = 0; i < 5000; i++)
    sorok.push(javaslatSor(i) ? `Sor ${i}: Newton törvényei és más szöveg.` : `Sor ${i}: sima szöveg, **félkövérrel** és [[Link]].`);
  return sorok.join('\n');
}

/** A `doc` összes "Newton" előfordulása javaslatként (legfeljebb 50, mint a core `emlites_max`-a). */
function javaslatok(doc: string): Javaslat[] {
  const ki: Javaslat[] = [];
  for (const m of doc.matchAll(/Newton/g)) {
    if (ki.length >= 50) break;
    ki.push({ id: ki.length + 1, from: m.index!, to: m.index! + 6, szoveg: 'Newton', celUt: 'Newton.md', kulcs: 'Newton.md|newton' });
  }
  return ki;
}

// a bővítmény SAJÁT költsége: a Markdown-elemző és a Live Preview a mérésben nincs (azok a C08 kapu tárgya; 5000 soron
// jsdom-ban leütésenként ~90 ms, ami ennek a méréstől független alap); a bővítmény a szintaxisfát csak a válasz
// feldolgozásánál kérdezi
const kiterjesztesek = (javaslatLegyen: boolean) => [
  ...(javaslatLegyen ? [javaslatBeallitas.of({ ut: 'J.md', kapcsolo: () => true, linkCel: async () => 'Newton', kliens: KLIENS })] : []),
  javaslatBovitmeny(),
];

const mediann = (a: number[]) => [...a].sort((x, y) => x - y)[Math.floor(a.length / 2)];
const p95 = (a: number[]) => [...a].sort((x, y) => x - y)[Math.floor(a.length * 0.95)];

/** A kurzor a `KEZD_SOR` sor végén; 50 "Newton" a doc elején vagy a kurzor körül. */
function allapotKeszit(doc: string, javaslatLegyen: boolean): EditorState {
  const kezd = doc.split('\n').slice(0, KEZD_SOR).join('\n').length;
  let s = EditorState.create({ doc, selection: { anchor: kezd }, extensions: kiterjesztesek(true) });
  if (javaslatLegyen) s = s.update({ effects: javaslatBeerkezett.of({ lista: javaslatok(doc), max: 5 }) }).state;
  return s;
}

function allapotMeres(s: EditorState, n = 2000): number[] {
  const idok: number[] = [];
  let pos = s.selection.main.head;
  for (let i = 0; i < n; i++) {
    const t0 = performance.now();
    s = s.update({ changes: { from: pos, insert: 'a' }, selection: { anchor: pos + 1 }, userEvent: 'input.type' }).state;
    idok.push(performance.now() - t0);
    pos++;
  }
  return idok;
}

function nezetMeres(s: EditorState, n = 200): number[] {
  const hely = document.createElement('div');
  document.body.appendChild(hely);
  const v = new EditorView({ state: s, parent: hely });
  const idok: number[] = [];
  let pos = s.selection.main.head;
  for (let i = 0; i < n; i++) {
    const t0 = performance.now();
    v.dispatch({ changes: { from: pos, insert: 'a' }, selection: { anchor: pos + 1 }, userEvent: 'input.type' });
    idok.push(performance.now() - t0);
    pos++;
  }
  v.destroy();
  return idok;
}

describe('gépelési késleltetés: javaslat ki / be (a bővítmény saját költsége, 5000 sor)', () => {
  const szort = jegyzet((i) => i % 100 === 0); // 50 javaslat szórva: a kurzor bekezdésében 1
  const egyBekezdes = jegyzet((i) => i > KEZD_SOR - 30 && i < KEZD_SOR + 20); // legrosszabb eset: mind az 50 a kurzor körül

  for (const [nev, doc] of [['szórt', szort], ['egy bekezdés', egyBekezdes]] as const) {
    it(`állapot-szintű tranzakció: ${nev}`, { timeout: 60_000 }, () => {
      const ki = allapotKeszit(doc, false);
      const be = allapotKeszit(doc, true);
      expect(lathatoJavaslatok(be).length).toBeGreaterThan(0);
      allapotMeres(ki, 200); // bemelegítés
      allapotMeres(be, 200);
      const kiIdok = allapotMeres(ki);
      const beIdok = allapotMeres(be);
      console.info(
        `[C30b-mag] állapot-tranzakció (${nev}, ${lathatoJavaslatok(be).length} javaslat): ki p50 ${mediann(kiIdok).toFixed(3)} / p95 ${p95(kiIdok).toFixed(3)} ms; ` +
          `be p50 ${mediann(beIdok).toFixed(3)} / p95 ${p95(beIdok).toFixed(3)} ms`,
      );
      // a kapu: a javaslat leütésenként legfeljebb ~1 ms-ot tesz hozzá (a keret 16 ms)
      expect(mediann(beIdok)).toBeLessThanOrEqual(mediann(kiIdok) + 1);
      expect(p95(beIdok)).toBeLessThanOrEqual(p95(kiIdok) + 2);
    });

    it(`nézet-szintű dispatch (a dekorációtól a DOM-ig): ${nev}`, { timeout: 120_000 }, () => {
      const ki = allapotKeszit(doc, false);
      const be = allapotKeszit(doc, true);
      nezetMeres(ki, 30);
      nezetMeres(be, 30);
      const kiIdok = nezetMeres(ki);
      const beIdok = nezetMeres(be);
      console.info(
        `[C30b-mag] nézet-dispatch (${nev}): ki p50 ${mediann(kiIdok).toFixed(2)} / p95 ${p95(kiIdok).toFixed(2)} ms; ` +
          `be p50 ${mediann(beIdok).toFixed(2)} / p95 ${p95(beIdok).toFixed(2)} ms`,
      );
      expect(mediann(beIdok)).toBeLessThanOrEqual(mediann(kiIdok) * 1.5 + 1);
      expect(p95(beIdok)).toBeLessThanOrEqual(p95(kiIdok) * 1.5 + 3);
    });
  }

  it('a core-kérés nem a gépelés útvonalán indul: leütésenként egy időzítő áll újra, a szöveg a csend végén épül', { timeout: 30_000 }, async () => {
    vi.useFakeTimers();
    let szovegHivas = 0;
    const kliens: JavaslatKliens = {
      ...KLIENS,
      emlitesek: async (_u, szoveg) => {
        szovegHivas++;
        expect(szoveg.length).toBeGreaterThan(1000);
        return { ut: 'J.md', emlitesek: [], kapcsolo: true };
      },
    };
    const hely = document.createElement('div');
    document.body.appendChild(hely);
    const v = new EditorView({
      state: EditorState.create({
        doc: szort.split('\n').slice(0, 400).join('\n'),
        selection: { anchor: 10 },
        extensions: [javaslatBeallitas.of({ ut: 'J.md', kapcsolo: () => true, linkCel: async () => 'x', kliens }), javaslatBovitmeny()],
      }),
      parent: hely,
    });
    for (let i = 0; i < 100; i++) v.dispatch({ changes: { from: 10 + i, insert: 'a' }, userEvent: 'input.type' });
    expect(szovegHivas).toBe(0); // a leütések alatt egy kérés sem ment ki
    await vi.advanceTimersByTimeAsync(1500);
    expect(szovegHivas).toBe(1); // a csend végén egyetlen
    v.destroy();
  });

  it('a C25c-hasonlóság kérése (C30b) sem a gépelés útvonalán indul: leütés alatt 0, a csend végén egyetlen kérés', { timeout: 30_000 }, async () => {
    vi.useFakeTimers();
    let hasonlosagHivas = 0;
    let emlitesHivas = 0;
    const kliens: JavaslatKliens = {
      ...KLIENS,
      kuszob: async () => ({ szint: 'alap', szorzo: 1, hasonlosag: 0.55 }),
      emlitesek: async (_u, szoveg) => {
        emlitesHivas++;
        const kezd = Array.from(szoveg.slice(0, szoveg.indexOf('Newton'))).length;
        return {
          ut: 'J.md',
          kapcsolo: true,
          emlitesek: [{ kezd, veg: kezd + 6, sor: 1, oszlop: 0, szoveg: 'Newton', cel: 'Newton.md', tobbertelmu: false, jeloltek: [], forras: 'nev' }],
        };
      },
      hasonlosag: async (_u, celok) => {
        hasonlosagHivas++;
        return { ut: 'J.md', allapot: 'ok', elavult: false, pontok: Object.fromEntries(celok.map((c) => [c, 0.9])) };
      },
    };
    const hely = document.createElement('div');
    document.body.appendChild(hely);
    const v = new EditorView({
      state: EditorState.create({
        doc: 'Newton ' + szort.split('\n').slice(0, 400).join('\n'),
        selection: { anchor: 10 },
        extensions: [javaslatBeallitas.of({ ut: 'J.md', kapcsolo: () => true, linkCel: async () => 'x', kliens }), javaslatBovitmeny()],
      }),
      parent: hely,
    });
    for (let i = 0; i < 100; i++) v.dispatch({ changes: { from: 10 + i, insert: 'a' }, userEvent: 'input.type' });
    expect([emlitesHivas, hasonlosagHivas]).toEqual([0, 0]); // a leütések alatt sem az említés-, sem a hasonlóság-kérés nem ment ki
    await vi.advanceTimersByTimeAsync(1500);
    expect([emlitesHivas, hasonlosagHivas]).toEqual([1, 1]); // a csend végén egy-egy, egymás után
    v.destroy();
  });
});
