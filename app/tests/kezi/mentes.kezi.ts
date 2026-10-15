// A mentés bájthűsége a vault klónján (C08 kész-feltétele). Futtatás: tests/kezi/szerkeszto_mentes.py (az
// indítja a core-t a klónra, és átadja a címét és a jegyzetek listáját).
//
// Jegyzetenként a szerkesztő valódi útja, DOM nélkül: a core fájl-API-ja → Dokumentum → EditorState a teljes
// bővítménykészlettel (Live Preview) → teljes elemzés és a blokkszintű díszítések → egy beírás és a
// visszatörlése (a Dokumentumon át, ahogy a nézet teszi) → kényszerített mentés `elso` + `pillanat`
// jelzővel. A szkript utána a klón minden fájlját összeveti a manifeszttel.

import { ensureSyntaxTree } from '@codemirror/language';
import { EditorState } from '@codemirror/state';
import { writeFileSync } from 'node:fs';
import { expect, it } from 'vitest';
import { bovitmenyek } from '../../src/szerkeszto/beallitas';
import { vaultApi } from '../../src/szerkeszto/dokumentum/api';
import { Dokumentum } from '../../src/szerkeszto/dokumentum/dokumentum.svelte';
import { blokkMezo } from '../../src/szerkeszto/elo/blokkok';

const CORE = process.env.MOS_KEZI_CORE;
const UTAK = process.env.MOS_KEZI_UTAK;
const RIPORT = process.env.MOS_KEZI_RIPORT;

it.skipIf(!CORE || !UTAK || !RIPORT)('a jegyzetek megnyitás + mentés után bájtra változatlanok', async () => {
  const api = vaultApi(CORE);
  const utak = JSON.parse(UTAK!) as string[];
  const eredmeny: Record<string, unknown>[] = [];
  for (const ut of utak) {
    const kezd = performance.now();
    const f = await api.olvas(ut);
    const dok = new Dokumentum(api, f);
    let state = EditorState.create({
      doc: dok.szoveg,
      extensions: bovitmenyek({ mod: 'elo', csakOlvashato: !!dok.csakOlvashato, ut, cimke: ut }),
    });
    ensureSyntaxTree(state, state.doc.length, 120_000);
    const diszites = state.field(blokkMezo).size;
    expect(dok.fajlSzoveg(state.doc), `${ut}: a szerkesztő szövege`).toBe(f.tartalom); // a szerkesztő LF-fel dolgozik, a Dokumentum illeszti vissza
    // beírás és visszatörlés a közepén (a nézet így adja tovább a Dokumentumnak)
    const kozep = state.doc.line(Math.max(1, Math.floor(state.doc.lines / 2))).to;
    const be = state.update({ changes: { from: kozep, insert: 'x' } });
    dok.valtozott(be.changes, be.newDoc, null);
    const ki = be.state.update({ changes: { from: kozep, to: kozep + 1 } });
    dok.valtozott(ki.changes, ki.newDoc, null);
    state = ki.state;
    expect(dok.fajlSzoveg(), `${ut}: a mentendő szöveg`).toBe(f.tartalom);
    const m = await dok.ment({ kenyszer: true, pillanat: true });
    expect(m.ok, `${ut}: a mentés`).toBe(true);
    eredmeny.push({
      ut,
      karakter: f.tartalom.length,
      sorok: state.doc.lines,
      sorveg: dok.sorveg,
      csak_olvashato: dok.csakOlvashato,
      diszitesek: diszites,
      pillanat: m.pillanat ?? null,
      ms: Math.round(performance.now() - kezd),
    });
  }
  writeFileSync(RIPORT!, JSON.stringify(eredmeny, null, 1));
});
