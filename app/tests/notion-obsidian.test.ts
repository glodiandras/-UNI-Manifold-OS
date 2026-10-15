// A C09 kapuja: minden Notion-művelet után a fájl érvényes Markdown, és Obsidianban azonosan jelenik meg.
// A 10 eset mindegyike valódi nézeten fut (a `/` menü, a blokkmenü-műveletek, a táblázatszerkesztő, az
// eszköztár), és ellenőrzi:
//   1. a kimenet pontos szövege;
//   2. hibátlan elemzés (nincs hibacsomópont);
//   3. az Olvasó HTML-je azonos egy KÉZZEL ÍRT, más formázású, de Obsidianban ugyanúgy megjelenő változatéval
//      (a pozíció-attribútumok nélkül);
//   4. a visszavonás pontosan az eredeti szöveget adja vissza.
// Ha a `MOS_NOTION_OBSIDIAN` környezeti változó egy mappa, az esetek előtte/utána jegyzetei oda is kiíródnak
// (tests/kezi/notion_obsidian.py: a valódi Obsidianban való összevetéshez).

import { mkdirSync, writeFileSync } from 'node:fs';
import { undo } from '@codemirror/commands';
import { EditorSelection } from '@codemirror/state';
import type { EditorView } from '@codemirror/view';
import { afterEach, describe, expect, it } from 'vitest';
import { korbefog } from '../src/szerkeszto/formazas';
import { obsidianElemzo } from '../src/szerkeszto/markdown/elemzo';
import { dokumentumRenderel } from '../src/szerkeszto/olvaso/html';
import { LustaRajzolo } from '../src/szerkeszto/olvaso/lusta';
import { blokkok } from '../src/szerkeszto/notion/blokkmodell';
import { linkParancs } from '../src/szerkeszto/notion/eszkoztar';
import { atalakit, blokkLink, duplikal, idBeir, mozgat } from '../src/szerkeszto/notion/muveletek';
import { billentyu, gepel, hibatlan, nezet, tisztit } from './notion-segedek';

afterEach(tisztit);

function html(szoveg: string): string {
  const d = document.createElement('div');
  d.appendChild(dokumentumRenderel(obsidianElemzo.parse(szoveg), { olvas: (a, b) => szoveg.slice(a, b), ut: 'proba.md', lusta: LustaRajzolo.azonnali(), elotag: 'p' }));
  return d.innerHTML.replace(/ data-[a-z-]+="\d+"/g, '').replace(/>\s+</g, '><');
}

const blokk = (v: EditorView, szoveg: string) => {
  const bl = blokkok(v.state);
  const b = bl.find((x) => v.state.doc.line(x.elsoSor).text.includes(szoveg));
  if (!b) throw new Error(`nincs blokk: ${szoveg}`);
  return { bl, b };
};

function alkalmaz(v: EditorView, sz: { changes: unknown; selection: { anchor: number } } | null, esemeny = 'input.proba'): void {
  if (!sz) throw new Error('nincs változás');
  v.dispatch({ changes: sz.changes as never, selection: sz.selection, userEvent: esemeny });
}

function kijelol(v: EditorView, szoveg: string): void {
  const a = v.state.doc.toString().indexOf(szoveg);
  v.dispatch({ selection: EditorSelection.single(a, a + szoveg.length) });
}

interface Eset {
  nev: string;
  elotte: string;
  /** a kurzor kezdőhelye (alapból a dokumentum vége) */
  kurzor?: number;
  muvelet(v: EditorView): void;
  elvart: string;
  /** kézzel írt, más formázású változat, amelynek az Obsidian-megjelenése azonos */
  kanonikus: string;
}

const ESETEK: Eset[] = [
  {
    nev: 'bekezdés → Fejezet 2 (blokkmenü: Átalakítás)',
    elotte: 'Bevezető\n\nSzöveg a fejezetnek.\n\nVége\n',
    muvelet(v) {
      const { b } = blokk(v, 'Szöveg a fejezetnek.');
      alkalmaz(v, atalakit(v.state, b, { tipus: 'fejezet', szint: 2 }), 'input.atalakit');
    },
    elvart: 'Bevezető\n\n## Szöveg a fejezetnek.\n\nVége\n',
    kanonikus: 'Bevezető\n\nSzöveg a fejezetnek.\n---\n\nVége\n',
  },
  {
    nev: '/ menü: callout típussal, a törzs begépelve',
    elotte: 'Előtte\n\n\n\nUtána\n',
    kurzor: 8,
    muvelet(v) {
      gepel(v, '/tip');
      billentyu(v, 'Enter');
      gepel(v, 'Hasznos tipp');
    },
    elvart: 'Előtte\n\n> [!tip]\n> Hasznos tipp\n\nUtána\n',
    kanonikus: 'Előtte\n\n>[!tip]\n>Hasznos tipp\n\nUtána\n',
  },
  {
    nev: '/ menü: összecsukható callout (toggle) címmel és törzzsel',
    elotte: 'Szöveg\n\n\n\nVége\n',
    kurzor: 8,
    muvelet(v) {
      gepel(v, '/toggle');
      billentyu(v, 'Enter');
      gepel(v, 'GYIK'); // a „Cím” helyőrző kijelölve volt
      v.dispatch({ selection: { anchor: v.state.doc.line(4).to } });
      gepel(v, 'Rejtett válasz');
    },
    elvart: 'Szöveg\n\n> [!note]- GYIK\n> Rejtett válasz\n\nVége\n',
    kanonikus: 'Szöveg\n\n>[!note]- GYIK\n>Rejtett válasz\n\nVége\n',
  },
  {
    nev: 'blokkfogó: gyerekes listaelem mozgatása lefelé',
    elotte: '- a\n\t- a1\n\t- a2\n- b\n- c\n',
    muvelet(v) {
      const { bl, b } = blokk(v, '- a');
      const cel = bl.find((x) => v.state.doc.line(x.elsoSor).text === '- b')!;
      alkalmaz(v, mozgat(v.state, bl, b, { blokk: cel, hely: 'utan' }), 'move.blokk');
    },
    elvart: '- b\n- a\n\t- a1\n\t- a2\n- c\n',
    kanonikus: '- b\n- a\n    - a1\n    - a2\n- c\n',
  },
  {
    nev: 'blokkfogó: számozott listaelem mozgatása, újraszámozás',
    elotte: '1. alma\n2. körte\n3. szilva\n',
    muvelet(v) {
      const { bl, b } = blokk(v, 'szilva');
      alkalmaz(v, mozgat(v.state, bl, b, { blokk: bl[0], hely: 'elott' }), 'move.blokk');
    },
    elvart: '1. szilva\n2. alma\n3. körte\n',
    kanonikus: '1. szilva\n1. alma\n1. körte\n',
  },
  {
    nev: 'blokkfogó: legfelső szintű blokk (táblázat) a callout mögé húzva',
    elotte: '# Cím\n\n| a | b |\n|---|---|\n| 1 | 2 |\n\n> [!note] N\n> törzs\n\nVég\n',
    muvelet(v) {
      const { bl, b } = blokk(v, '| a | b |');
      const cel = bl.find((x) => x.tipus === 'callout')!;
      alkalmaz(v, mozgat(v.state, bl, b, { blokk: cel, hely: 'utan' }), 'move.blokk');
    },
    elvart: '# Cím\n\n> [!note] N\n> törzs\n\n| a | b |\n|---|---|\n| 1 | 2 |\n\nVég\n',
    kanonikus: '# Cím\n\n\n> [!note] N\n> törzs\n\n\n|a|b|\n|-|-|\n|1|2|\n\nVég\n',
  },
  {
    nev: 'blokkmenü: gyerekes feladat-listaelem duplikálása',
    elotte: '- [x] kész\n\t- [ ] rész\n- [ ] másik\n',
    muvelet(v) {
      const { bl, b } = blokk(v, '[x] kész');
      alkalmaz(v, duplikal(v.state, bl, b), 'input.blokk');
    },
    elvart: '- [x] kész\n\t- [ ] rész\n- [x] kész\n\t- [ ] rész\n- [ ] másik\n',
    kanonikus: '- [x] kész\n  - [ ] rész\n- [x] kész\n  - [ ] rész\n- [ ] másik\n',
  },
  {
    nev: 'link a blokkra: ^id a bekezdésre, a listaelemre és (önálló sorba) a táblázatra',
    elotte: 'Bekezdés\n\n- elem\n\t- gyerek\n\n| a |\n|---|\n| 1 |\n',
    muvelet(v) {
      const ids = ['p1aaaa', 'l2bbbb', 't3cccc'];
      const szovegek = ['Bekezdés', '- elem', '| a |'];
      szovegek.forEach((sz, i) => {
        const { b } = blokk(v, sz);
        const r = idBeir(v.state, b, ids[i])!;
        alkalmaz(v, r.szerkesztes, 'input.blokkid');
        expect(blokkLink('Jegyzet', blokk(v, sz).b, ids[i], '')).toBe(`[[Jegyzet#^${ids[i]}]]`);
      });
    },
    elvart: 'Bekezdés ^p1aaaa\n\n- elem ^l2bbbb\n\t- gyerek\n\n| a |\n|---|\n| 1 |\n\n^t3cccc\n',
    // az Obsidian a blokkazonosítót nem mutatja: az olvasó-nézet az azonosítók nélküli jegyzet
    kanonikus: 'Bekezdés\n\n- elem\n\t- gyerek\n\n| a |\n|---|\n| 1 |\n',
  },
  {
    nev: 'táblázat: oszlop beszúrása, igazítás, auto-igazítás képletes és \\|-cellával',
    elotte: '| Név | Érték |\n|---|---:|\n| $|x|$ | 5 |\n| a\\|b | 7 |\n',
    muvelet(v) {
      const cella = (s: number, o: number) => v.dom.querySelector<HTMLElement>(`.nt-tabla [data-sor="${s}"][data-oszlop="${o}"]`)!;
      const menu = (fogo: string, nev: string) => {
        const f = v.dom.querySelector<HTMLElement>(fogo)!;
        f.dispatchEvent(new PointerEvent('pointerdown', { bubbles: true, button: 0 }));
        f.dispatchEvent(new PointerEvent('pointerup', { bubbles: true, button: 0 }));
        [...document.body.querySelectorAll<HTMLElement>('.nt-lebego .nt-menu-elem')].find((e) => e.textContent!.includes(nev))!.click();
      };
      menu('.nt-oszlop-fogo[aria-label^="2."]', 'Beszúrás jobbra'); // a fejléc új oszlopot kap: „Oszlop 3”
      menu('.nt-oszlop-fogo[aria-label^="3."]', 'Igazítás');
      // az almenü: a „Középre” választása
      [...document.body.querySelectorAll<HTMLElement>('.nt-lebego .nt-menu-elem')].find((e) => e.textContent!.includes('Középre'))?.click();
      cella(1, 2).click();
      const i = v.dom.querySelector<HTMLInputElement>('.nt-cella-mezo')!;
      i.value = 'új';
      i.dispatchEvent(new KeyboardEvent('keydown', { key: 'Tab', bubbles: true, cancelable: true }));
    },
    elvart:
      '| Név   | Érték | Oszlop 3 |\n| ----- | ----: | :------: |\n| $|x|$ |     5 |    új    |\n| a\\|b  |     7 |          |\n',
    kanonikus: '|Név|Érték|Oszlop 3|\n|-|-:|:-:|\n|$|x|$|5|új|\n|a\\|b|7||\n',
  },
  {
    nev: 'idézetben álló táblázat sora fel + eszköztár: félkövér, kiemelés, link egy bekezdésben',
    elotte: '> [!note]\n> | a | b |\n> |---|---|\n> | 1 | 2 |\n> | 3 | 4 |\n\nEgy két három szó.\n',
    muvelet(v) {
      // a 2. sor fogójának menüje: „Mozgatás fel”
      const f = [...v.dom.querySelectorAll<HTMLElement>('.nt-sor-fogo')][1];
      f.dispatchEvent(new PointerEvent('pointerdown', { bubbles: true, button: 0 }));
      f.dispatchEvent(new PointerEvent('pointerup', { bubbles: true, button: 0 }));
      [...document.body.querySelectorAll<HTMLElement>('.nt-lebego .nt-menu-elem')].find((e) => e.textContent!.includes('Mozgatás fel'))!.click();
      kijelol(v, 'két');
      korbefog(v, '**');
      kijelol(v, 'három');
      korbefog(v, '==');
      kijelol(v, 'szó');
      linkParancs(v);
      const i = v.dom.querySelector<HTMLInputElement>('.nt-eszk-mezo')!;
      i.value = 'https://pelda.hu';
      i.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', bubbles: true, cancelable: true }));
    },
    elvart:
      '> [!note]\n> | a   | b   |\n> | --- | --- |\n> | 3   | 4   |\n> | 1   | 2   |\n\nEgy **két** ==három== [szó](https://pelda.hu).\n',
    kanonikus:
      '> [!note]\n> |a|b|\n> |-|-|\n> |3|4|\n> |1|2|\n\nEgy __két__ ==három== [szó](https://pelda.hu).\n',
  },
];

const KIMENET = process.env.MOS_NOTION_OBSIDIAN;

describe('Notion-réteg: érvényes Markdown és Obsidian-azonos megjelenés (10 eset)', () => {
  it('pontosan 10 eset van', () => {
    expect(ESETEK).toHaveLength(10);
  });

  ESETEK.forEach((e, i) => {
    it(`${i + 1}. ${e.nev}`, () => {
      const v = nezet(e.elotte, e.kurzor ?? e.elotte.length);
      e.muvelet(v);
      const utana = v.state.doc.toString();
      expect(utana).toBe(e.elvart);
      expect(hibatlan(utana)).toBe(true);
      expect(html(utana)).toBe(html(e.kanonikus));
      expect(html(utana)).not.toBe('');
      if (KIMENET) {
        mkdirSync(KIMENET, { recursive: true });
        const szam = String(i + 1).padStart(2, '0');
        const nev = e.nev.split(':')[0].replace(/[\\/]/g, '-');
        writeFileSync(`${KIMENET}/${szam} - ${nev} — előtte.md`, e.elotte);
        writeFileSync(`${KIMENET}/${szam} - ${nev} — utána.md`, utana);
        writeFileSync(`${KIMENET}/${szam} - ${nev} — kanonikus.md`, e.kanonikus);
      }
      // a visszavonás egy vagy több lépésben, de pontosan az eredetit adja vissza
      for (let n = 0; n < 40 && v.state.doc.toString() !== e.elotte; n++) undo(v);
      expect(v.state.doc.toString()).toBe(e.elotte);
    });
  });
});
