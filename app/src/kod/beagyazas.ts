// A `![[x.cpp]]` (és bármely ismert nyelv, F10: `![[x.py]]`) beágyazás (C36a-UI): csak olvasható, színezett kód (az Olvasó
// `kodSzinez`-ével, ugyanazok a `tok-*` osztályok), fejléc a fájlnévvel, a nyelv nevével, „Megnyitás” gombbal és az utolsó ⌘R
// jelvényével („4/5 átment”). Az index a forrást `egyeb` típusnak adja (C36a, G döntés): ez a renderelő az `egyeb` típust
// kiterjesztés szerint választja, minden más marad link-chip. A szerkeszthető beágyazás nem része (C36a2).

import { kerdez } from '../lib/core/api';
import { t } from '../lib/i18n';
import { fajlNev } from '../lib/vault/fajlok.svelte';
import type { BeagyazasRenderelo } from '../szerkeszto/beagyazas/regiszter';
import { chip } from '../szerkeszto/beagyazas/rajzol';
import type { FajlOlvasas } from '../szerkeszto/dokumentum/api';
import { linkMegnyit, nyitasMod } from '../szerkeszto/linkek/navigacio';
import { kodSzinez } from '../szerkeszto/renderelok/kodszin';
import { szerkesztok } from '../szerkeszto/szerkesztok.svelte';
import { kodFutasok, type Osszesito } from './futas.svelte';
import { KOD_UT, nyelvUt } from './nyelvek.svelte';

/** A jelvény szövege és fajtája egy összesítőből (vagy `null`, ha még nem futott). */
export function jelveny(o: Osszesito | undefined): { szoveg: string; fajta: 'jo' | 'rossz' | 'semleges' } | null {
  if (!o) return null;
  if (o.allapot === 'megszakitva') return { szoveg: t('megszakítva'), fajta: 'semleges' };
  if (o.allapot === 'hiba') return { szoveg: t('nem futott le'), fajta: 'rossz' };
  if (!o.fordit_ok) return { szoveg: t('fordítási hiba'), fajta: 'rossz' };
  if (!o.tesztek_db) return { szoveg: t('lefordul'), fajta: 'semleges' };
  return { szoveg: t('{atment}/{db} átment', { atment: o.atment_db, db: o.tesztek_db }), fajta: o.atment_db === o.tesztek_db ? 'jo' : 'rossz' };
}

function jelvenyRajzol(span: HTMLElement, ut: string): void {
  const j = jelveny(kodFutasok.utolso[ut]);
  span.hidden = !j;
  span.textContent = j?.szoveg ?? '';
  span.className = `kod-jelveny ${j?.fajta ?? ''}`;
}

export const kodBeagyazasRenderelo: BeagyazasRenderelo = {
  tipus: 'egyeb',
  async render(adat, link, kont, o) {
    const ut = adat.ut!;
    if (!KOD_UT.test(ut)) return chip(adat, link, kont, o);
    const nyelv = nyelvUt(ut);
    kont.className = 'beagyazas kod-beagyazas';
    kont.replaceChildren();
    const fej = document.createElement('div');
    fej.className = 'kod-beagyazas-fej';
    const nev = document.createElement('a');
    nev.className = 'beagyazas-cim';
    nev.setAttribute('role', 'link');
    nev.tabIndex = 0;
    nev.textContent = fajlNev(ut);
    const nyit = (e: MouseEvent | KeyboardEvent) => {
      e.preventDefault();
      e.stopPropagation();
      void linkMegnyit({ forras: o.forras, cel: link.cel, alcel: null }, nyitasMod(e));
    };
    nev.addEventListener('click', nyit);
    nev.addEventListener('keydown', (e) => e.key === 'Enter' && nyit(e));
    const nyelvJel = document.createElement('span');
    nyelvJel.className = 'kod-nyelv-jel';
    nyelvJel.textContent = nyelv?.nev ?? '';
    const jel = document.createElement('span');
    jelvenyRajzol(jel, ut);
    const le = kodFutasok.figyel((u) => u === ut && jelvenyRajzol(jel, ut));
    o.jel?.addEventListener('abort', le, { once: true });
    const gomb = document.createElement('button');
    gomb.type = 'button';
    gomb.className = 'kod-beagyazas-nyit';
    gomb.textContent = t('Megnyitás');
    gomb.addEventListener('click', nyit);
    fej.append(nev, nyelvJel, jel, gomb);
    const pre = document.createElement('pre');
    pre.className = 'kod-beagyazas-kod';
    if (o.kompakt) pre.classList.add('kompakt');
    const code = document.createElement('code');
    pre.append(code);
    kont.append(fej, pre);
    // a nyitott (esetleg mentetlen) dokumentum szövege a frissebb; különben a lemezen álló
    const nyitott = szerkesztok.dokumentumok.kap(ut);
    let szoveg: string;
    if (nyitott) szoveg = nyitott.szoveg.toString();
    else {
      const f = await kerdez<FajlOlvasas>(`/api/vault/fajl?ut=${encodeURIComponent(ut)}`, { idokorlat: 15000, jel: o.jel });
      szoveg = f.tartalom;
    }
    if (o.jel?.aborted) return;
    await kodSzinez(szoveg.replace(/\n$/, ''), nyelv?.kerites[0] ?? '', code);
  },
};
