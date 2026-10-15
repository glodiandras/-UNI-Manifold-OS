// A héj saját parancsai (C07). Minden gomb is ezeket futtatja, így a palettából és billentyűről ugyanaz
// történik. A későbbi modulok a saját parancsaikat ugyanígy, a saját chatjükben regisztrálják.

import { ertesitesek } from './lib/ertesites/ertesites.svelte';
import type { Felulet } from './lib/elrendezes/felulet.svelte';
import { alkalmaz, type Tema } from './lib/elrendezes/tema';
import { csend } from './lib/elrendezes/csend.svelte';
import { rendszerErtesites } from './lib/ertesites/rendszer';
import { regioFokusz, regioLep } from './lib/fokusz/fokusz';
import { ChevronsDownUp, Columns2, Command, FilePlus, FileClock, Monitor, Moon, Network, PanelBottom, PanelLeft, PanelRight, Plus, Rows2, Search, SlidersHorizontal, Sun, Tag, X } from './lib/ikon/ikonok';
import { keresoMegnyit } from './lib/kereses/kereso';
import type { Parancs, Regiszter } from './lib/parancsok/regiszter';

export function alapParancsok(reg: Regiszter, f: Felulet): () => void {
  const m = f.munkaterulet;
  const atfedes = (cel: 'paletta' | 'valto') => {
    f.atfedes = f.atfedes === cel ? null : cel;
  };
  const tema = (t: Tema, nev: string, ikon: Parancs['ikon']): Parancs => ({
    id: `tema.${t}`,
    nev,
    kategoria: 'Téma',
    ikon,
    elerheto: () => f.tema !== t,
    futtat: () => {
      f.tema = t;
      alkalmaz(t);
    },
  });

  const lista: Parancs[] = [
    { id: 'hej.paletta', nev: 'Parancspaletta', kategoria: 'Általános', billentyu: 'Mod+P', ikon: Command, atfedesben: true, palettaban: false, futtat: () => atfedes('paletta') },
    { id: 'hej.valto', nev: 'Fájl megnyitása', kategoria: 'Gyorsváltó', billentyu: 'Mod+O', ikon: Search, atfedesben: true, futtat: () => atfedes('valto') },
    {
      id: 'manifold.vezerlo',
      nev: 'Manifold áttekintő',
      kategoria: 'Manifold',
      billentyu: 'Mod+Shift+M',
      atfedesben: true,
      futtat: () => {
        f.atfedes = null;
        m.megnyitNezet('manifold');
      },
    },
    {
      id: 'kereses.panel',
      nev: 'Keresés a vaultban',
      kategoria: 'Keresés',
      billentyu: 'Mod+Shift+F',
      ikon: Search,
      atfedesben: true,
      futtat: () => (f.atfedes === 'kereso' ? (f.atfedes = null) : keresoMegnyit(f)),
    },
    {
      id: 'cimkek.panel',
      nev: 'Címkék (címkefa)',
      kategoria: 'Keresés',
      ikon: Tag,
      futtat: () => {
        f.atfedes = null;
        f.oldalsav.nyitva = true;
        f.oldalsav.nezet = 'cimkek';
      },
    },
    {
      id: 'tulajdonsagok.kapcsol',
      nev: 'Tulajdonságok megjelenítése / összecsukása',
      kategoria: 'Jegyzet',
      ikon: SlidersHorizontal,
      elerheto: () => !!m.aktivFul?.ut?.toLowerCase().endsWith('.md'),
      futtat: () => void (f.tulajdonsagok.nyitva = !f.tulajdonsagok.nyitva),
    },
    {
      id: 'elozmenyek.megnyit',
      nev: 'Jegyzet előzményei',
      kategoria: 'Jegyzet',
      ikon: FileClock,
      elerheto: () => !!m.aktivFul?.ut?.toLowerCase().endsWith('.md'),
      futtat: () => {
        f.atfedes = null;
        f.jobbPanel.nyitva = true;
        f.jobbPanel.elozmenyek = true;
        queueMicrotask(() => document.querySelector<HTMLElement>('[data-regio="jobb"] [aria-label="A jegyzet pillanatképei"] button')?.focus());
      },
    },
    {
      id: 'fa.megmutat',
      nev: 'Megmutatás a fájlfában',
      kategoria: 'Nézet',
      elerheto: () => !!m.aktivFul?.ut,
      futtat: () => {
        const ut = m.aktivFul?.ut;
        if (ut) f.megmutatFaban(ut);
      },
    },
    // az átfedésként előjött sáv (C38) a kapcsolóra rögzül, nem tűnik el
    { id: 'hej.oldalsav', nev: 'Oldalsáv megjelenítése / elrejtése', kategoria: 'Nézet', billentyu: 'Mod+Alt+1', ikon: PanelLeft, futtat: () => void (f.oldalsav.nyitva = !f.oldalsav.nyitva) },
    { id: 'hej.jobb-panel', nev: 'Jobb panel megjelenítése / elrejtése', kategoria: 'Nézet', billentyu: 'Mod+Alt+2', ikon: PanelRight, futtat: () => void (f.jobbPanel.nyitva = !f.jobbPanel.nyitva) },
    // C25c: a hasonló jegyzetek a (rejtett) jobb panel szakasza — a parancs kinyitja a panelt és a szakaszt
    {
      id: 'kereses.hasonlo',
      nev: 'Hasonló jegyzetek',
      kategoria: 'Keresés',
      ikon: Network,
      futtat: () => {
        f.jobbPanel.nyitva = true;
        f.jobbPanel.hasonlo = true;
      },
    },
    // csend és elérés (C38): a kapcsoló, és minden rejtett elem egy parancs
    { id: 'hej.csend', nev: 'Csend mód be/ki', kategoria: 'Nézet', futtat: () => f.csendKapcsol() },
    { id: 'hej.allapotsor', nev: 'Állapotsor megjelenítése', kategoria: 'Nézet', ikon: PanelBottom, futtat: () => void regioFokusz('allapotsor') },
    {
      id: 'fa.uj-jegyzet',
      nev: 'Új jegyzet a fájlfában',
      kategoria: 'Fájl',
      ikon: FilePlus,
      futtat: () => {
        f.atfedes = null;
        f.oldalsav.nezet = 'fajlok';
        if (!f.oldalsav.nyitva) csend.oldalsavAtfedes = true;
        f.faUjJegyzet = true;
      },
    },
    { id: 'fa.osszecsuk', nev: 'Összes mappa összecsukása', kategoria: 'Fájl', ikon: ChevronsDownUp, futtat: () => void (f.oldalsav.nyitott = []) },
    { id: 'ful.ujranyit', nev: 'Bezárt fül újranyitása', kategoria: 'Fül', billentyu: 'Mod+Shift+T', futtat: () => m.ujranyit() },
    { id: 'navigacio.vissza', nev: 'Vissza az előző jegyzethez', kategoria: 'Navigáció', billentyu: 'Mod+Alt+ArrowLeft', futtat: () => m.navigal(-1) },
    { id: 'navigacio.elore', nev: 'Előre a következő jegyzethez', kategoria: 'Navigáció', billentyu: 'Mod+Alt+ArrowRight', futtat: () => m.navigal(1) },
    { id: 'ful.uj', nev: 'Új fül', kategoria: 'Fül', billentyu: 'Mod+T', ikon: Plus, futtat: () => m.ujFul() },
    { id: 'ful.bezar', nev: 'Fül bezárása', kategoria: 'Fül', billentyu: 'Mod+W', ikon: X, futtat: () => m.bezar() },
    { id: 'ful.kovetkezo', nev: 'Következő fül', kategoria: 'Fül', billentyu: 'Ctrl+Tab', elerheto: () => m.aktivPanel.fulek.length > 1, futtat: () => m.lep(1) },
    { id: 'ful.elozo', nev: 'Előző fül', kategoria: 'Fül', billentyu: 'Ctrl+Shift+Tab', elerheto: () => m.aktivPanel.fulek.length > 1, futtat: () => m.lep(-1) },
    ...Array.from({ length: 9 }, (_, i): Parancs => ({
      id: `ful.n${i + 1}`,
      nev: i === 8 ? 'Utolsó fül' : `${i + 1}. fül`,
      kategoria: 'Fül',
      billentyu: `Mod+${i + 1}`,
      palettaban: false,
      futtat: () => m.nedik(i + 1),
    })),
    { id: 'panel.oszt-jobbra', nev: 'Osztás jobbra', kategoria: 'Panel', billentyu: 'Mod+Shift+2', ikon: Columns2, futtat: () => m.oszt('sor') },
    { id: 'panel.oszt-le', nev: 'Osztás lefelé', kategoria: 'Panel', billentyu: 'Mod+Alt+ArrowDown', ikon: Rows2, szerkesztoNyer: true, futtat: () => m.oszt('oszlop') }, // a szerkesztőben a ⌥⌘↓ a CM addCursorBelow-ja
    { id: 'panel.kovetkezo', nev: 'Következő panel', kategoria: 'Panel', elerheto: () => m.panelek().length > 1, futtat: () => m.panelLep(1) },
    { id: 'panel.elozo', nev: 'Előző panel', kategoria: 'Panel', elerheto: () => m.panelek().length > 1, futtat: () => m.panelLep(-1) },
    { id: 'fokusz.kovetkezo-regio', nev: 'Következő régió', kategoria: 'Fókusz', billentyu: 'F6', palettaban: false, futtat: () => regioLep(1) },
    { id: 'fokusz.elozo-regio', nev: 'Előző régió', kategoria: 'Fókusz', billentyu: 'Shift+F6', palettaban: false, futtat: () => regioLep(-1) },
    tema('rendszer', 'A rendszer szerint', Monitor),
    tema('vilagos', 'Világos', Sun),
    tema('sotet', 'Sötét', Moon),
    { id: 'ertesites.elozmeny', nev: 'Értesítések megjelenítése', kategoria: 'Értesítések', futtat: () => void (f.ertesitesPanel = !f.ertesitesPanel) },
    {
      // E10: a hiba, a mentési gond és a kézzel indított feladat vége a macOS Értesítési központjába is elmegy, ha az app nincs előtérben
      id: 'ertesites.rendszer',
      nev: 'Rendszerértesítések be/ki',
      kategoria: 'Értesítések',
      futtat: () => {
        f.rendszerErtesites = !f.rendszerErtesites;
        ertesitesek.ertesit({ szint: 'info', cim: f.rendszerErtesites ? 'Rendszerértesítések bekapcsolva' : 'Rendszerértesítések kikapcsolva', szoveg: f.rendszerErtesites ? 'Hibáról, mentési gondról és a kézzel indított feladat végéről a macOS is szól, ha az app háttérben van.' : 'Csak az appon belüli értesítések maradnak.', idotartam: 4000 });
      },
    },
    { id: 'ertesites.elvet', nev: 'Látható értesítések bezárása', kategoria: 'Értesítések', elerheto: () => ertesitesek.lista.length > 0, futtat: () => ertesitesek.mindElvet() },
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
