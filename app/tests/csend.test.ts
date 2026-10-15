// Csend és elérés (C38): a láthatósági szabályok, a tartós kapcsoló és az első indulás, a gépeléskor halványuló króm,
// a bemutató értesítés, az F6 a rejtett régión, a ⌥⌘1 / ⌥⌘2 a teljes regiszterben, és az őr: a hiba, a megszakadt
// kapcsolat és a mentetlen állapot jele soha nem rejtett és nem halványul.

import { flushSync } from 'svelte';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { alapParancsok } from '../src/alapParancsok';
import { bazisTelepit } from '../src/bazis';
import { canvasTelepit } from '../src/canvas';
import { dolgozatTelepit } from '../src/dolgozat';
import { grafTelepit } from '../src/graf';
import { kodTelepit } from '../src/kod';
import { kvizTelepit } from '../src/kviz';
import { CoreKapcsolat } from '../src/lib/core/ws.svelte';
import {
  ALLAPOTSOR_TELJES,
  BEMUTATO,
  SZEL_ZONA,
  allapotsorLathato,
  csend,
  csendTelepit,
  egerAlul,
  egerBal,
  gepelesBillentyu,
  regioMegjelenitKezel,
  type AllapotsorJelek,
} from '../src/lib/elrendezes/csend.svelte';
import { Felulet } from '../src/lib/elrendezes/felulet.svelte';
import { ertesitesek } from '../src/lib/ertesites/ertesites.svelte';
import { regioLep } from '../src/lib/fokusz/fokusz';
import { Regiszter } from '../src/lib/parancsok/regiszter';
import { VaultFajlok } from '../src/lib/vault/fajlok.svelte';
import { maTelepit } from '../src/ma';
import { mediaTelepit } from '../src/media';
import { naptarTelepit } from '../src/naptar';
import { szerkesztoTelepit } from '../src/szerkeszto';
import { trackerTelepit } from '../src/tracker';
import { vezerloTelepit } from '../src/vezerlo';

const NYUGALOM: AllapotsorJelek = {
  csend: true,
  kapcsolatMegszakadt: false,
  olvasatlanFontos: 0,
  indexEpul: false,
  indexHiba: false,
  elozmenyNyitva: false,
  feladatFut: false,
  oldalsavRejtett: false,
  egerAlul: false,
  fokuszBenne: false,
};

describe('az állapotsor láthatósága', () => {
  it('csend nélkül mindig; csendben nyugalomban rejtett', () => {
    expect(allapotsorLathato({ ...NYUGALOM, csend: false })).toBe(true);
    expect(allapotsorLathato(NYUGALOM)).toBe(false);
  });

  it('csendben előjön, ha mondanivalója van, az egér az alsó szélen áll, vagy a fókusz benne van', () => {
    const jelek: Partial<AllapotsorJelek>[] = [
      { kapcsolatMegszakadt: true },
      { indexHiba: true },
      { indexEpul: true },
      { olvasatlanFontos: 1 },
      { elozmenyNyitva: true },
      { feladatFut: true, oldalsavRejtett: true },
      { egerAlul: true },
      { fokuszBenne: true },
    ];
    for (const j of jelek) expect(allapotsorLathato({ ...NYUGALOM, ...j }), JSON.stringify(j)).toBe(true);
    // a futó feladat pontja a nyitott oldalsávon a MANIFOLD jel mellett áll: az állapotsor nem kell hozzá
    expect(allapotsorLathato({ ...NYUGALOM, feladatFut: true })).toBe(false);
  });

  it('a szélek: a rejtett sávot a zóna hozza elő, a megjelentet a saját mérete tartja', () => {
    expect(egerAlul(800 - SZEL_ZONA, 800, false)).toBe(true);
    expect(egerAlul(800 - SZEL_ZONA - 1, 800, false)).toBe(false);
    expect(egerAlul(800 - ALLAPOTSOR_TELJES, 800, true)).toBe(true);
    expect(egerAlul(800 - ALLAPOTSOR_TELJES - 1, 800, true)).toBe(false);
    expect(egerBal(SZEL_ZONA, false, 264)).toBe(true);
    expect(egerBal(SZEL_ZONA + 1, false, 264)).toBe(false);
    expect(egerBal(264 + SZEL_ZONA, true, 264)).toBe(true);
    expect(egerBal(264 + SZEL_ZONA + 1, true, 264)).toBe(false);
  });

  it('a gépelés: a szerkesztőben a nyomtatható billentyű, Backspace, Delete, Enter; ⌘ és F6 ébreszt', () => {
    expect(gepelesBillentyu({ key: 'a' }, true)).toBe('gepeles');
    expect(gepelesBillentyu({ key: 'ő' }, true)).toBe('gepeles');
    expect(gepelesBillentyu({ key: ' ' }, true)).toBe('gepeles');
    for (const key of ['Backspace', 'Delete', 'Enter']) expect(gepelesBillentyu({ key }, true)).toBe('gepeles');
    expect(gepelesBillentyu({ key: 'a' }, false)).toBeNull();
    expect(gepelesBillentyu({ key: 'b', metaKey: true }, true)).toBeNull();
    expect(gepelesBillentyu({ key: 'b', ctrlKey: true }, true)).toBeNull();
    expect(gepelesBillentyu({ key: 'ArrowDown' }, true)).toBeNull();
    expect(gepelesBillentyu({ key: 'Meta' }, true)).toBe('ebreszt');
    expect(gepelesBillentyu({ key: 'F6' }, false)).toBe('ebreszt');
  });
});

describe('a tartós kapcsoló', () => {
  it('az első C38-as indulás: csend be, a jobb panel zárva, a tulajdonságok összecsukva — egyszer', () => {
    const f = new Felulet({ jobbPanel: { nyitva: true }, tulajdonsagok: { nyitva: true } });
    expect(f.csend).toEqual({ be: true, bemutatva: false });
    expect(f.jobbPanel.nyitva).toBe(false);
    expect(f.tulajdonsagok.nyitva).toBe(false);
    // a felhasználó kinyitja: a következő indulás megtartja
    f.jobbPanel.nyitva = true;
    const ujra = new Felulet(JSON.parse(JSON.stringify(f.sorosit())));
    expect(ujra.csend.be).toBe(true);
    expect(ujra.jobbPanel.nyitva).toBe(true);
    expect(ujra.tulajdonsagok.nyitva).toBe(false);
  });

  it('a kapcsoló: ki → mindent mutat; be → a csend alapállapota; az oldalsáv a felhasználóé', () => {
    const f = new Felulet({});
    f.oldalsav.nyitva = false;
    f.csendKapcsol();
    expect(f.csend.be).toBe(false);
    expect(f.jobbPanel.nyitva).toBe(true);
    expect(f.tulajdonsagok.nyitva).toBe(true);
    expect(f.oldalsav.nyitva).toBe(false);
    f.csendKapcsol();
    expect(f.csend.be).toBe(true);
    expect(f.jobbPanel.nyitva).toBe(false);
    expect(f.tulajdonsagok.nyitva).toBe(false);
    expect(new Felulet({ csend: { be: false, bemutatva: true } }).csend).toEqual({ be: false, bemutatva: true });
  });
});

describe('a csend bekötése', () => {
  let le: (() => void) | null = null;
  beforeEach(() => vi.useFakeTimers());
  afterEach(() => {
    le?.();
    le = null;
    vi.useRealTimers();
    document.body.innerHTML = '';
    for (const e of [...ertesitesek.lista]) ertesitesek.elvet(e.id);
    ertesitesek.elozmenyTorles();
  });

  const gepel = (cel: Element, key: string, o: KeyboardEventInit = {}) =>
    cel.dispatchEvent(new KeyboardEvent('keydown', { key, bubbles: true, ...o }));
  const gepelesben = () => document.documentElement.hasAttribute('data-csend-gepeles');

  it('a <html data-csend> a módot követi; gépelés a szerkesztőben halványít, egér, ⌘ és F6 visszahoz', () => {
    document.body.innerHTML = '<div class="cm-content" contenteditable="true"></div><input id="mezo">';
    const cm = document.querySelector('.cm-content')!;
    const f = new Felulet({ csend: { be: true, bemutatva: true } });
    le = csendTelepit(f);
    flushSync();
    expect(document.documentElement.hasAttribute('data-csend')).toBe(true);
    gepel(document.getElementById('mezo')!, 'a');
    expect(gepelesben()).toBe(false); // más mezőben nem
    gepel(cm, 'a');
    expect(gepelesben()).toBe(true);
    // valódi mozdulat (a görgetés utáni, elmozdulás nélküli mousemove nem ébreszt)
    window.dispatchEvent(new MouseEvent('mousemove', { clientX: 300, clientY: 300 }));
    expect(gepelesben()).toBe(true);
    window.dispatchEvent(new MouseEvent('mousemove', { clientX: 300, clientY: 300, movementX: 4 }));
    expect(gepelesben()).toBe(false);
    gepel(cm, 'b');
    gepel(cm, 'Meta', { metaKey: true });
    expect(gepelesben()).toBe(false);
    gepel(cm, 'c');
    gepel(cm, 'F6');
    expect(gepelesben()).toBe(false);
    // kikapcsolva nincs csend és nincs halványulás
    f.csendKapcsol(false);
    flushSync();
    expect(document.documentElement.hasAttribute('data-csend')).toBe(false);
    gepel(cm, 'd');
    expect(gepelesben()).toBe(false);
  });

  it('a szélek: alul az állapotsor, balra a rejtett oldalsáv átfedése jön elő', () => {
    const f = new Felulet({ csend: { be: true, bemutatva: true } });
    f.oldalsav.nyitva = false;
    le = csendTelepit(f);
    flushSync();
    window.dispatchEvent(new MouseEvent('mousemove', { clientX: 400, clientY: window.innerHeight - 2 }));
    expect(csend.egerAlul).toBe(true);
    window.dispatchEvent(new MouseEvent('mousemove', { clientX: 400, clientY: 100 }));
    expect(csend.egerAlul).toBe(false);
    window.dispatchEvent(new MouseEvent('mousemove', { clientX: 2, clientY: 100 }));
    expect(csend.oldalsavAtfedes).toBe(true);
    window.dispatchEvent(new MouseEvent('mousemove', { clientX: 200, clientY: 100 }));
    expect(csend.oldalsavAtfedes).toBe(true); // az átfedés fölött marad
    window.dispatchEvent(new MouseEvent('mousemove', { clientX: 600, clientY: 100 }));
    expect(csend.oldalsavAtfedes).toBe(false);
  });

  it('a bemutató értesítés az első C38-as indulás után egyszer jelenik meg, és tartósan megjegyződik', () => {
    const f = new Felulet({});
    le = csendTelepit(f, 10);
    vi.advanceTimersByTime(20);
    expect(ertesitesek.lista.map((e) => e.cim)).toContain(BEMUTATO.cim);
    expect(f.sorosit().csend).toEqual({ be: true, bemutatva: true });
    le();
    for (const e of [...ertesitesek.lista]) ertesitesek.elvet(e.id);
    le = csendTelepit(new Felulet(JSON.parse(JSON.stringify(f.sorosit()))), 10);
    vi.advanceTimersByTime(20);
    expect(ertesitesek.lista.map((e) => e.cim)).not.toContain(BEMUTATO.cim);
    // az info-értesítés nem tartja nyitva az állapotsort; a figyelmeztetés és a hiba igen
    expect(ertesitesek.olvasatlanFontos).toBe(0);
    ertesitesek.ertesit({ szint: 'hiba', cim: 'Hiba' });
    expect(ertesitesek.olvasatlanFontos).toBe(1);
    ertesitesek.olvasva();
    expect(ertesitesek.olvasatlanFontos).toBe(0);
  });
});

describe('F6 a rejtett régión', () => {
  afterEach(() => {
    document.body.innerHTML = '';
  });

  it('a rejtett (inert) régió is sorra kerül: belépéskor megjelenik, és a fókusz benne áll', () => {
    document.body.innerHTML = `
      <nav data-regio="oldalsav" data-regio-rejtett inert><button id="o">o</button></nav>
      <main data-regio="munkaterulet"><button id="x">x</button></main>
      <aside data-regio="jobb" data-regio-rejtett inert><button id="j">j</button></aside>`;
    const megjelent: string[] = [];
    for (const el of document.querySelectorAll<HTMLElement>('[data-regio-rejtett]')) {
      regioMegjelenitKezel(el, () => {
        el.removeAttribute('inert');
        el.removeAttribute('data-regio-rejtett');
        megjelent.push(el.dataset.regio!);
      });
    }
    document.getElementById('x')!.focus();
    regioLep(1);
    expect(megjelent).toEqual(['jobb']);
    expect(document.activeElement?.id).toBe('j');
    regioLep(1);
    expect(megjelent).toEqual(['jobb', 'oldalsav']);
    expect(document.activeElement?.id).toBe('o');
  });
});

describe('a parancsok a teljes regiszterben', () => {
  it('a ⌥⌘1 és a ⌥⌘2 nem ütközik egyetlen modul billentyűjével sem; minden rejtett elem parancs a ⌘P-ben', () => {
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
      kodTelepit(reg, felulet, kapcsolat),
    ];
    expect(reg.akkordhoz('Mod+Alt+1')?.id).toBe('hej.oldalsav');
    expect(reg.akkordhoz('Mod+Alt+2')?.id).toBe('hej.jobb-panel');
    const paletta = new Set(reg.lista().map((p) => p.id));
    for (const id of [
      'hej.csend', 'hej.allapotsor', 'hej.oldalsav', 'hej.jobb-panel', 'tulajdonsagok.kapcsol', 'fa.uj-jegyzet',
      'fa.osszecsuk', 'ful.uj', 'ful.bezar', 'ertesites.elozmeny', 'fa.megmutat', 'manifold.vezerlo',
    ]) {
      expect(reg.kap(id), id).toBeTruthy();
    }
    expect(paletta.has('hej.csend')).toBe(true);
    // a kapcsoló a ⌘P-ből: ki, majd be
    reg.futtat('hej.csend');
    expect(felulet.csend.be).toBe(false);
    reg.futtat('hej.csend');
    expect(felulet.csend.be).toBe(true);
    // a vezérlő rejtett oldalsávnál is nyílik (⇧⌘M)
    felulet.oldalsav.nyitva = false;
    expect(reg.futtat(reg.akkordhoz('Mod+Shift+m')!.id)).toBe(true);
    expect(felulet.manifoldLap).toBe(true);
    le.forEach((f) => f());
  });
});

describe('az őr: a hiba, a megszakadt kapcsolat és a mentetlen állapot soha nem rejtett', () => {
  // a felület összes komponense szövegként (a Vite globja; a projektben nincs @types/node)
  const FORRASOK = import.meta.glob('../src/**/*.svelte', { query: '?raw', import: 'default', eager: true }) as Record<string, string>;
  const forras = (ut: string) => FORRASOK[`../src/${ut}`];
  /** Az elemek nyitó tagjei (a `<` és a hozzá tartozó `>` között; a `{…}` kifejezések átugorva). */
  const tagek = (forras: string): string[] => {
    const s = forras.replace(/<script[\s\S]*?<\/script>|<style[\s\S]*?<\/style>|<!--[\s\S]*?-->/g, '');
    const ki: string[] = [];
    for (let i = s.search(/<[a-zA-Z]/); i >= 0; i = s.indexOf('<', i + 1)) {
      if (!/[a-zA-Z]/.test(s[i + 1] ?? '')) continue;
      let m = 0;
      let j = i;
      for (; j < s.length; j++) {
        if (s[j] === '{') m++;
        else if (s[j] === '}') m--;
        else if (s[j] === '>' && m === 0) break;
      }
      ki.push(s.slice(i, j + 1));
    }
    return ki;
  };

  it('a `data-csend-rejt` elem nem hiba-, figyelmeztetés- vagy riasztás-jel', () => {
    let db = 0;
    for (const [f, szoveg] of Object.entries(FORRASOK)) {
      for (const t of tagek(szoveg).filter((t) => t.includes('data-csend-rejt'))) {
        db++;
        expect(t, f).not.toMatch(/role="alert"|class="[^"]*\b(hiba|figyelmeztetes)\b|megszakadt|ütközés/i);
      }
    }
    expect(db).toBeGreaterThan(5);
  });

  it('a szerkesztő fejlécében a hibás és az ütköző állapot jele nem rejthető; a halk „Mentve” jelzés (E12) külön komponens', () => {
    const s = forras('szerkeszto/Szerkeszto.svelte');
    expect(s).not.toMatch(/data-csend-rejt=\{dok\?\.allapot/);
    // a „Nincs mentve” jel: piros, a foglalt zárra váró állapotban figyelmeztetés-színű — rejteni egyiket sem lehet
    const hiba = tagek(s).find((t) => t.includes('class="jel"') && t.includes('class:hiba='))!;
    expect(hiba).not.toContain('data-csend');
    const jel = tagek(s).find((t) => t.includes('class="jel figyelmeztetes"'))!;
    expect(jel).not.toContain('data-csend');
    expect(tagek(s).find((t) => t.includes('class="jel hiba gomb"'))).not.toContain('data-csend');
    // a mentés-jelzés (Mentve / Mentés… / pont) nem hiba-jel és nem rejtett: a hiba állapotában semmit nem mutat, a fejléc jele áll
    expect(forras('szerkeszto/MentesJelzes.svelte')).not.toContain('data-csend');
  });

  it('halványulni csak az oldalsáv és a fülsor halványul; az állapotsor nem', () => {
    const hol = Object.entries(FORRASOK)
      .filter(([, sz]) => sz.includes('data-csend-halvanyul'))
      .map(([f]) => f.slice('../src/'.length))
      .sort();
    expect(hol).toEqual(['hej/Fulsor.svelte', 'hej/Oldalsav.svelte']);
  });
});
