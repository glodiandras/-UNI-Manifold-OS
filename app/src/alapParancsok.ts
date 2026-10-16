// A héj saját parancsai (C07). Minden gomb is ezeket futtatja, így a palettából és billentyűről ugyanaz
// történik. A későbbi modulok a saját parancsaikat ugyanígy, a saját chatjükben regisztrálják.

import { beallitasok, modulEngedelyezett } from './lib/beallitasok/allapot.svelte';
import type { BeallitasokValtozas } from './lib/beallitasok/tipusok';
import { ertesitesek } from './lib/ertesites/ertesites.svelte';
import { NAGYITAS, type Felulet } from './lib/elrendezes/felulet.svelte';
import { alkalmaz, type Tema } from './lib/elrendezes/tema';
import { csend } from './lib/elrendezes/csend.svelte';
import { rendszerErtesites } from './lib/ertesites/rendszer';
import { regioFokusz, regioLep } from './lib/fokusz/fokusz';
import { ChevronsDownUp, Columns2, Command, FilePlus, FileClock, FolderOpen, LayoutGrid, Link2, ListTree, Monitor, Moon, Network, PanelBottom, PanelLeft, PanelRight, Plus, Rows2, Search, SlidersHorizontal, Sun, Tag, X, ZoomIn, ZoomOut } from './lib/ikon/ikonok';
import { t, tk } from './lib/i18n';
import { keresoMegnyit, keresoOldalsav } from './lib/kereses/kereso';
import type { Parancs, Regiszter } from './lib/parancsok/regiszter';
import { hejbenFut, hejnek } from './lib/core/hej';
import { finderMegmutat, masolatKeszit } from './lib/vault/faMuveletek';
import type { FaRendezes } from './lib/vault/fa';
import { panelKapcsolatMenu } from './hej/panelKapcsolat';

const FA_RENDEZES_PARANCSOK: [FaRendezes, string][] = [
  ['nev', tk('Fájlfa rendezése: fájlnév (A–Z)')],
  ['nev-forditva', tk('Fájlfa rendezése: fájlnév (Z–A)')],
  ['modositva', tk('Fájlfa rendezése: módosítás, legújabb elöl')],
  ['modositva-regi', tk('Fájlfa rendezése: módosítás, legrégebbi elöl')],
  ['letrehozva', tk('Fájlfa rendezése: létrehozás, legújabb elöl')],
  ['letrehozva-regi', tk('Fájlfa rendezése: létrehozás, legrégebbi elöl')],
];

export function alapParancsok(reg: Regiszter, f: Felulet): () => void {
  const m = f.munkaterulet;
  // a PDF-fül saját ⌘+/⌘−/⌘0 nagyítást kezel: ott a globális UI-nagyítás nem veszi el a billentyűt
  const pdfAktiv = () => !!m.aktivFul?.ut?.toLowerCase().endsWith('.pdf');
  const fanyit = () => {
    f.atfedes = null;
    f.oldalsav.nezet = 'fajlok';
    if (!f.oldalsav.nyitva) csend.oldalsavAtfedes = true;
  };
  const panelFokusz = (muvelet: () => void) => {
    muvelet();
    queueMicrotask(() => document.querySelector<HTMLElement>(`[data-panel-id="${m.aktivPanelId}"] [role="tabpanel"]`)?.focus({ preventScroll: true }));
  };
  const beallit = (valtozas: BeallitasokValtozas, alkalmazas: () => void): void | Promise<void> => {
    if (!beallitasok.adat) { alkalmazas(); return; }
    return beallitasok.ment(valtozas).then(ok => {
      if (!ok) throw new Error(beallitasok.hiba ?? t('beallitasok.mentesi_hiba'));
      alkalmazas();
    });
  };
  const atfedes = (cel: 'paletta' | 'valto') => {
    f.atfedes = f.atfedes === cel ? null : cel;
  };
  const tema = (id: Tema, nev: string, ikon: Parancs['ikon']): Parancs => ({
    id: `tema.${id}`,
    nev,
    kategoria: tk('Téma'),
    ikon,
    elerheto: () => f.tema !== id && !beallitasok.mentes,
    futtat: () => beallit({ megjelenes: { tema: id } }, () => {
      f.tema = id;
      alkalmaz(id);
    }),
  });

  const lista: Parancs[] = [
    { id: 'hej.paletta', nev: tk('Parancspaletta'), kategoria: tk('Általános'), billentyu: 'Mod+P', ikon: Command, atfedesben: true, palettaban: false, futtat: () => atfedes('paletta') },
    { id: 'hej.valto', nev: tk('Fájl megnyitása'), kategoria: tk('Gyorsváltó'), billentyu: 'Mod+O', ikon: Search, atfedesben: true, futtat: () => atfedes('valto') },
    {
      id: 'manifold.vezerlo',
      nev: tk('Manifold áttekintő'),
      kategoria: tk('Manifold'),
      billentyu: 'Mod+Shift+M',
      atfedesben: true,
      futtat: () => {
        f.atfedes = null;
        m.megnyitNezet('manifold');
      },
    },
    {
      id: 'kereses.panel',
      nev: tk('Keresés a vaultban'),
      kategoria: tk('Keresés'),
      billentyu: 'Mod+Shift+F',
      ikon: Search,
      atfedesben: true,
      futtat: () => {
        if (f.atfedes === 'kereso') f.atfedes = null;
        else keresoMegnyit(f);
      },
    },
    { id: 'kereses.oldalsav', nev: tk('Keresés az oldalsávban'), kategoria: tk('Keresés'), ikon: Search, futtat: () => keresoOldalsav(f) },
    {
      id: 'cimkek.panel',
      nev: tk('Címkék (címkefa)'),
      kategoria: tk('Keresés'),
      ikon: Tag,
      futtat: () => {
        f.atfedes = null;
        f.oldalsav.nyitva = true;
        f.oldalsav.nezet = 'cimkek';
      },
    },
    {
      id: 'tulajdonsagok.panel',
      nev: tk('Tulajdonságok (összes tulajdonság)'),
      kategoria: tk('Keresés'),
      ikon: SlidersHorizontal,
      elerheto: () => modulEngedelyezett('tulajdonsagok'),
      futtat: () => {
        f.atfedes = null;
        f.oldalsav.nyitva = true;
        f.oldalsav.nezet = 'tulajdonsagok';
      },
    },
    {
      id: 'tulajdonsagok.kapcsol',
      nev: tk('Tulajdonságok megjelenítése / összecsukása'),
      kategoria: tk('Jegyzet'),
      ikon: SlidersHorizontal,
      elerheto: () => !!m.aktivFul?.ut?.toLowerCase().endsWith('.md'),
      futtat: () => void (f.tulajdonsagok.nyitva = !f.tulajdonsagok.nyitva),
    },
    {
      id: 'elozmenyek.megnyit',
      nev: tk('Jegyzet előzményei'),
      kategoria: tk('Jegyzet'),
      ikon: FileClock,
      elerheto: () => !!m.aktivFul?.ut?.toLowerCase().endsWith('.md'),
      futtat: () => {
        f.atfedes = null;
        f.jobbPanel.nyitva = true;
        f.jobbPanel.elozmenyek = true;
        queueMicrotask(() => document.querySelector<HTMLElement>(`[data-regio="jobb"] [aria-label="${t('A jegyzet pillanatképei')}"] button`)?.focus());
      },
    },
    {
      id: 'fa.megmutat',
      nev: tk('Megmutatás a fájlfában'),
      kategoria: tk('Nézet'),
      elerheto: () => !!m.aktivFul?.ut,
      futtat: () => {
        const ut = m.aktivFul?.ut;
        if (ut) f.megmutatFaban(ut);
      },
    },
    // az átfedésként előjött sáv (C38) a kapcsolóra rögzül, nem tűnik el
    { id: 'hej.oldalsav', nev: tk('Oldalsáv megjelenítése / elrejtése'), kategoria: tk('Nézet'), billentyu: 'Mod+Alt+1', ikon: PanelLeft, futtat: () => void (f.oldalsav.nyitva = !f.oldalsav.nyitva) },
    { id: 'hej.jobb-panel', nev: tk('Jobb panel megjelenítése / elrejtése'), kategoria: tk('Nézet'), billentyu: 'Mod+Alt+2', ikon: PanelRight, futtat: () => void (f.jobbPanel.nyitva = !f.jobbPanel.nyitva) },
    // C25c: a hasonló jegyzetek a (rejtett) jobb panel szakasza — a parancs kinyitja a panelt és a szakaszt
    {
      id: 'kereses.hasonlo',
      nev: tk('Hasonló jegyzetek'),
      kategoria: tk('Keresés'),
      ikon: Network,
      futtat: () => {
        f.jobbPanel.nyitva = true;
        f.jobbPanel.hasonlo = true;
      },
    },
    // csend és elérés (C38): a kapcsoló, és minden rejtett elem egy parancs
    {
      id: 'hej.csend', nev: tk('Csend mód be/ki'), kategoria: tk('Nézet'), elerheto: () => !beallitasok.mentes,
      futtat: () => {
        const be = !f.csend.be;
        return beallit({ megjelenes: { csend: be } }, () => { if (f.csend.be !== be) f.csendKapcsol(be); });
      },
    },
    { id: 'hej.allapotsor', nev: tk('Állapotsor megjelenítése'), kategoria: tk('Nézet'), ikon: PanelBottom, futtat: () => void regioFokusz('allapotsor') },
    {
      id: 'fa.uj-jegyzet',
      nev: tk('Új jegyzet a fájlfában'),
      kategoria: tk('Fájl'),
      ikon: FilePlus,
      billentyu: 'Mod+N',
      futtat: () => {
        f.atfedes = null;
        f.oldalsav.nezet = 'fajlok';
        if (!f.oldalsav.nyitva) csend.oldalsavAtfedes = true;
        f.faUjJegyzet = true;
      },
    },
    { id: 'fa.osszecsuk', nev: tk('Összes mappa összecsukása'), kategoria: tk('Fájl'), ikon: ChevronsDownUp, futtat: () => void (f.oldalsav.nyitott = []) },
    { id: 'fa.kinyit-mind', nev: tk('Összes mappa kinyitása'), kategoria: tk('Fájl'), ikon: ListTree, futtat: () => { fanyit(); f.faKinyitKer++; } },
    ...FA_RENDEZES_PARANCSOK.map(([mod, nev]): Parancs => ({ id: `fa.rendez-${mod}`, nev, kategoria: tk('Fájl'), elerheto: () => f.oldalsav.rendezes !== mod, futtat: () => void (f.oldalsav.rendezes = mod) })),
    { id: 'fa.auto-megmutat', nev: tk('Az aktív fájl automatikus megmutatása be/ki'), kategoria: tk('Fájl'), futtat: () => void (f.oldalsav.autoMegmutat = !f.oldalsav.autoMegmutat) },
    { id: 'fa.minden-fajl', nev: tk('Minden fájltípus mutatása a fában be/ki'), kategoria: tk('Fájl'), futtat: () => void (f.oldalsav.mindenFajl = !f.oldalsav.mindenFajl) },
    { id: 'fa.finder', nev: tk('Megmutatás a Finderben'), kategoria: tk('Fájl'), elerheto: () => !!m.aktivFul?.ut, futtat: () => { const ut = m.aktivFul?.ut; if (ut) return void finderMegmutat(ut); } },
    { id: 'fa.masolat', nev: tk('Másolat készítése'), kategoria: tk('Fájl'), elerheto: () => !!m.aktivFul?.ut, futtat: () => { const ut = m.aktivFul?.ut; if (ut) return void masolatKeszit(f, ut); } },
    // UI-nagyítás (06-workspace-28)
    { id: 'nezet.nagyit', nev: tk('Felület nagyítása'), kategoria: tk('Nézet'), billentyu: 'Mod+=', ikon: ZoomIn, elerheto: () => !pdfAktiv() && f.nagyitas < NAGYITAS.max, futtat: () => f.nagyit(NAGYITAS.lepes) },
    { id: 'nezet.kicsinyit', nev: tk('Felület kicsinyítése'), kategoria: tk('Nézet'), billentyu: 'Mod+-', ikon: ZoomOut, elerheto: () => !pdfAktiv() && f.nagyitas > NAGYITAS.min, futtat: () => f.nagyit(-NAGYITAS.lepes) },
    { id: 'nezet.nagyitas-alap', nev: tk('Felület nagyításának visszaállítása'), kategoria: tk('Nézet'), billentyu: 'Mod+0', elerheto: () => !pdfAktiv() && f.nagyitas !== NAGYITAS.alap, futtat: () => f.nagyitasAlap() },
    // ikonsáv (06-workspace-12) és névvel mentett elrendezések (06-workspace-26)
    { id: 'munkater.valto', nev: tk('Munkaterület váltása'), kategoria: tk('Általános'), ikon: FolderOpen, elerheto: () => hejbenFut(), futtat: () => hejnek({ tipus: 'munkater-valaszto' }) },
    { id: 'ikonsav.kapcsol', nev: tk('Ikonsáv megjelenítése / elrejtése'), kategoria: tk('Nézet'), futtat: () => void (f.ikonsav.lathato = !f.ikonsav.lathato) },
    { id: 'elrendezes.kezel', nev: tk('Munkaterület-elrendezések kezelése'), kategoria: tk('Nézet'), ikon: LayoutGrid, atfedesben: false, futtat: () => void (f.atfedes = 'elrendezesek') },
    { id: 'elrendezes.ment', nev: tk('Munkaterület-elrendezés mentése névvel'), kategoria: tk('Nézet'), ikon: LayoutGrid, futtat: () => void (f.atfedes = 'elrendezesek') },
    // összekapcsolt fülcsoportok (06-workspace-08)
    { id: 'panel.osszekapcsol', nev: tk('Fülcsoport összekapcsolása…'), kategoria: tk('Panel'), ikon: Link2, elerheto: () => m.panelek().length > 1, futtat: () => panelKapcsolatMenu(f, m.aktivPanelId) },
    { id: 'panel.lekapcsol', nev: tk('Fülcsoport leválasztása'), kategoria: tk('Panel'), elerheto: () => m.kapcsoltTarsak(m.aktivPanelId).length > 0, futtat: () => m.lekapcsol() },
    { id: 'ful.ujranyit', nev: tk('Bezárt fül újranyitása'), kategoria: tk('Fül'), billentyu: 'Mod+Shift+T', futtat: () => m.ujranyit() },
    { id: 'navigacio.vissza', nev: tk('Vissza az előző jegyzethez'), kategoria: tk('Navigáció'), billentyu: 'Mod+Alt+ArrowLeft', elerheto: () => m.navigalhato(-1), futtat: () => m.navigal(-1) },
    { id: 'navigacio.elore', nev: tk('Előre a következő jegyzethez'), kategoria: tk('Navigáció'), billentyu: 'Mod+Alt+ArrowRight', elerheto: () => m.navigalhato(1), futtat: () => m.navigal(1) },
    { id: 'ful.uj', nev: tk('Új fül'), kategoria: tk('Fül'), billentyu: 'Mod+T', ikon: Plus, futtat: () => m.ujFul() },
    { id: 'ful.bezar', nev: tk('Fül bezárása'), kategoria: tk('Fül'), billentyu: 'Mod+W', ikon: X, futtat: () => m.bezar() },
    { id: 'ful.kovetkezo', nev: tk('Következő fül'), kategoria: tk('Fül'), billentyu: 'Ctrl+Tab', elerheto: () => m.aktivPanel.fulek.length > 1, futtat: () => m.lep(1) },
    { id: 'ful.elozo', nev: tk('Előző fül'), kategoria: tk('Fül'), billentyu: 'Ctrl+Shift+Tab', elerheto: () => m.aktivPanel.fulek.length > 1, futtat: () => m.lep(-1) },
    ...Array.from({ length: 9 }, (_, i): Parancs => ({
      id: `ful.n${i + 1}`,
      get nev() {
        return i === 8 ? t('Utolsó fül') : t('{n}. fül', { n: i + 1 });
      },
      kategoria: tk('Fül'),
      billentyu: `Mod+${i + 1}`,
      palettaban: false,
      futtat: () => m.nedik(i + 1),
    })),
    { id: 'panel.oszt-jobbra', nev: tk('Osztás jobbra'), kategoria: tk('Panel'), billentyu: 'Mod+Shift+2', ikon: Columns2, futtat: () => m.oszt('sor') },
    { id: 'panel.oszt-le', nev: tk('Osztás lefelé'), kategoria: tk('Panel'), billentyu: 'Mod+Alt+ArrowDown', ikon: Rows2, szerkesztoNyer: true, futtat: () => m.oszt('oszlop') }, // a szerkesztőben a ⌥⌘↓ a CM addCursorBelow-ja
    { id: 'panel.kovetkezo', nev: tk('Következő panel'), kategoria: tk('Panel'), elerheto: () => m.panelek().length > 1, futtat: () => panelFokusz(() => m.panelLep(1)) },
    { id: 'panel.elozo', nev: tk('Előző panel'), kategoria: tk('Panel'), elerheto: () => m.panelek().length > 1, futtat: () => panelFokusz(() => m.panelLep(-1)) },
    { id: 'ful.rogzit', nev: tk('Fül rögzítése / feloldása'), kategoria: tk('Fül'), futtat: () => m.rogzit() },
    { id: 'ful.tobbi-bezar', nev: tk('Többi nem rögzített fül bezárása'), kategoria: tk('Fül'), futtat: () => m.bezarTobbit('tobbi') },
    { id: 'ful.jobb-bezar', nev: tk('Jobbra lévő nem rögzített fülek bezárása'), kategoria: tk('Fül'), futtat: () => m.bezarTobbit('jobb') },
    { id: 'panel.fulek-bezar', nev: tk('Csoport nem rögzített füleinek bezárása'), kategoria: tk('Panel'), futtat: () => m.bezarTobbit('mind') },
    { id: 'panel.bezar', nev: tk('Fülcsoport bezárása'), kategoria: tk('Panel'), futtat: () => m.bezarPanel() },
    { id: 'panel.fokusz-bal', nev: tk('Fókusz a bal oldali panelre'), kategoria: tk('Panel'), elerheto: () => m.panelek().length > 1, futtat: () => panelFokusz(() => m.panelIrany('bal')) },
    { id: 'panel.fokusz-jobb', nev: tk('Fókusz a jobb oldali panelre'), kategoria: tk('Panel'), elerheto: () => m.panelek().length > 1, futtat: () => panelFokusz(() => m.panelIrany('jobb')) },
    { id: 'panel.fokusz-fel', nev: tk('Fókusz a felső panelre'), kategoria: tk('Panel'), elerheto: () => m.panelek().length > 1, futtat: () => panelFokusz(() => m.panelIrany('fel')) },
    { id: 'panel.fokusz-le', nev: tk('Fókusz az alsó panelre'), kategoria: tk('Panel'), elerheto: () => m.panelek().length > 1, futtat: () => panelFokusz(() => m.panelIrany('le')) },
    { id: 'fokusz.kovetkezo-regio', nev: tk('Következő régió'), kategoria: tk('Fókusz'), billentyu: 'F6', palettaban: false, futtat: () => regioLep(1) },
    { id: 'fokusz.elozo-regio', nev: tk('Előző régió'), kategoria: tk('Fókusz'), billentyu: 'Shift+F6', palettaban: false, futtat: () => regioLep(-1) },
    tema('rendszer', tk('A rendszer szerint'), Monitor),
    tema('vilagos', tk('Világos'), Sun),
    tema('sotet', tk('Sötét'), Moon),
    { id: 'ertesites.elozmeny', nev: tk('Értesítések megjelenítése'), kategoria: tk('Értesítések'), futtat: () => void (f.ertesitesPanel = !f.ertesitesPanel) },
    {
      // E10: a hiba, a mentési gond és a kézzel indított feladat vége a macOS Értesítési központjába is elmegy, ha az app nincs előtérben
      id: 'ertesites.rendszer',
      nev: tk('Rendszerértesítések be/ki'),
      kategoria: tk('Értesítések'),
      elerheto: () => !beallitasok.mentes,
      futtat: () => {
        const be = !f.rendszerErtesites;
        return beallit({ adatvedelem: { ertesitesek: be } }, () => {
          f.rendszerErtesites = be;
          ertesitesek.ertesit({ szint: 'info', cim: f.rendszerErtesites ? t('Rendszerértesítések bekapcsolva') : t('Rendszerértesítések kikapcsolva'), szoveg: f.rendszerErtesites ? t('Hibáról, mentési gondról és a kézzel indított feladat végéről a macOS is szól, ha az app háttérben van.') : t('Csak az appon belüli értesítések maradnak.'), idotartam: 4000 });
        });
      },
    },
    { id: 'ertesites.elvet', nev: tk('Látható értesítések bezárása'), kategoria: tk('Értesítések'), elerheto: () => ertesitesek.lista.length > 0, futtat: () => ertesitesek.mindElvet() },
  ];
  // a rendszerértesítések kötése: a beállítás a felületé, a kattintás alapművelete az előzmény megnyitása
  rendszerErtesites.bekapcsolva = () => f.rendszerErtesites;
  rendszerErtesites.alapMuvelet = () => void (f.ertesitesPanel = true);
  ertesitesek.rendszerKuldo = (e) => void rendszerErtesites.kuld(e);
  const le = reg.regisztralMind(lista);
  return () => {
    le();
    ertesitesek.rendszerKuldo = null;
  };
}
