// A C++ parancsai (C36a-UI): a billentyűk nem ütköznek a teljes regiszterrel (minden modul telepítve), az `elerheto`
// csak `.cpp` fülön vagy `.cpp`-t beágyazó jegyzeten igaz, a Markdown-formázás (⌘B) a `.cpp` fülön nem él, a jegyzetből
// indított ⌘R a `.cpp` fület osztásban hozza elő, a hibaágak értesítést adnak, a formázás egy szerkesztő-tranzakció.

import { history, undo } from '@codemirror/commands';
import { EditorState } from '@codemirror/state';
import { EditorView } from '@codemirror/view';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { alapParancsok } from '../src/alapParancsok';
import { bazisTelepit } from '../src/bazis';
import { canvasTelepit } from '../src/canvas';
import { dolgozatTelepit } from '../src/dolgozat';
import { grafTelepit } from '../src/graf';
import { kodTelepit } from '../src/kod';
import { kodFulok, type KodPeldany } from '../src/kod/aktiv.svelte';
import { kodFutasok } from '../src/kod/futas.svelte';
import { ellenoriz, formaz, kodCel } from '../src/kod/muveletek';
import { kvizTelepit } from '../src/kviz';
import { CoreKapcsolat } from '../src/lib/core/ws.svelte';
import { Felulet } from '../src/lib/elrendezes/felulet.svelte';
import { ertesitesek } from '../src/lib/ertesites/ertesites.svelte';
import { Regiszter } from '../src/lib/parancsok/regiszter';
import { VaultFajlok } from '../src/lib/vault/fajlok.svelte';
import { maTelepit } from '../src/ma';
import { mediaTelepit } from '../src/media';
import { naptarTelepit } from '../src/naptar';
import { szerkesztoTelepit } from '../src/szerkeszto';
import { szerkesztok, type SzerkesztoPeldany } from '../src/szerkeszto/szerkesztok.svelte';
import { trackerTelepit } from '../src/tracker';
import { vezerloTelepit } from '../src/vezerlo';

const valasz = (kod: number, adat: unknown) => new Response(JSON.stringify(adat), { status: kod, headers: { 'Content-Type': 'application/json' } });
let keresek: { ut: string; torzs: Record<string, unknown> | undefined }[];
let ellenorizValasz: () => Response;
let formazValasz: () => Response;

beforeEach(() => {
  keresek = [];
  kodFutasok.aktiv = null;
  ellenorizValasz = () => valasz(202, { futas: 'futas-0123456789ab', cpp: 'Info/Összeg.cpp', jegyzet: 'Info/Összeg.md', mod: 'gyors', tesztek_db: 1 });
  formazValasz = () => valasz(200, { szoveg: 'int main() {\n    return 0;\n}\n', valtozott: true });
  vi.stubGlobal('fetch', async (url: string, init?: RequestInit) => {
    const u = new URL(url, 'http://127.0.0.1/');
    keresek.push({ ut: u.pathname, torzs: init?.body ? JSON.parse(String(init.body)) : undefined });
    if (u.pathname === '/api/cpp/ellenoriz') return ellenorizValasz();
    if (u.pathname === '/api/cpp/formaz') return formazValasz();
    if (u.pathname === '/api/cpp/feladat') return valasz(200, { tesztek: [] });
    return valasz(404, { hiba: 'nincs' });
  });
});

afterEach(() => {
  vi.unstubAllGlobals();
  kodFulok.aktiv = null;
  szerkesztok.aktiv = null;
  for (const e of [...ertesitesek.lista]) ertesitesek.elvet(e.id);
});

function kodPeldany(ut: string, view: EditorView | null = null, irhato = true): KodPeldany {
  return { ut, nezet: () => view, mentes: async () => true, irhato: () => irhato, ugras: () => {} };
}

function mdPeldany(ut: string, szoveg: string): SzerkesztoPeldany {
  const v = new EditorView({ state: EditorState.create({ doc: szoveg }) });
  return {
    ut,
    nezet: () => v,
    mod: () => 'elo',
    olvasoValt: () => {},
    forrasValt: () => {},
    mentes: async () => {},
    pillanatkep: async () => {},
    fokuszban: () => true,
    ugras: () => {},
    vazlat: () => [],
    valtozat: () => 0,
  };
}

describe('a C++ parancsok a teljes regiszterben', () => {
  it('a ⌘R, ⇧⌘R és ⇧⌥F nem ütközik egyetlen modul billentyűjével sem; a palettában megvannak', () => {
    const reg = new Regiszter();
    const felulet = new Felulet({});
    const fajlok = new VaultFajlok();
    const kapcsolat = new CoreKapcsolat('ws://127.0.0.1:1/ws');
    const le = [
      alapParancsok(reg, felulet),
      szerkesztoTelepit(reg, kapcsolat, felulet, fajlok),
      bazisTelepit({ felulet, fajlok, kapcsolat }),
      kvizTelepit(),
      grafTelepit(reg, felulet),
      maTelepit(reg, felulet, kapcsolat),
      dolgozatTelepit(reg, felulet, kapcsolat),
      canvasTelepit(reg, felulet, fajlok),
      mediaTelepit(reg, kapcsolat),
      trackerTelepit(reg, felulet),
      vezerloTelepit(reg, felulet, kapcsolat),
      naptarTelepit(reg, felulet, kapcsolat),
      kodTelepit(reg, felulet, kapcsolat), // ütközésnél itt dobna
    ];
    expect(reg.akkordhoz('Mod+r')?.id).toBe('kod.ellenorzes');
    expect(reg.akkordhoz('Mod+Shift+r')?.id).toBe('kod.ellenorzes-hibakereso');
    expect(reg.akkordhoz('Alt+Shift+f')?.id).toBe('kod.formaz');
    expect(reg.kap('kod.uj-feladat')).toBeTruthy();
    // semmi nem aktív: a C++ parancsok nem érhetők el (a ⌘R nem nyel el billentyűt máshol)
    expect(reg.elerheto(reg.kap('kod.ellenorzes')!)).toBe(false);
    expect(reg.elerheto(reg.kap('kod.formaz')!)).toBe(false);
    expect(reg.elerheto(reg.kap('kod.megszakit')!)).toBe(false);
    // .cpp fül aktív: a C++ parancs él, a Markdown-formázás (⌘B) nem
    kodFulok.aktiv = kodPeldany('Info/Összeg.cpp');
    expect(reg.elerheto(reg.kap('kod.ellenorzes')!)).toBe(true);
    expect(reg.elerheto(reg.kap('kod.formaz')!)).toBe(true);
    expect(reg.elerheto(reg.akkordhoz('Mod+b')!)).toBe(false);
    le.forEach((f) => f());
  });
});

describe('kodCel', () => {
  it('.cpp fül → a .cpp; .cpp-t beágyazó jegyzet → a jegyzet; más jegyzet → nincs', () => {
    expect(kodCel()).toBeNull();
    szerkesztok.aktiv = mdPeldany('Info/Összeg.md', '# Összeg\n\n## Megoldás\n\n![[Összeg.cpp]]\n');
    expect(kodCel()).toEqual({ ut: 'Info/Összeg.md', jegyzet: 'Info/Összeg.md' });
    szerkesztok.aktiv = mdPeldany('Info/Más.md', '# Más\n\n[[Összeg.cpp]] csak link, nem beágyazás\n');
    expect(kodCel()).toBeNull();
    kodFulok.aktiv = kodPeldany('Info/Összeg.cpp');
    expect(kodCel()).toEqual({ ut: 'Info/Összeg.cpp', jegyzet: null });
  });
});

describe('ellenoriz', () => {
  it('jegyzetből: a jegyzet a kérésben, a .cpp fül osztásban nyílik, a fókusz a jegyzet paneljén marad', async () => {
    const felulet = new Felulet({});
    const mt = felulet.munkaterulet;
    mt.megnyit('Info/Összeg.md');
    const eredeti = mt.aktivPanelId;
    szerkesztok.aktiv = mdPeldany('Info/Összeg.md', '![[Összeg.cpp]]');
    expect(await ellenoriz(felulet, 'gyors')).toBe(true);
    expect(keresek.find((k) => k.ut === '/api/cpp/ellenoriz')!.torzs).toEqual({ ut: 'Info/Összeg.md', mod: 'gyors', jegyzet: 'Info/Összeg.md' });
    expect(mt.panelek()).toHaveLength(2);
    expect(mt.panelek().some((p) => p.fulek.some((f) => f.ut === 'Info/Összeg.cpp'))).toBe(true);
    expect(mt.aktivPanelId).toBe(eredeti);
    // a második ⌘R már nem nyit újabb osztást
    kodFutasok.aktiv = null;
    await ellenoriz(felulet, 'gyors');
    expect(mt.panelek()).toHaveLength(2);
  });

  it('nincs eszköztár: tartós hibaértesítés a telepítő paranccsal; futás közben a második ⌘R nem indul', async () => {
    const felulet = new Felulet({});
    kodFulok.aktiv = kodPeldany('Info/Összeg.cpp');
    ellenorizValasz = () => valasz(503, { hiba: 'nincs C++ eszköztár (hiányzik: clang++): bin/mos cpp telepit --igen', kod: 'nincs_eszkoztar' });
    expect(await ellenoriz(felulet, 'gyors')).toBe(false);
    expect(ertesitesek.lista.some((e) => e.cim === 'Nincs C++ eszköztár' && e.szoveg.includes('telepit'))).toBe(true);
    ellenorizValasz = () => valasz(202, { futas: 'futas-0123456789ab', cpp: 'Info/Összeg.cpp', jegyzet: null, mod: 'gyors', tesztek_db: 0 });
    expect(await ellenoriz(felulet, 'gyors')).toBe(true);
    const db = keresek.filter((k) => k.ut === '/api/cpp/ellenoriz').length;
    expect(await ellenoriz(felulet, 'gyors')).toBe(false);
    expect(keresek.filter((k) => k.ut === '/api/cpp/ellenoriz').length).toBe(db);
  });

  it('a mentetlen-jelzés késése (409 mentetlen) után újrapróbál', async () => {
    const felulet = new Felulet({});
    kodFulok.aktiv = kodPeldany('Info/Összeg.cpp');
    let n = 0;
    ellenorizValasz = () =>
      ++n === 1
        ? valasz(409, { hiba: 'mentetlen változás van a fájlban: mentsd előbb', kod: 'mentetlen', utak: ['Info/Összeg.cpp'] })
        : valasz(202, { futas: 'futas-0123456789ab', cpp: 'Info/Összeg.cpp', jegyzet: null, mod: 'gyors', tesztek_db: 0 });
    expect(await ellenoriz(felulet, 'gyors')).toBe(true);
    expect(n).toBe(2);
  });
});

describe('formaz', () => {
  it('a clang-format eredménye egy tranzakció: egy ⌘Z visszahozza az eredetit', async () => {
    const eredeti = 'int main(){return 0;}\n';
    const v = new EditorView({ state: EditorState.create({ doc: eredeti, extensions: [history()] }) });
    kodFulok.aktiv = kodPeldany('x.cpp', v);
    expect(await formaz()).toBe(true);
    expect(keresek.find((k) => k.ut === '/api/cpp/formaz')!.torzs).toEqual({ szoveg: eredeti });
    expect(v.state.doc.toString()).toBe('int main() {\n    return 0;\n}\n');
    undo(v);
    expect(v.state.doc.toString()).toBe(eredeti);
  });

  it('csak olvasható fájlon nem kér formázást', async () => {
    const v = new EditorView({ state: EditorState.create({ doc: 'x' }) });
    kodFulok.aktiv = kodPeldany('x.cpp', v, false);
    expect(await formaz()).toBe(false);
    expect(keresek).toHaveLength(0);
  });
});
