// A canvas bájthűsége a vault klónján (C14 kész-feltétele). Futtatás: tests/kezi/canvas_proba.py (az indítja a
// core-t a klónra, és átadja a címét és a canvasok listáját).
//
// Canvasonként a nézet valódi útja, DOM nélkül: a core fájl-API-ja → Dokumentum → CanvasForras (beolvasás) →
//   (a) a változatlan modell visszaírása + kényszerített mentés `elso` + `pillanat` jelzővel (a lemezre megy;
//       a szkript utána a manifeszttel veti össze);
//   (b) minden node x-e +20, majd −20 a foltozón át → bájtra az eredeti;
//   (c) az első node elmozdítva → a különbség csak annak a node-nak a szövegén belül áll;
//   (d) új szövegkártya + él + az utolsó node törlése → minden érintetlen elem szövege bájtra benne van;
// a (c) és (d) szövege a mintákba kerül: a szkript a Python `json.loads`-szal és a core `canvas_bajtbol`-jával
// ellenőrzi (ezek nem kerülnek a lemezre).

import { writeFileSync } from 'node:fs';
import { expect, it } from 'vitest';
import { CanvasForras } from '../../src/canvas/forras';
import { foltoz } from '../../src/canvas/iro';
import { elemez } from '../../src/canvas/json';
import { csomopontok, type Vaszon } from '../../src/canvas/modell';
import { vaultApi } from '../../src/szerkeszto/dokumentum/api';
import { Dokumentumok } from '../../src/szerkeszto/dokumentum/dokumentum.svelte';

const CORE = process.env.MOS_KEZI_CORE;
const UTAK = process.env.MOS_KEZI_UTAK;
const RIPORT = process.env.MOS_KEZI_RIPORT;
const MINTAK = process.env.MOS_KEZI_MINTAK;

const klon = <T>(x: T): T => JSON.parse(JSON.stringify(x)) as T;

/** A két szöveg közti eltérő szakasz helye a régiben. */
function kulonbseg(a: string, b: string): [number, number] {
  let k = 0;
  while (k < a.length && k < b.length && a[k] === b[k]) k++;
  let v = 0;
  while (v < a.length - k && v < b.length - k && a[a.length - 1 - v] === b[b.length - 1 - v]) v++;
  return [k, a.length - v];
}

/** A tömbelemek szövegei (a változatlannak maradó elemek bájtjainak ellenőrzéséhez). */
function elemSzovegek(s: string): Map<string, string> {
  const ki = new Map<string, string>();
  const gy = elemez(s);
  if (gy.t !== 'obj') return ki;
  for (const t of gy.tagok)
    if ((t.kulcs === 'nodes' || t.kulcs === 'edges') && t.ertek.t === 'tomb')
      for (const e of t.ertek.elemek) {
        const id = e.t === 'obj' ? e.tagok.find((x) => x.kulcs === 'id') : undefined;
        if (id && id.ertek.t === 'prim') ki.set(String(id.ertek.ertek), s.slice(e.kezd, e.veg));
      }
  return ki;
}

it.skipIf(!CORE || !UTAK || !RIPORT || !MINTAK)('a canvasok megnyitás + mentés után bájtra változatlanok', async () => {
  const api = vaultApi(CORE);
  const dk = new Dokumentumok(api);
  const utak = JSON.parse(UTAK!) as string[];
  const eredmeny: Record<string, unknown>[] = [];
  const mintak: Record<string, unknown>[] = [];
  for (const ut of utak) {
    const kezd = performance.now();
    const f = await api.olvas(ut);
    const forras = await CanvasForras.nyit(ut, dk);
    const s = forras.szoveg();
    expect(forras.dok.fajlSzoveg(), `${ut}: a dokumentum szövege`).toBe(f.tartalom);
    const { vaszon, hiba } = forras.allapot;
    expect(hiba, `${ut}: beolvasás`).toBeNull();
    const v = vaszon as Vaszon;
    const olvasMs = performance.now() - kezd;

    // (a) változatlan modell → a szöveg ugyanaz; kényszerített mentés
    expect(forras.ir(klon(v)), `${ut}: a változatlan modell`).toEqual({ ok: true, valtozott: false });
    expect(forras.dok.fajlSzoveg(), `${ut}: a mentendő szöveg`).toBe(f.tartalom);
    const m = await forras.dok.ment({ kenyszer: true, pillanat: true });
    expect(m.ok, `${ut}: a mentés`).toBe(true);

    const n = csomopontok(v).length;
    let c: string | null = null;
    let d: string | null = null;
    let cElvart: Vaszon | null = null;
    let dElvart: Vaszon | null = null;
    if (n) {
      // (b) minden node +20, majd −20
      const tol = klon(v);
      for (const x of csomopontok(tol)) x.x += 20;
      const s1 = foltoz(s, tol);
      expect(foltoz(s1, v), `${ut}: oda-vissza`).toBe(s);

      // (c) egy node elmozdítva: a különbség a node szövegén belül
      cElvart = klon(v);
      const elso = csomopontok(cElvart)[0];
      elso.x += 40;
      elso.y -= 20;
      c = foltoz(s, cElvart);
      const regiElem = elemSzovegek(s).get(elso.id) as string;
      const elemKezd = s.indexOf(regiElem);
      const [a, b] = kulonbseg(s, c);
      expect(a >= elemKezd && b <= elemKezd + regiElem.length, `${ut}: a különbség a node-on belül`).toBe(true);

      // (d) új szövegkártya + él + az utolsó node törlése (a hozzá tartozó élekkel)
      dElvart = klon(v);
      const torolt = csomopontok(dElvart)[n - 1].id;
      dElvart.nodes = csomopontok(dElvart).filter((x) => x.id !== torolt);
      dElvart.nodes.push({ id: 'c14kezi000000001', type: 'text', text: 'Próba — „C14”', x: 0, y: 0, width: 250, height: 60 });
      dElvart.edges = (dElvart.edges ?? []).filter((e) => e.fromNode !== torolt && e.toNode !== torolt);
      if (dElvart.nodes.length > 1)
        dElvart.edges.push({ id: 'c14kezi000000002', fromNode: dElvart.nodes[0].id, fromSide: 'right', toNode: 'c14kezi000000001', toSide: 'left', label: 'próba' });
      d = foltoz(s, dElvart);
      const ujElemek = elemSzovegek(d);
      for (const [id, szoveg] of elemSzovegek(s)) {
        const marad = dElvart.nodes.some((x) => x.id === id) || dElvart.edges.some((e) => e.id === id);
        if (marad) expect(ujElemek.get(id), `${ut}: ${id} bájtra marad`).toBe(szoveg);
      }
    }
    mintak.push({ ut, c, c_elvart: cElvart, d, d_elvart: dElvart });
    eredmeny.push({
      ut,
      karakter: s.length,
      node: n,
      el: (v.edges ?? []).length,
      figyelmeztetesek: forras.allapot.figyelmeztetesek,
      pillanat: m.pillanat ?? null,
      olvas_ms: Math.round(olvasMs),
      ms: Math.round(performance.now() - kezd),
    });
    await forras.lezar();
  }
  writeFileSync(RIPORT!, JSON.stringify(eredmeny, null, 1));
  writeFileSync(MINTAK!, JSON.stringify(mintak));
});
