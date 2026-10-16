// F8 import: szintetikus előnézetek, állapotok (mockolt API-hoz). Nincs valódi útvonal és nincs személyes adat.
import type { ImportAllapot, ObsidianElonezet, V2Elonezet } from '../src/lib/import/tipusok';

export const ID = 'obs-0123456789abcdef';
export const FORRAS = '/synthetic/Vault';
export const CEL = '/synthetic/Vault (Manifold)';

export function elonezet(felulir: Partial<ObsidianElonezet> = {}): ObsidianElonezet {
  return {
    verzio: 1, id: ID, fajta: 'obsidian', forras: FORRAS, cel: CEL, eredmeny: 'figyelmeztet', akadaly: [],
    figyelmeztetes: ['kihagyott_elemek', 'nem_tamogatott_pluginok'], allapot: null,
    opciok: { obsidian_mappa: true, kuka_mappa: false, nev: '' },
    osszesites: { fajl_db: 12, bajt: 34567, md_db: 8, canvas_db: 1, base_db: 0, csatolmany_db: 2, obsidian_db: 1, egyeb_db: 0, mappa_db: 3, kihagyott_db: 2, masolando_db: 12, megvan_db: 0 },
    fajlok: [{ ut: 'Note.md', fajta: 'md', meret: 100, muvelet: 'masol' }], fajlok_csonkitva: false,
    kihagyott: [{ ut: '.trash', ok: 'obsidian_kuka' }, { ut: 'Shortcut.md', ok: 'symlink' }], utkozesek: [],
    linkek: { wikilink_db: 5, markdown_link_db: 2, beagyazas_db: 3, frontmatter_db: 4, beallitas: { wikilinkek: true, link_formatum: 'rovid' } },
    obsidian: {
      beallitasok: [
        { kulcs: 'beallitasok.szerkeszto.tab_meret', ertek: 4, forras: '.obsidian/app.json#tabSize', mod: 'ir' },
        { kulcs: 'beallitasok.fajlok.link_formatum', ertek: 'relativ', forras: '.obsidian/app.json#newLinkFormat', mod: 'ir' },
        { kulcs: 'beallitasok.megjelenes.tema', ertek: 'sotet', forras: '.obsidian/appearance.json#theme', mod: 'azonos' },
      ],
      nem_atvett: [{ forras: '.obsidian/hotkeys.json', ok: 'nem_tamogatott' }],
      mag_pluginok: [
        { id: 'backlink', be: true, allapot: 'tamogatott', modul: 'hivatkozasok' },
        { id: 'file-explorer', be: true, allapot: 'beepitett', modul: null },
        { id: 'sync', be: false, allapot: 'nem_tamogatott', modul: null },
      ],
      kozossegi_pluginok: [{ id: 'dataview', be: true, allapot: 'nem_tamogatott' }],
      tipusok_db: 2,
    },
    atiras: [], letrehozando: [CEL], szabad_bajt: 5_000_000_000, terv_hash: 'hash-1', ...felulir,
  };
}

export function v2Elonezet(felulir: Partial<V2Elonezet> = {}): V2Elonezet {
  return {
    verzio: 1, id: 'v2-0123456789abcdef', fajta: 'v2', forras: '/synthetic/old-os', eredmeny: 'figyelmeztet', akadaly: [], figyelmeztetes: ['utkozes_kihagyva'],
    kulcsok: [{ kulcs: 'sema.mod', jelen: 'laza', uj: 'szigoru' }],
    utkozesek: [{ kulcs: 'beallitasok.x', jelen: 'a', v2: 'b' }],
    nem_atvett: [{ kulcs: 'schema.json', ok: 'sema_hibas' }],
    nem_munkater_kulcs_db: 4, azonos_db: 2, sema: { cel: '/synthetic/ws/schema.json', muvelet: 'ir' }, valtozas_db: 2, ujrainditas: true, terv_hash: 'v2-hash', ...felulir,
  };
}

export function allapot(felulir: Partial<ImportAllapot> = {}): ImportAllapot {
  return {
    id: ID, fajta: 'obsidian', allapot: 'kesz', fut: false, forras: FORRAS, cel: CEL, kezdve: '2026-10-16T10:00:00', frissitve: '2026-10-16T10:05:00',
    opciok: { obsidian_mappa: true, kuka_mappa: false, nev: '' }, terv_hash: 'hash-1', hiba: null,
    eredmeny: { id: ID, allapot: 'kesz', cel: CEL, munkater_id: 'ws-1', masolt_db: 12, megvolt_db: 0, bajt: 34567, kihagyott_db: 2, beallitasok_irva: ['beallitasok.szerkeszto.tab_meret'], forras_valtozott: [], naplo: '/synthetic/install/imports/obs-0123456789abcdef', ismetles: false },
    ...felulir,
  };
}
