import type { EditorState } from '@codemirror/state';
import { isolateHistory } from '@codemirror/commands';
import type { EditorView } from '@codemirror/view';
import { kerdez } from '../lib/core/api';
import { beallitasok } from '../lib/beallitasok/allapot.svelte';
import type { Felulet } from '../lib/elrendezes/felulet.svelte';
import { ertesitesek } from '../lib/ertesites/ertesites.svelte';
import { t } from '../lib/i18n';
import { linkek } from '../lib/vault/linkek.svelte';
import { vezerloApi } from '../lib/vezerlo/api';
import { irhato } from '../szerkeszto/beallitas';
import { linkSzoveg } from '../szerkeszto/linkek/adat';
import { regiDokumentumokKikerulnek, type TervLink } from '../szerkeszto/linkek/atnevezes';
import { szerkesztok, type SzerkesztoPeldany } from '../szerkeszto/szerkesztok.svelte';

export interface KomponaloKeres {
  mod: 'kivon'|'osszefuz';
  forras: string;
  peldany: SzerkesztoPeldany;
  nezet: EditorView;
  alap: EditorState;
}
export const komponaloAblak = new class { keres = $state.raw<KomponaloKeres | null>(null); }();

export function komponaloElerheto(kivon: boolean): boolean {
  const p = szerkesztok.aktiv, v = p?.nezet();
  return !!p && /\.md$/i.test(p.ut) && p.mod() !== 'olvaso' && !!v && irhato(v) && (!kivon || (v.state.selection.ranges.length === 1 && !v.state.selection.main.empty));
}

export function komponaloNyit(felulet: Felulet, mod: KomponaloKeres['mod']): void {
  if (!komponaloElerheto(mod === 'kivon')) return;
  const p = szerkesztok.aktiv!, v = p.nezet()!;
  felulet.atfedes = null;
  komponaloAblak.keres = { mod, forras: p.ut, peldany: p, nezet: v, alap: v.state };
}

function forrasIrhato(k: KomponaloKeres): boolean {
  return szerkesztok.aktiv === k.peldany && k.peldany.nezet() === k.nezet && k.peldany.ut === k.forras && k.peldany.mod() !== 'olvaso' && irhato(k.nezet);
}

function forrasAzonos(k: KomponaloKeres): boolean {
  return forrasIrhato(k) && k.nezet.state.doc === k.alap.doc && k.nezet.state.selection.eq(k.alap.selection);
}

export type KivonasCel = { mod: 'uj'; nev: string; mappa?: string } | { mod: 'meglevo'; ut: string; hely: 'veg'|'eleje' };
export interface KivonasEredmeny { ok: boolean; ut: string; nev: string; letrejott: boolean; pillanat: string|null; figyelmeztetes: string|null }

/** Előbb a core biztonságos célírása, azután a még változatlan kijelölés cseréje. A sikertelen/elhagyott csere megőrzi a forrást. */
export async function kivonasVegez(k: KomponaloKeres, cel: KivonasCel, aktiv: () => boolean, utana = beallitasok.ertek.fajlok.kivonas_utana): Promise<{ eredmeny: KivonasEredmeny; cserelve: boolean }> {
  if (!aktiv() || !forrasAzonos(k)) throw new Error(t('s1.napi.szerkeszto_valtozott'));
  const s = k.alap.selection.main;
  const r = await kerdez<KivonasEredmeny>('/api/komponalo/kivon', { metodus: 'POST', torzs: { forras: k.forras, szoveg: k.alap.doc.sliceString(s.from, s.to), cel }, idokorlat: 30000 });
  // A Vault `vault_iras` jelet küld, a szerkesztő viszont csak a külső változásokat tölti újra. A saját célírást ezért közvetlenül frissítjük.
  await dokumentumokFrissit([r.ut]);
  let csere = '';
  try {
    if (utana !== 'semmi' && aktiv() && forrasAzonos(k)) csere = linkSzoveg(await linkek.linkForma(r.ut, k.forras), { nev: r.nev, beagyazas: utana === 'beagyazas' });
    if (!aktiv() || !forrasAzonos(k)) return { eredmeny: r, cserelve: false };
    k.nezet.dispatch({ changes: { from: s.from, to: s.to, insert: csere }, selection: { anchor: s.from + csere.length }, userEvent: 'input.paste', annotations: isolateHistory.of('full') });
    return { eredmeny: r, cserelve: true };
  } catch {
    // A cél már megvan. Egy linkformázási hiba nem teheti úgy újrapróbálhatóvá a kérést, mintha semmi sem íródott volna.
    return { eredmeny: r, cserelve: false };
  }
}

export interface OsszefuzesTerv {
  ok: boolean; forras: string; cel: string; hely: 'veg'|'eleje'; terv_hash: string; blokkolok: string[];
  figyelmeztetesek: Array<{ kod: string; kulcsok?: string[]; db?: number }>;
  modositott_linkek: number; kukaba: string; cel_sorok: { elotte: number; utana: number };
  fajlok: Array<{ ut: string; darab: number; linkek: TervLink[] }>;
}
export interface OsszefuzesEredmeny { ok: boolean; forras: string; cel: string; modositott: string[]; kor: string; forras_kukaban: boolean; forras_hiba: string|null; visszavonhato: boolean }

async function szerkesztesekMentese(): Promise<void> {
  await szerkesztok.dokumentumok.mindLezar();
  if (szerkesztok.dokumentumok.mentetlenUtak().length) throw new Error(t('s1.komponalo.mentes_kell'));
}

function muveletMegengedett(k: KomponaloKeres, mehet: () => boolean): void {
  if (!mehet() || !forrasIrhato(k)) throw new Error(t('s1.napi.szerkeszto_valtozott'));
}

export async function osszefuzesTerv(k: KomponaloKeres, cel: string, hely: 'veg'|'eleje', mehet: () => boolean = () => true): Promise<OsszefuzesTerv> {
  muveletMegengedett(k, mehet);
  await szerkesztesekMentese();
  muveletMegengedett(k, mehet);
  return kerdez('/api/komponalo/osszefuz/terv', { metodus: 'POST', torzs: { forras: k.forras, cel, hely }, idokorlat: 60000 });
}

/** A terv hash-e változatlanul jut a core-hoz. A forrást csak a core helyezi a Kukába, a UI nem töröl fájlt. */
export async function osszefuzesVegez(k: KomponaloKeres, terv: OsszefuzesTerv, mehet: () => boolean = () => true): Promise<OsszefuzesEredmeny> {
  if (!terv.ok || terv.blokkolok.length) throw new Error(t('s1.komponalo.blokkolt'));
  muveletMegengedett(k, mehet);
  await szerkesztesekMentese();
  muveletMegengedett(k, mehet);
  const r = await kerdez<OsszefuzesEredmeny>('/api/komponalo/osszefuz', { metodus: 'POST', torzs: { forras: terv.forras, cel: terv.cel, hely: terv.hely, terv_hash: terv.terv_hash }, idokorlat: 60000 });
  if (r.forras_kukaban) regiDokumentumokKikerulnek(r.forras, false);
  await dokumentumokFrissit(r.modositott);
  return r;
}

async function dokumentumokFrissit(utak: string[]): Promise<void> {
  linkek.ervenytelenit();
  const eredmenyek = await Promise.allSettled(utak.map(ut => szerkesztok.dokumentumok.kap(ut)?.kulsoValtozas()));
  if (eredmenyek.some(r => r.status === 'rejected')) ertesitesek.ertesit({ szint: 'figyelmeztetes', cim: t('s1.komponalo.frissites_hiba'), idotartam: 0 });
}

export async function osszefuzesVisszavon(r: OsszefuzesEredmeny, felulet: Felulet): Promise<void> {
  try {
    await szerkesztesekMentese();
    await vezerloApi.visszavon(r.kor);
    await dokumentumokFrissit([...r.modositott, r.forras]);
    felulet.munkaterulet.megnyit(r.forras);
  } catch (e) {
    ertesitesek.ertesit({ szint: 'hiba', cim: t('s1.komponalo.undo_hiba'), szoveg: e instanceof Error ? e.message : String(e), idotartam: 0 });
  }
}
