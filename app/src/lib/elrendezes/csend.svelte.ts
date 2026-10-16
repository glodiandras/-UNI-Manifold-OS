// Csend és elérés (C38, CLAUDE.md 25. döntés): a felület alapból a lehető legkevesebbet mutatja, de minden egy
// mozdulatnyira van. Itt él a csend mód futásidejű állapota és a láthatósági szabályok tiszta függvényei; a tartós
// kapcsoló a `Felulet.csend`-ben. A jelölés a `<html>` két attribútuma: `data-csend` (a mód be) és
// `data-csend-gepeles` (gépelés közben) — a hozzájuk tartozó szabályok egy helyen, az `alap.css` „Csend és elérés”
// blokkjában. A hiba, a megszakadt kapcsolat és a mentetlen állapot jelzése soha nem rejtett és nem halványul.

import { t, tk } from '../i18n';

import { flushSync } from 'svelte';
import { ertesitesek } from '../ertesites/ertesites.svelte';
import type { Felulet } from './felulet.svelte';

/** Az ablak széle (px), ahová vitt egér a rejtett sávot előhozza (a 4-es rácson; DESIGN.md „Csend és elérés”). */
export const SZEL_ZONA = 8;
/** Az állapotsor teljes magassága (24 + 1 px keret; a tokens.css `--allapotsor-teljes`). */
export const ALLAPOTSOR_TELJES = 25;

/** Az állapotsor jelei: amiből eldől, van-e mondanivalója. */
export interface AllapotsorJelek {
  csend: boolean;
  kapcsolatMegszakadt: boolean;
  /** olvasatlan figyelmeztetés vagy hiba (az info és a siker már látszott értesítésként) */
  olvasatlanFontos: number;
  indexEpul: boolean;
  indexHiba: boolean;
  elozmenyNyitva: boolean;
  feladatFut: boolean;
  oldalsavRejtett: boolean;
  egerAlul: boolean;
  fokuszBenne: boolean;
}

/** Van-e az állapotsornak mondanivalója (ekkor csendben is látszik). A hiba és a megszakadt kapcsolat mindig az. */
export function allapotsorMondanivalo(j: AllapotsorJelek): boolean {
  return (
    j.kapcsolatMegszakadt ||
    j.indexHiba ||
    j.indexEpul ||
    j.olvasatlanFontos > 0 ||
    j.elozmenyNyitva ||
    (j.feladatFut && j.oldalsavRejtett)
  );
}

/** Látszik-e az állapotsor: csend nélkül mindig; csendben, ha mondanivalója van, az egér az alsó szélen áll, vagy
 *  a fókusz benne van (F6, ⌘P „Állapotsor megjelenítése”). */
export function allapotsorLathato(j: AllapotsorJelek): boolean {
  return !j.csend || allapotsorMondanivalo(j) || j.egerAlul || j.fokuszBenne;
}

/** Az alsó szél: rejtett sávnál a `SZEL_ZONA`-n belül hozza elő, a megjelent sáv fölött az egér megtartja. */
export function egerAlul(y: number, ablakMagassag: number, most: boolean): boolean {
  return y >= ablakMagassag - (most ? ALLAPOTSOR_TELJES : SZEL_ZONA);
}

/** A bal szél: a rejtett oldalsávot a `SZEL_ZONA`-n belül hozza elő átfedésként; a megjelent átfedés a szélessége
 *  fölött (plusz a zóna) nyitva marad. */
export function egerBal(x: number, most: boolean, oldalsavSzelesseg: number): boolean {
  return x <= (most ? oldalsavSzelesseg + SZEL_ZONA : SZEL_ZONA);
}

export type GepelesJel = 'gepeles' | 'ebreszt' | null;

/** A billentyű a csend szemével: a szerkesztőben leütött nyomtatható billentyű, Backspace, Delete, Enter (⌘ és ⌃
 *  nélkül) gépelés; a ⌘ lenyomása és az F6 ébreszt; minden más közömbös. */
export function gepelesBillentyu(
  e: { key: string; metaKey?: boolean; ctrlKey?: boolean },
  szerkesztoben: boolean,
): GepelesJel {
  if (e.key === 'Meta' || e.key === 'F6') return 'ebreszt';
  if (e.metaKey || e.ctrlKey || !szerkesztoben) return null;
  if (e.key.length === 1 || e.key === 'Backspace' || e.key === 'Delete' || e.key === 'Enter') return 'gepeles';
  return null;
}

/** A csend mód futásidejű állapota (egy példány). */
export class Csend {
  /** A mód be (a `Felulet.csend.be` tükre; a `csendTelepit` köti). Alapból ki: a telepítetlen (teszt)felület a mai. */
  be = $state(false);
  /** A rejtett oldalsáv átfedésként látszik (bal szél vagy F6). */
  oldalsavAtfedes = $state(false);
  /** A rejtett jobb panel átfedésként látszik (F6). */
  jobbAtfedes = $state(false);
  /** Az egér az ablak alsó szélén (az állapotsor előjön). */
  egerAlul = $state(false);
  private gepelesErtek = false;

  get gepeles(): boolean {
    return this.gepelesErtek;
  }

  /** Gépelés közben: csak állapotváltáskor ír a DOM-ba (leütésenként egy logikai vizsgálat). */
  set gepeles(v: boolean) {
    if (v === this.gepelesErtek) return;
    this.gepelesErtek = v;
    if (typeof document !== 'undefined') document.documentElement.toggleAttribute('data-csend-gepeles', v);
  }
}

export const csend = new Csend();

/** A rejtett régió megjelenítése (F6, parancs): a régió `regio-megjelenit` eseményét a komponens szinkron kezeli. */
export function regioMegjelenitKezel(el: HTMLElement, megjelenit: () => void): () => void {
  const f = () => flushSync(megjelenit);
  el.addEventListener('regio-megjelenit', f);
  return () => el.removeEventListener('regio-megjelenit', f);
}

/** A fókusz és az egér a csomóponton kívül van-e (az átfedés ekkor visszabújhat). */
export function kivul(el: HTMLElement | undefined, kovetkezo: EventTarget | null = null): boolean {
  if (!el) return true;
  if (kovetkezo instanceof Node && el.contains(kovetkezo)) return false;
  if (el.contains(document.activeElement)) return false;
  return !el.matches(':hover');
}

/** A bemutató értesítés: az első C38-as indulás után egyszer (tartósan), hogy a rejtés ne legyen rejtély. */
export const BEMUTATO = { cim: tk('Csend mód'), szoveg: tk('A panelek ⌥⌘1/⌥⌘2-vel és a ⌘P-ből érhetők el.') } as const;

/** A csend bekötése (az App csatolásakor): a mód tükre és a `<html data-csend>`, a bemutató értesítés, a gépelés,
 *  az egér és a szélek figyelése. A leiratkozót adja vissza. */
export function csendTelepit(f: Felulet, bemutatoKesleltetes = 1500): () => void {
  const html = document.documentElement;
  const effektLe = $effect.root(() => {
    $effect(() => {
      const be = f.csend.be;
      csend.be = be;
      html.toggleAttribute('data-csend', be);
      if (!be) {
        csend.gepeles = false;
        csend.egerAlul = false;
        csend.oldalsavAtfedes = false;
      }
    });
    // a nyitott sávnak nincs átfedése
    $effect(() => {
      if (f.oldalsav.nyitva) csend.oldalsavAtfedes = false;
    });
    $effect(() => {
      if (f.jobbPanel.nyitva) csend.jobbAtfedes = false;
    });
  });

  let bemutatoIdozito: ReturnType<typeof setTimeout> | null = null;
  if (f.csend.be && !f.csend.bemutatva) {
    bemutatoIdozito = setTimeout(() => {
      bemutatoIdozito = null;
      ertesitesek.ertesit({ szint: 'info', cim: t(BEMUTATO.cim), szoveg: t(BEMUTATO.szoveg), idotartam: 8000 });
      f.csend.bemutatva = true;
    }, bemutatoKesleltetes);
  }

  const billentyu = (e: KeyboardEvent) => {
    const j = gepelesBillentyu(e, e.target instanceof Element && e.target.closest('.cm-content') !== null);
    if (j === 'gepeles') {
      if (csend.be) csend.gepeles = true;
    } else if (j === 'ebreszt') csend.gepeles = false;
  };
  const nav = () => document.querySelector<HTMLElement>('[data-regio="oldalsav"]') ?? undefined;
  const mozog = (e: MouseEvent) => {
    if (csend.gepeles && (e.movementX !== 0 || e.movementY !== 0)) csend.gepeles = false;
    if (!csend.be) return;
    const alul = egerAlul(e.clientY, window.innerHeight, csend.egerAlul);
    if (alul !== csend.egerAlul) csend.egerAlul = alul;
    if (f.oldalsav.nyitva) return;
    const bal = egerBal(e.clientX, csend.oldalsavAtfedes, f.oldalsav.szelesseg);
    if (bal && !csend.oldalsavAtfedes) csend.oldalsavAtfedes = true;
    else if (!bal && csend.oldalsavAtfedes && kivul(nav())) csend.oldalsavAtfedes = false;
  };
  const kilep = () => {
    csend.egerAlul = false;
    if (csend.oldalsavAtfedes && kivul(nav())) csend.oldalsavAtfedes = false;
  };
  window.addEventListener('keydown', billentyu, { capture: true, passive: true });
  window.addEventListener('mousemove', mozog, { passive: true });
  html.addEventListener('mouseleave', kilep);
  return () => {
    effektLe();
    if (bemutatoIdozito) clearTimeout(bemutatoIdozito);
    window.removeEventListener('keydown', billentyu, { capture: true });
    window.removeEventListener('mousemove', mozog);
    html.removeEventListener('mouseleave', kilep);
    html.removeAttribute('data-csend');
    csend.gepeles = false;
    csend.be = false;
  };
}
