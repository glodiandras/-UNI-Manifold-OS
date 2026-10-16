// A PDF-olvasó és a lejátszó telepítése (C16): a `.pdf` és a videó/hang fül nézete, a `![[x.pdf]]` beágyazás, a ⌘P
// parancsai és a ⇧⌘I (beszúrás a jegyzetbe: PDF-ből kiemelés + idézet, a lejátszóból időkód). Az `App.svelte` hívja.

import './media.css';
import type { CoreKapcsolat } from '../lib/core/ws.svelte';
import { nezetek } from '../lib/elrendezes/nezetek.svelte';
import { tk } from '../lib/i18n';
import { Highlighter } from '../lib/ikon/ikonok';
import type { Parancs, Regiszter } from '../lib/parancsok/regiszter';
import { beagyazasRenderelok } from '../szerkeszto/beagyazas/regiszter';
import { mediaNezetek, type MediaParancs, type MediaPeldany } from './aktiv.svelte';
import Lejatszo from './Lejatszo.svelte';
import { pdfBeagyazasRenderelo } from './pdf/beagyazas';
import { ervenytelenit } from './pdf/dokumentum';
import PdfFul from './pdf/PdfFul.svelte';

const PDF_KIT = /\.pdf$/i;
const VIDEO_KIT = /\.(mp4|m4v|mov|webm|mkv|ogv)$/i;
const HANG_KIT = /\.(mp3|m4a|wav|flac|ogg|opus|aac|3gp)$/i;

const PDF_PARANCSOK: [MediaParancs, string][] = [
  ['kereses', tk('PDF: keresés')],
  ['kov-oldal', tk('PDF: következő oldal')],
  ['elozo-oldal', tk('PDF: előző oldal')],
  ['ugras', tk('PDF: ugrás oldalra…')],
  ['belyegek', tk('PDF: oldalbélyegek be/ki')],
  ['nagyit', tk('PDF: nagyítás')],
  ['kicsinyit', tk('PDF: kicsinyítés')],
  ['oldalszelesseg', tk('PDF: oldalszélesség')],
  ['egesz-oldal', tk('PDF: egész oldal')],
];

const LEJATSZO_PARANCSOK: [MediaParancs, string][] = [
  ['lejatszas', tk('Lejátszó: lejátszás / szünet')],
  ['hatra', tk('Lejátszó: vissza 10 másodpercet')],
  ['elore', tk('Lejátszó: előre 10 másodpercet')],
  ['gyorsabb', tk('Lejátszó: gyorsabb')],
  ['lassabb', tk('Lejátszó: lassabb')],
  ['felirat', tk('Lejátszó: felirat a képen be/ki')],
  ['atirat', tk('Lejátszó: szűrés az átiratban')],
];

function parancsok(tipus: MediaPeldany['tipus'], lista: [MediaParancs, string][], kategoria: string): Parancs[] {
  return lista.map(([p, nev]) => ({
    id: `${tipus}.${p}`,
    nev,
    kategoria,
    elerheto: () => !!mediaNezetek.cel(tipus),
    futtat: () => mediaNezetek.cel(tipus)?.parancs(p),
  }));
}

export function mediaTelepit(reg: Regiszter, kapcsolat: CoreKapcsolat): () => void {
  const le = [
    nezetek.regisztral({
      id: 'media.pdf',
      illeszkedik: (f, info) => !!f.ut && (info ? info.tipus === 'pdf' : PDF_KIT.test(f.ut)),
      komponens: PdfFul,
      prioritas: 10,
    }),
    nezetek.regisztral({
      id: 'media.lejatszo',
      illeszkedik: (f, info) => !!f.ut && (info ? info.tipus === 'video' || info.tipus === 'hang' : VIDEO_KIT.test(f.ut) || HANG_KIT.test(f.ut)),
      komponens: Lejatszo,
      prioritas: 10,
    }),
    beagyazasRenderelok.regisztral(pdfBeagyazasRenderelo),
    reg.regisztral({
      id: 'media.beszur',
      nev: tk('Beszúrás a jegyzetbe: kiemelés idézetként a PDF-ből / időkód a lejátszóból'),
      kategoria: tk('Média'),
      billentyu: 'Mod+Shift+I',
      ikon: Highlighter,
      elerheto: () => !!mediaNezetek.cel(undefined, true),
      futtat: () => mediaNezetek.cel(undefined, true)?.parancs('beszur'),
    }),
    reg.regisztralMind(parancsok('pdf', PDF_PARANCSOK, tk('PDF'))),
    reg.regisztralMind(parancsok('lejatszo', LEJATSZO_PARANCSOK, tk('Lejátszó'))),
    // a megváltozott vagy törölt PDF a következő megnyitáskor újratöltődik
    kapcsolat.figyel('vault_valtozas', (e) => {
      for (const ut of [...((e.kulso as string[] | undefined) ?? []), ...((e.torolt as string[] | undefined) ?? [])])
        if (PDF_KIT.test(ut)) ervenytelenit(ut);
    }),
  ];
  return () => le.forEach((f) => f());
}
