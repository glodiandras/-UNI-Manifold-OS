// Az összefoglaló parancsai (C26b; docs/C26-TERV.md 7.): „Összefoglalás” (a C17 helyőrző helyett, ugyanazon az azonosítón),
// „Összefoglalás a mappából”, „Kontextus-csomag a vágólapra” és a külső AI válaszának beillesztése. A logika a core-é (kapuk,
// gépi írás); itt csak az indítás, a vágólap és a kurzorhoz illesztés van. A külső AI válaszát **a felhasználó illeszti be**
// a szerkesztő útján (49. döntés): az írás a meglévő egyetlen úton megy, a ⌘Z egy lépés.

import { ApiHiba } from '../lib/core/api';
import type { Felulet } from '../lib/elrendezes/felulet.svelte';
import { ertesitesek } from '../lib/ertesites/ertesites.svelte';
import { t, tp } from '../lib/i18n';
import { fajlNev } from '../lib/vault/fajlok.svelte';
import { irhato } from '../szerkeszto/beallitas';
import { szerkesztok } from '../szerkeszto/szerkesztok.svelte';
import { vagolapra } from '../szerkeszto/vagolap';
import { kiseroUt, mediaUt, osszefoglaloUt } from './allando';
import { osszefoglalasApi } from './api';
import { kulsoAi } from './kulsoAllapot.svelte';

const uzenet = (e: unknown) => (e instanceof ApiHiba ? e.message : e instanceof Error ? e.message : String(e));

/** Tartalmi jegyzet-e (a core `automatika.tartalmi_ut` tükre): nem gépi kísérőjegyzet, nem rejtett mappa. */
export function tartalmiJegyzet(ut: string | undefined | null): ut is string {
  if (!ut || !ut.toLowerCase().endsWith('.md')) return false;
  return !kiseroUt(ut) && !ut.normalize('NFC').split('/').some((r) => r.startsWith('.'));
}

function mentesElotte(ut: string): Promise<void> {
  const p = szerkesztok.aktiv;
  return p && p.ut === ut ? p.mentes() : Promise.resolve();      // a gépi írás mentetlen dokumentumba nem ír (28(c))
}

/** Összefoglalás egy jegyzetből (`jegyzet`) vagy egy videó/hang átiratából (`video`). */
export async function osszefoglalasFajlbol(ut: string): Promise<void> {
  const video = mediaUt(ut);
  if (!video && !tartalmiJegyzet(ut)) {
    ertesitesek.ertesit({
      szint: 'info',
      cim: t('Ebből nem készül összefoglaló'),
      szoveg: osszefoglaloUt(ut) ? t('Ez maga egy összefoglaló; a forrásjegyzetből készül.') : t('Tartalmi jegyzetet vagy videó/hang fájlt jelölj ki.'),
    });
    return;
  }
  try {
    if (!video) await mentesElotte(ut);
    await osszefoglalasApi.keszit({ szint: video ? 'video' : 'jegyzet', ut });
  } catch (e) {
    ertesitesek.ertesit({ szint: 'hiba', cim: t('Az összefoglaló nem indult el'), szoveg: uzenet(e) });
    return;
  }
  ertesitesek.ertesit({
    szint: 'info',
    cim: t('Összefoglaló készül'),
    szoveg: video
      ? t('A modell az átirat időablakaiból állításokat javasol időkód-linkekkel; ami átmegy a kapukon, a kísérőjegyzetbe kerül (visszavonható).')
      : t('A modell állításokat javasol a jegyzetből, mindegyik mellé a jegyzet mondatával; ami átmegy a kapukon, a kísérőjegyzetbe kerül, a jegyzetbe beágyazó sor (visszavonható).'),
  });
}

/** Mappa-szintű összefoglaló: előbb a terv (hány hiányzó jegyzet-összefoglaló készül), aztán az indítás. */
export async function osszefoglalasMappabol(mappa: string): Promise<void> {
  const m = mappa.replace(/^\/+|\/+$/g, '');
  try {
    const terv = await osszefoglalasApi.mappaTerv(m);
    if (terv.van.length + terv.keszul.length < 2) {
      ertesitesek.ertesit({
        szint: 'figyelmeztetes',
        cim: t('Kevés jegyzet a mappa-összefoglalóhoz'),
        szoveg: t('Legalább két jegyzet-összefoglaló kell; most {van} van, és {keszul} készülhetne el.', { van: terv.van.length, keszul: terv.keszul.length }),
      });
      return;
    }
    await osszefoglalasApi.keszit({ szint: 'mappa', ut: m });
    const marad = terv.hianyzik.length - terv.keszul.length;
    ertesitesek.ertesit({
      szint: 'info',
      cim: t('Mappa-összefoglaló készül'),
      szoveg:
        tp('{n} jegyzethez már van összefoglaló', terv.van.length) +
        (terv.keszul.length ? t(', {n} még előbb elkészül', { n: terv.keszul.length }) : '') +
        t('; összesen {n} gépi írás, egyenként visszavonható', { n: terv.tetelek }) +
        (marad > 0 ? t('. {marad} jegyzet kimarad (egy kérésben legfeljebb {max} új jegyzet-összefoglaló készül; futtasd újra).', { marad, max: terv.tetelek - 1 }) : '.'),
      idotartam: 12000,
    });
  } catch (e) {
    ertesitesek.ertesit({ szint: 'hiba', cim: t('A mappa-összefoglaló nem indult el'), szoveg: uzenet(e) });
  }
}

function aktivUt(felulet: Felulet): string | null {
  return felulet.munkaterulet.aktivFul?.ut ?? null;
}

export function osszefoglalas(felulet: Felulet): Promise<void> {
  const ut = aktivUt(felulet);
  if (!ut) {
    ertesitesek.ertesit({ szint: 'info', cim: t('Nyiss meg egy jegyzetet'), szoveg: t('Az összefoglaló a jegyzetből (vagy a videó/hang átiratából) készül.') });
    return Promise.resolve();
  }
  return osszefoglalasFajlbol(ut);
}

export function osszefoglalasAktivMappabol(felulet: Felulet): Promise<void> {
  const ut = aktivUt(felulet);
  if (!ut || !ut.includes('/')) {
    ertesitesek.ertesit({ szint: 'info', cim: t('Nyiss meg egy mappában álló jegyzetet'), szoveg: t('A mappa-összefoglaló az aktív jegyzet mappájából készül.') });
    return Promise.resolve();
  }
  return osszefoglalasMappabol(ut.slice(0, ut.lastIndexOf('/')));
}

/** A kontextus-csomag a vágólapra: az aktív jegyzetből (útvonal nélkül; a `J1` azonosító a felületen marad). */
export async function kontextusCsomag(felulet: Felulet): Promise<void> {
  const ut = aktivUt(felulet);
  if (!ut || !ut.toLowerCase().endsWith('.md')) {
    ertesitesek.ertesit({ szint: 'info', cim: t('Nyiss meg egy jegyzetet'), szoveg: t('A kontextus-csomag a megnyitott jegyzetből készül.') });
    return;
  }
  try {
    await mentesElotte(ut);
    const cs = await osszefoglalasApi.kontextus([ut]);
    const ok = await vagolapra(cs.szoveg);
    kulsoAi.beallit([ut], ok);
    ertesitesek.ertesit({
      szint: ok ? 'siker' : 'figyelmeztetes',
      cim: ok ? t('A kontextus-csomag a vágólapon van') : t('A vágólapra másolás nem sikerült'),
      szoveg:
        t('{n} jegyzet, {k} karakter', { n: cs.benne.length, k: cs.karakter }) +
        (cs.csonkolt.length ? ' ' + t('(a hosszú jegyzet további fejezetei kimaradtak)') : '') +
        t('; útvonal nincs benne. Add a külső AI-nak, majd illeszd vissza a válaszát.'),
      muvelet: { nev: t('Válasz beillesztése…'), futtat: () => kulsoAiMegnyit(felulet) },
      idotartam: 15000,
    });
  } catch (e) {
    ertesitesek.ertesit({ szint: 'hiba', cim: t('A kontextus-csomag nem készült el'), szoveg: uzenet(e) });
  }
}

/** A külső AI válaszának átvétele: az átfedés megnyitása (a csomag jegyzetei, különben az aktív jegyzet). */
export function kulsoAiMegnyit(felulet: Felulet): void {
  if (!kulsoAi.utak.length) {
    const ut = aktivUt(felulet);
    if (!ut || !ut.toLowerCase().endsWith('.md')) {
      ertesitesek.ertesit({ szint: 'info', cim: t('Előbb készíts kontextus-csomagot'), szoveg: t('A válasz azokon a jegyzeteken kapuzódik, amelyekből a csomag készült.') });
      return;
    }
    kulsoAi.beallit([ut], false);
  }
  felulet.atfedes = 'kulso-ai';
}

/** Az `## Állítások` blokk beillesztése az aktív szerkesztő kurzorához (egy tranzakció: a ⌘Z egy lépés). */
export function torzsBeszur(torzs: string): { ok: boolean; hiba?: string } {
  const p = szerkesztok.aktiv;
  const v = p?.nezet();
  if (!p || p.mod() === 'olvaso' || !v || !irhato(v)) {
    return { ok: false, hiba: v && !irhato(v) ? t('A jegyzet csak olvasható.') : t('Nyiss meg egy jegyzetet szerkesztésre.') };
  }
  const doc = v.state.doc.toString();
  const s = v.state.selection.main;
  const elotte = doc.slice(0, s.from);
  const utana = doc.slice(s.to);
  const szoveg = (elotte && !elotte.endsWith('\n\n') ? (elotte.endsWith('\n') ? '\n' : '\n\n') : '') + torzs.trimEnd() + (utana.startsWith('\n') ? '\n' : '\n\n');
  v.dispatch({
    changes: { from: s.from, to: s.to, insert: szoveg },
    selection: { anchor: s.from + szoveg.length },
    scrollIntoView: true,
    userEvent: 'input.paste',
  });
  v.focus();
  return { ok: true };
}

export const jegyzetNev = (ut: string) => fajlNev(ut).replace(/\.md$/i, '');
