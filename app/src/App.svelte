<!-- A felület gyökere: a környezet, a parancsok, a billentyűkezelő, a WS és a tartós állapot. -->
<script lang="ts">
  import { onMount, untrack } from 'svelte';
  import { alapParancsok } from './alapParancsok';
  import { aktivitasFigyelo } from './lib/core/aktivitas';
  import { CoreKapcsolat } from './lib/core/ws.svelte';
  import { csendTelepit } from './lib/elrendezes/csend.svelte';
  import { Mento, betoltesPotol, type Felulet } from './lib/elrendezes/felulet.svelte';
  import { nezetek } from './lib/elrendezes/nezetek.svelte';
  import { fokuszVisszaallit, utolsoFokuszKovet } from './lib/fokusz/fokusz';
  import { grafTelepit } from './graf';
  import { maTelepit } from './ma';
  import { hidTelepit } from './lib/core/hid';
  import { dolgozatTelepit } from './dolgozat';
  import { kornyezetBeallit } from './lib/kornyezet';
  import { telepit } from './lib/parancsok/kezelo';
  import { regiszter } from './lib/parancsok/regiszter';
  import { cimkek } from './lib/vault/cimkek.svelte';
  import { VaultFajlok } from './lib/vault/fajlok.svelte';
  import { grafAdat } from './lib/vault/graf.svelte';
  import { ikonok } from './lib/vault/ikonok.svelte';
  import { bazisTelepit } from './bazis';
  import { kvizTelepit } from './kviz';
  import { canvasTelepit } from './canvas';
  import { trackerTelepit } from './tracker';
  import { trackerKliens } from './lib/tracker/kliens.svelte';
  import { vezerloTelepit } from './vezerlo';
  import { naptarTelepit } from './naptar';
  import { naptarHid } from './lib/naptar/hid.svelte';
  import { mediaTelepit } from './media';
  import { kodTelepit } from './kod';
  import { matekTelepit } from './matek';
  import { kartyaTelepit } from './kartya';
  import { osszefoglalasTelepit } from './osszefoglalas';
  import { kilepesMentes, mentetlenSzovegek, szerkesztesLezar, szerkesztoTelepit } from './szerkeszto';
  import { szerkesztok } from './szerkeszto/szerkesztok.svelte';
  import Hej from './hej/Hej.svelte';
  import Helyorzo from './hej/nezetek/Helyorzo.svelte';
  import UjFul from './hej/nezetek/UjFul.svelte';

  const props: { felulet: Felulet } = $props();
  const felulet = untrack(() => props.felulet); // egyszer adódik át, nem változik

  const kapcsolat = new CoreKapcsolat();
  const fajlok = new VaultFajlok();
  const kornyezetObj = kornyezetBeallit({ felulet, fajlok, kapcsolat });

  // az átnevezés közben „eltűnt” (régi) út nem üríti ki a füleket: a `vault_atnevezes` esemény átcímzi őket
  fajlok.eltuntek = (utak) => felulet.munkaterulet.eltuntek(new Set([...utak].filter((u) => !szerkesztok.atnevezesAlatt.has(u))));
  regiszter.futasUtan = (id) => felulet.parancsFutott(id);

  // Az alapnézetek a mount előtt, hogy az első festés már a végleges tartalmat mutassa.
  const nezetekLe = [
    nezetek.regisztral({ id: 'alap.uj-ful', illeszkedik: (f) => f.ut === null, komponens: UjFul, prioritas: -100 }),
    nezetek.regisztral({ id: 'alap.helyorzo', illeszkedik: () => true, komponens: Helyorzo, prioritas: -1000 }),
    // a szerkesztő (C08): a `.md` nézet, a parancsai és a WS-figyelése
    szerkesztoTelepit(regiszter, kapcsolat, felulet, fajlok),
    // az adatbázis-nézetek (C12): a `.base` fül, a blokk és a beágyazás
    bazisTelepit(kornyezetObj),
    // a kvíz (C22a, C22b): a kvízjegyzet beágyazása kitölthető blokk; a „Kvíz ebből” (a C17 helyőrzője helyett)
    kvizTelepit(regiszter, felulet),
    // a gráfnézet (C13): a nézet és a parancsai
    grafTelepit(regiszter, felulet),
    // a napi jegyzet, a sablonok és a „Ma” oldal (C15)
    maTelepit(regiszter, felulet, kapcsolat),
    // a dolgozat-oldal (C28a): témánkénti felkészültség, napi terv
    dolgozatTelepit(regiszter, felulet, kapcsolat),
    // a canvas (C14): a `.canvas` fül, a parancsai és a beágyazás
    canvasTelepit(regiszter, felulet, fajlok),
    // a PDF-olvasó és a lejátszó (C16): a fülek, a PDF-beágyazás, a ⇧⌘I és a parancsok
    mediaTelepit(regiszter, kapcsolat),
    // a C++ munkafelület (C36a-UI): a `.cpp` fül, a ⌘R és az eredménypanel, a `![[x.cpp]]` beágyazás, az új feladat
    kodTelepit(regiszter, felulet, kapcsolat),
    // a tracker (C27): az aktív idő és a parancsok gyűjtése, a Statisztika és a Használat nézet-fül
    trackerTelepit(regiszter, felulet),
    // a matek-motor (C24b): a levezetés-ellenőrzés (margójel) és a „Megoldás” (feladat), a C17 helyőrzői helyett
    matekTelepit(regiszter, felulet),
    // a kártyák (C23b): a kísérőjegyzet beágyazott paklija, a „Kártyák ebből” (a C17 helyőrzője helyett) és a „Mai ismétlés”
    kartyaTelepit(regiszter, felulet),
    // az összefoglaló (C26b): a kísérőjegyzet beágyazott megjelenítése, az „Összefoglalás” (a C17 helyőrzője helyett), a kontextus-csomag
    osszefoglalasTelepit(regiszter, felulet),
  ];

  // Tartós állapot: minden változás után 500 ms-mal, a lap elhagyásakor azonnal.
  // Ha induláskor a mentett állapot nem jött meg, a mentő zárolva: az alapelrendezés nem írhatja felül a `felulet.json`-t.
  const mento = new Mento();
  mento.alap(JSON.stringify(felulet.sorosit()));
  if (!felulet.betoltve) mento.zarol();
  $effect(() => {
    mento.utemez(JSON.stringify(felulet.sorosit()));
  });

  onMount(() => {
    const le = [
      alapParancsok(regiszter, felulet),
      ...nezetekLe,
      telepit(regiszter),
      aktivitasFigyelo(),
      // csend és elérés (C38): a mód, a gépeléskor halványuló króm, a rejtett sávok előhívása
      csendTelepit(felulet),
      utolsoFokuszKovet(),
      fajlok.figyel(kapcsolat),
      ikonok.figyel(kapcsolat),
      cimkek.figyel(kapcsolat),
      grafAdat.figyel(kapcsolat),
      // a vezérlő (C17): a feladatsor élő nézete, a feladat végének értesítése, a parancsok
      vezerloTelepit(regiszter, felulet, kapcsolat),
      // a naptár és az emlékeztetők (C29): állapot, értesítések, az engedély-híd válasza, parancsok
      naptarTelepit(regiszter, felulet, kapcsolat),
      // a bukott induló betöltés pótlása, amikor a core él (minden `hello`-n, amíg nem sikerül)
      kapcsolat.figyel('hello', () => void betoltesPotol(felulet, mento)),
    ];
    kapcsolat.indit();
    void fajlok.frissit();
    // a lap elhagyása vagy az ablak elrejtése: a felület állapota azonnal, a szerkesztés lezárul (pillanatkép)
    const elhagy = () => {
      void mento.ki(true);
      if (document.visibilityState === 'hidden') void szerkesztesLezar();
    };
    window.addEventListener('pagehide', elhagy);
    document.addEventListener('visibilitychange', elhagy);
    // A héj hídja (`window.manifold`): a kilépéskor a `mentes()` jelentését megvárja (a WKWebView kilépéskor nem küld
    // pagehide-ot), és mentetlen jegyzetnél kérdez, mielőtt leállítja a core-t (H6). A szerződése: `lib/core/hid.ts`.
    const hidLe = hidTelepit({
      parancsFuttat: (id) => regiszter.futtat(id, 'hej'),
      fokuszVisszaallit: () => fokuszVisszaallit(),
      naptarFogad: (v) => naptarHid.fogad(v),
      mentesElokeszit: () => mento.utemez(JSON.stringify(felulet.sorosit())),
      mentesKi: () => mento.ki(true),
      kilepesMentes: () => kilepesMentes(),
      trackerKi: () => trackerKliens.kuldKi(),
      mentetlenSzovegek: () => mentetlenSzovegek(),
    });
    return () => {
      le.forEach((f) => f());
      hidLe();
      kapcsolat.leallit();
      window.removeEventListener('pagehide', elhagy);
      document.removeEventListener('visibilitychange', elhagy);
    };
  });
</script>

<Hej />
