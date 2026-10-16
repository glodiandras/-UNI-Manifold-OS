// A Manifold-OS vezérlő telepítése (C17): a feladatsor és a kapcsolók feliratkozása a core eseményeire, a feladat
// végének értesítése, a vezérlő parancsai és a modulok jegyzet-parancsainak helyőrzői. Az `App.svelte` hívja egyszer.
// A lap maga (`hej/ManifoldLap.svelte`) a héj része; a gomb és a ⇧⌘M az `alapParancsok.ts`-ben él.

import type { Felulet } from '../lib/elrendezes/felulet.svelte';
import { ertesitesek } from '../lib/ertesites/ertesites.svelte';
import type { CoreKapcsolat } from '../lib/core/ws.svelte';
import { tick } from 'svelte';
import { t, tk } from '../lib/i18n';
import { Activity, Link, MessageCircleQuestionMark, Save } from '../lib/ikon/ikonok';
import type { Regiszter } from '../lib/parancsok/regiszter';
import { vezerloApi } from '../lib/vezerlo/api';
import { feladatsor } from '../lib/vezerlo/feladatsor.svelte';
import { feladatHiba, feladatSzoveg } from '../lib/vezerlo/megjelenites';
import { videoBevitel } from '../lib/vezerlo/videoBevitel.svelte';
import { vezerloKapcsolok } from '../lib/vezerlo/kapcsolok.svelte';
import type { Feladat } from '../lib/vezerlo/tipusok';
import { HELYORZOK } from './helyorzok';

/** A feladat végének értesítése (a munkafelületen az OS egyetlen hangja): „Részletek” a lapot a feladatra nyitja. */
export function feladatVege(f: Feladat, felulet: Felulet): void {
  const nev = feladatSzoveg(f.cim) || f.tipus || t('feladat');
  const muvelet = {
    nev: t('Részletek'),
    futtat: () => {
      felulet.atfedes = null;
      felulet.manifoldFeladat = f.id;
      felulet.manifoldMegnyit();
    },
  };
  // E10: a rendszerértesítésbe a kézzel indított feladat vége megy (a gép magától indított munkája nem zavar; a hibája igen: a hiba szint mindig megy)
  const rendszer = f.automatikus !== true;
  if (f.allapot === 'kesz') ertesitesek.ertesit({ szint: 'siker', cim: t('Kész: {nev}', { nev }), muvelet, rendszer });
  else if (f.allapot === 'hiba') ertesitesek.ertesit({ szint: 'hiba', cim: t('Hiba: {nev}', { nev }), szoveg: feladatHiba(f), muvelet, rendszer });
  else if (f.allapot === 'megallitva') ertesitesek.ertesit({ szint: 'info', cim: t('Megállítva: {nev}', { nev }), muvelet });
  else if (f.allapot === 'megszakadt') ertesitesek.ertesit({ szint: 'figyelmeztetes', cim: t('Megszakadt: {nev}', { nev }), szoveg: feladatHiba(f), muvelet, rendszer });
}

const jegyzetNyitva = (f: Felulet) => !!f.munkaterulet.aktivFul?.ut?.toLowerCase().endsWith('.md');

export function vezerloTelepit(reg: Regiszter, felulet: Felulet, kapcsolat: CoreKapcsolat): () => void {
  const le = [
    feladatsor.figyel(kapcsolat, (f) => feladatVege(f, felulet)),
    vezerloKapcsolok.figyel(kapcsolat),
    reg.regisztralMind([
      {
        id: 'manifold.most',
        nev: tk('Manifold: futó feladatok'),
        kategoria: tk('Manifold'),
        ikon: Activity,
        futtat: () => {
          felulet.atfedes = null;
          felulet.vezerlo.nyitott.most = true;
          felulet.manifoldFeladat = null;
          felulet.manifoldMegnyit();
        },
      },
      {
        // a videólánc (C20a) valódi parancsa: nincs hozzá helyőrző (a Bevitel szakasz addig üres-állapot szöveg volt)
        id: 'video.link',
        nev: tk('Videó hozzáadása linkből…'),
        kategoria: tk('Manifold'),
        ikon: Link,
        futtat: () => {
          felulet.atfedes = null;
          felulet.vezerlo.nyitott.bevitel = true;
          felulet.manifoldFeladat = null;
          felulet.manifoldMegnyit();
          videoBevitel.kerFokuszt();
        },
      },
      {
        // C25b: a vault-válasz a vezérlőben (a válasz a vaultba nem íródik, 58(d))
        id: 'kereses.kerdezz',
        nev: tk('Kérdezz a vaulttól…'),
        kategoria: tk('Manifold'),
        ikon: MessageCircleQuestionMark,
        futtat: () => {
          felulet.atfedes = null;
          felulet.vezerlo.nyitott.kerdezz = true;
          felulet.manifoldFeladat = null;
          felulet.manifoldMegnyit();
          void tick().then(() => document.getElementById('kerdezz-mezo')?.focus());
        },
      },
      {
        id: 'manifold.mentes',
        nev: tk('Manifold: mentés a belső lemezre'),
        kategoria: tk('Manifold'),
        ikon: Save,
        futtat: async () => {
          try {
            await vezerloApi.mentesInditas();
            ertesitesek.ertesit({ szint: 'info', cim: t('A mentés elindult'), szoveg: t('A belső lemezre készül a szöveges pillanatkép.') });
          } catch (e) {
            ertesitesek.ertesit({ szint: 'hiba', cim: t('A mentés nem indult el'), szoveg: e instanceof Error ? e.message : String(e) });
          }
        },
      },
      ...(['asszisztens', 'tracker'] as const).flatMap((nev) => {
        const [be, ki] = nev === 'asszisztens' ? [tk('Asszisztens bekapcsolása'), tk('Asszisztens kikapcsolása')] : [tk('Tracker bekapcsolása'), tk('Tracker kikapcsolása')];
        return [
          { id: `manifold.${nev}-be`, nev: be, kategoria: tk('Manifold'), elerheto: () => !vezerloKapcsolok.ertek[nev], futtat: () => vezerloKapcsolok.allit(nev, true) },
          { id: `manifold.${nev}-ki`, nev: ki, kategoria: tk('Manifold'), elerheto: () => vezerloKapcsolok.ertek[nev], futtat: () => vezerloKapcsolok.allit(nev, false) },
        ];
      }),
    ]),
    // a modulok jegyzet-parancsai: helyőrzők, amíg a tulajdonos chat el nem készíti (ugyanezen az azonosítón)
    reg.regisztralMind(
      HELYORZOK.map((h) => ({
        id: h.id,
        nev: h.nev,
        kategoria: tk('Jegyzet'),
        elerheto: () => jegyzetNyitva(felulet),
        futtat: () => {
          ertesitesek.ertesit({ szint: 'info', cim: t(h.nev), szoveg: t('Ez a funkció még nem érhető el.') });
        },
      })),
    ),
  ];
  return () => le.forEach((f) => f());
}
