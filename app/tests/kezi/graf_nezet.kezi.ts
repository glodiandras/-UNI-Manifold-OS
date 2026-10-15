// A gráfnézet adatmodellje a valódi vault gráfján (C13 kész-feltétele): ugyanaz a csúcs- és élhalmaz, mint a core gráfja.
// Futtatás: tests/kezi/graf_nezet_paritas.py (az adja át a core `graf_api()`, `fa()` és `graf_meta()` kimenetét JSON-ban).

import { readFileSync, writeFileSync } from 'node:fs';
import { expect, it } from 'vitest';
import { GrafAdat, lathatoElDb, lathatosag, szinCsoportok, type FajlTipus } from '../../src/lib/graf/modell';

const FAJL = process.env.MOS_KEZI_GRAF;

it('a nézet csúcs- és élhalmaza pontosan a core gráfja', () => {
  expect(FAJL, 'MOS_KEZI_GRAF').toBeTruthy();
  const j = JSON.parse(readFileSync(FAJL!, 'utf8')) as {
    graf: { csucsok: string[]; elek: [string, string][] };
    fa: { fajlok: { ut: string; tipus: FajlTipus }[] };
    meta: { cimkek: Record<string, string[]>; tulajdonsagok: Record<string, Record<string, string[]>> };
    csoportok: { lekerdezes: string; szin: string }[];
  };
  const tipus = new Map(j.fa.fajlok.map((f) => [f.ut, f.tipus]));
  const g = new GrafAdat(j.graf, (u) => tipus.get(u), j.meta);

  // csúcsok: ugyanaz a halmaz és ugyanaz a sorrend
  expect(g.n).toBe(j.graf.csucsok.length);
  expect(g.ut).toEqual(j.graf.csucsok);
  // élek: egyetlen irányított él sem vész el, és nem kerül hozzá semmi
  expect(g.hianyzoElek).toBe(0);
  const mienk = new Set(g.iranyitottElek().map(([a, b]) => `${a}\u0000${b}`));
  const core = new Set(j.graf.elek.map(([a, b]) => `${a}\u0000${b}`));
  expect(mienk.size).toBe(core.size);
  expect([...core].filter((e) => !mienk.has(e))).toEqual([]);
  expect([...mienk].filter((e) => !core.has(e))).toEqual([]);
  // az irányítatlan élek (a rajz és a fizika élei) pontosan a core élpárjai, irány nélkül
  const par = new Set<string>();
  let onhurok = 0;
  for (const [a, b] of j.graf.elek) {
    if (a === b) onhurok++;
    else par.add(a < b ? `${a}\u0000${b}` : `${b}\u0000${a}`);
  }
  expect(g.elek.length / 2).toBe(par.size);
  // az alap nézet (minden kapcsoló be, nincs szűrő) a teljes halmaz
  const r = lathatosag(g, { lekerdezes: '', mellekletek: true, arvak: true });
  expect(r.csucsDb).toBe(g.n);
  expect(lathatoElDb(g, r.lathato)).toBe(par.size);
  // a graph.json színcsoportjai: nincs nem támogatott lekérdezés a valódi vaulton
  const cs = szinCsoportok(g, j.csoportok);
  const szinezett = cs.csoport.reduce((n, v) => n + (v >= 0 ? 1 : 0), 0);
  const osszegzes =
    `csúcs ${g.n} · irányított él ${core.size} · irányítatlan él ${par.size} · önhurok ${onhurok} · ` +
    `színezett csúcs ${szinezett} · nem támogatott csoport ${cs.tamogatott.filter((t) => !t).length}/${j.csoportok.length}`;
  // a Python szkript a riport-fájlból olvassa vissza és kiírja
  if (process.env.MOS_KEZI_RIPORT) writeFileSync(process.env.MOS_KEZI_RIPORT, osszegzes);
  expect(cs.tamogatott.every(Boolean)).toBe(true);
});
