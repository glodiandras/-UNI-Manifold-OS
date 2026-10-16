// A beágyazott keresés (08-search-13): a ```` ```query ```` kódblokk a vault keresésének élő eredményét rajzolja a jegyzetbe
// (Olvasó és Live Preview). A blokk forrása a keresés szövege (a ⌘⇧F lekérdezés-nyelve); a jegyzet bájtjai nem változnak,
// a blokk semmit nem ír. Az eredmény a core `GET /api/vault/kereses`-éből jön (ugyanaz a lekérdezés, mint az ablaké), a
// vault változására késleltetve frissül, a kapcsolat vagy a blokk megszűnésekor a kérés megszakad. A Keresés modul
// kikapcsolva: a blokk sima kódblokk marad (a regiszter nem adja ki a renderelőt).

import './keresesBlokk.css';
import { t, tp } from '../../lib/i18n';
import { ApiHiba, kerdez } from '../../lib/core/api';
import type { CoreKapcsolat } from '../../lib/core/ws.svelte';
import { ikonElem } from '../../lib/ikon/ikonElem';
import { CircleAlert, Search } from '../../lib/ikon/ikonok';
import { fajlNev } from '../../lib/vault/fajlok.svelte';
import { darabok, sorokraEgyesit, utf16Oszlop, type KeresesValasz } from '../../lib/kereses/vaultKereses.svelte';
import { nyitasMod, type NyitasMod } from '../linkek/navigacio';
import type { KodRenderelo } from './regiszter';

/** Egy blokk legfeljebb ennyi fájlt, fájlonként ennyi egyezés-sort mutat (a teljes lista a ⌘⇧F ablakban). */
export const BLOKK_FAJL_MAX = 50;
export const BLOKK_SOR_MAX = 3;
const FRISSITES_KESLELTETES_MS = 800;

export interface KeresesBlokkKornyezet {
  /** a core eseményei (a vault változására frissít); hiányában nem frissül magától */
  kapcsolat?: Pick<CoreKapcsolat, 'figyel'>;
  /** egy találat megnyitása: a fájl, opcionálisan a sor és az oszlop (UTF-16) */
  megnyit(ut: string, sor: number | null, oszlop: number, mod: NyitasMod): void;
  /** a jegyzet fájlneve a találati fejlécben */
  fajlNev?(ut: string): string;
}

/** A blokk forrásából a keresés szövege: a megjegyzés-sorok (`%%`) nélkül, a sorok szóközzel összefűzve. */
export function blokkLekerdezes(forras: string): string {
  return forras.split(/\r?\n/).map((s) => s.trim()).filter((s) => s && !s.startsWith('%%')).join(' ').trim();
}

const el = (tag: string, osztaly: string, szoveg?: string): HTMLElement => {
  const e = document.createElement(tag);
  e.className = osztaly;
  if (szoveg !== undefined) e.textContent = szoveg;
  return e;
};

function hiba(cel: HTMLElement, szoveg: string): void {
  cel.replaceChildren();
  const d = el('div', 'kereses-blokk-hiba');
  d.setAttribute('role', 'alert');
  d.append(ikonElem(CircleAlert, 14), el('span', '', szoveg));
  cel.appendChild(d);
}

export function keresesBlokkRenderelo(k: KeresesBlokkKornyezet): KodRenderelo {
  const nev = k.fajlNev ?? fajlNev;
  return {
    nyelv: 'query',
    interaktiv: true,
    becsultMagassag: () => 96,
    render(forras, cel, kk) {
      const lekerdezes = blokkLekerdezes(forras);
      const doboz = el('section', 'kereses-blokk');
      doboz.setAttribute('aria-label', t('Beágyazott keresés'));
      const fej = el('div', 'kereses-blokk-fej');
      fej.append(ikonElem(Search, 14), el('code', 'kereses-blokk-q', lekerdezes || t('(üres keresés)')));
      const db = el('span', 'kereses-blokk-db');
      db.setAttribute('role', 'status');
      fej.appendChild(db);
      if (kk.blokk) {
        const forrasGomb = el('button', 'kereses-blokk-forras', t('Lekérdezés szerkesztése'));
        (forrasGomb as HTMLButtonElement).type = 'button';
        forrasGomb.addEventListener('click', () => kk.blokk!.forrasba());
        fej.appendChild(forrasGomb);
      }
      const torzs = el('div', 'kereses-blokk-torzs');
      doboz.append(fej, torzs);
      cel.replaceChildren(doboz);

      if (!lekerdezes) {
        db.textContent = '';
        torzs.appendChild(el('p', 'kereses-blokk-ures', t('Írj keresést a blokkba, pl. tag:#projekt vagy [status:kész].')));
        return;
      }

      let vezerlo: AbortController | null = null;
      let sorszam = 0;
      let idozito: ReturnType<typeof setTimeout> | null = null;
      let vege = false;

      const rajzol = (v: KeresesValasz) => {
        torzs.replaceChildren();
        db.textContent = v.osszes === 0 ? t('Nincs találat') : v.legalabb ? tp('legalább {n} találó fájl', v.osszes) : tp('{n} találó fájl', v.osszes);
        const lista = el('ul', 'kereses-blokk-lista');
        for (const f of v.talalatok.slice(0, BLOKK_FAJL_MAX)) {
          const li = el('li', 'kereses-blokk-fajl');
          const gomb = el('button', 'kereses-blokk-nev', nev(f.ut)) as HTMLButtonElement;
          gomb.type = 'button';
          gomb.title = f.ut;
          gomb.addEventListener('click', (e) => k.megnyit(f.ut, null, 0, mod(e)));
          li.appendChild(gomb);
          const sorok = sorokraEgyesit(f);
          for (const h of sorok.slice(0, BLOKK_SOR_MAX)) {
            const s = el('button', 'kereses-blokk-sor') as HTMLButtonElement;
            s.type = 'button';
            s.title = `${f.ut}:${h.sor}`;
            s.append(el('span', 'kereses-blokk-sorszam', String(h.sor)));
            const sz = el('span', 'kereses-blokk-szoveg');
            for (const d of darabok(h, 40, 100)) {
              if (d.jelolt) sz.appendChild(el('mark', '', d.t));
              else sz.append(document.createTextNode(d.t));
            }
            s.appendChild(sz);
            s.addEventListener('click', (e) => k.megnyit(f.ut, h.sor, utf16Oszlop(h.szoveg, h.oszlop), mod(e)));
            li.appendChild(s);
          }
          if (sorok.length > BLOKK_SOR_MAX) li.appendChild(el('span', 'kereses-blokk-tobb', t('+{n} további sor', { n: sorok.length - BLOKK_SOR_MAX })));
          lista.appendChild(li);
        }
        torzs.appendChild(lista);
        if (v.talalatok.length > BLOKK_FAJL_MAX) torzs.appendChild(el('p', 'kereses-blokk-tobb', t('Az első {n} fájl látszik; a többi a keresőablakban.', { n: BLOKK_FAJL_MAX })));
      };

      const mod = (e: MouseEvent): NyitasMod => nyitasMod(e);

      const frissit = async () => {
        const en = ++sorszam;
        vezerlo?.abort();
        const v = (vezerlo = new AbortController());
        const jel = kk.jel;
        const megszakit = () => v.abort();
        jel.addEventListener('abort', megszakit, { once: true });
        try {
          const r = await kerdez<KeresesValasz>(`/api/vault/kereses?q=${encodeURIComponent(lekerdezes)}&limit=${BLOKK_FAJL_MAX}&kornyezet=0`, { idokorlat: 15000, jel: v.signal });
          if (vege || en !== sorszam) return;
          rajzol(r);
        } catch (e) {
          if (vege || en !== sorszam) return;
          db.textContent = '';
          if (e instanceof ApiHiba && e.statusz === 503) {
            torzs.replaceChildren(el('p', 'kereses-blokk-ures', t('Az index még épül — a keresés hamarosan elérhető.')));
            return;
          }
          hiba(torzs, e instanceof Error ? e.message : String(e));
        } finally {
          jel.removeEventListener('abort', megszakit);
        }
      };

      const kesleltet = () => {
        if (vege) return;
        if (idozito) clearTimeout(idozito);
        idozito = setTimeout(() => { idozito = null; void frissit(); }, FRISSITES_KESLELTETES_MS);
      };
      const le = [k.kapcsolat?.figyel('vault_valtozas', kesleltet), k.kapcsolat?.figyel('index', kesleltet)].filter((f): f is () => void => !!f);
      db.textContent = t('Keresés…');
      void frissit();

      return () => {
        vege = true;
        sorszam++;
        if (idozito) clearTimeout(idozito);
        vezerlo?.abort();
        le.forEach((f) => f());
      };
    },
  };
}
