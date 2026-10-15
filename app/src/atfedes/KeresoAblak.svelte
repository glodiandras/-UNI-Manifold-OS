<!--
  A nagy keresőablak (E3, ⇧⌘F): középre nyíló, teljes magasságú átfedés a core keresőnyelvével (szó, "kifejezés", OR,
  -tagadás, zárójel, path:, file:, tag:, line:, /regex/). Felül a mező, az állapot és a „Jelentés szerint” kapcsoló;
  alatta fájlonként egy kártya: név + egyezésszám, mappa-út, legfeljebb négy kiemelt kivágás (sorszám / PDF-lap /
  videó-időkód). Az adatréteg a `vaultKereses` (250 ms késleltetés, az elavult válasz eldobása; PDF-szöveg C25c,
  hibrid C25b). A mező `combobox`, a lista `listbox` (a kártya `group`, a fejléce és a kivágásai `option`;
  `aria-activedescendant`): a fókusz a mezőben marad. ↑↓ lép (kártya, kivágás, kártya…), ↵ a találatra ugorva nyit,
  ⌘↵ új fülben, ⌥⌘↵ osztásban, ⌥↵ linket szúr az aktív szerkesztőbe (a core `linkcel`-je, L42), Tab a fájlon belüli
  keresésre vált (CodeMirror), ⌘G a kivágásokat ki-be kapcsolja (tartós), Esc bezár. A kártyák fokozatosan rajzolódnak
  (30-asával, a görgetéssel és a lépkedéssel), így a 200 találat sem akasztja a rajzot.
-->
<script lang="ts">
  import { openSearchPanel, SearchQuery, setSearchQuery } from '@codemirror/search';
  import { onMount, tick } from 'svelte';
  import { Search, X } from '../lib/ikon/ikonok';
  import Ikon from '../lib/ikon/Ikon.svelte';
  import { ertesitesek } from '../lib/ertesites/ertesites.svelte';
  import { kornyezet } from '../lib/kornyezet';
  import { keresoSzavak, szoKiemeles } from '../lib/kereses/kereso';
  import { fajlNev, mappa } from '../lib/vault/fajlok.svelte';
  import { linkek } from '../lib/vault/linkek.svelte';
  import {
    KERESES_LIMIT,
    MIN_HOSSZ,
    darabok,
    helyCimke,
    pdfFolyamatban,
    sorokraEgyesit,
    talalatCel,
    utf16Oszlop,
    vaultKereses as allapot,
    type KeresesFajl,
    type PdfSzovegAllapot,
    type SorTalalat,
  } from '../lib/kereses/vaultKereses.svelte';
  import Atfedes from '../lib/ui/Atfedes.svelte';
  import Billentyu from '../lib/ui/Billentyu.svelte';
  import JegyzetIkon from '../lib/ui/JegyzetIkon.svelte';
  import { nyitasMod, type NyitasMod } from '../szerkeszto/linkek/navigacio';
  import { szerkesztok } from '../szerkeszto/szerkesztok.svelte';

  /** Egy kártyán legfeljebb ennyi kivágás sor látszik (a többit a „+N további sor” jelzi). */
  const KIVAGAS_MAX = 4;
  /** A kártyák fokozatos rajza: ennyit rajzolunk elsőre, és ennyivel többet, ha a lista vége közeledik. */
  const LEPES = 30;

  const { felulet, fajlok, kapcsolat } = kornyezet();
  const id = $props.id();

  let mezo: HTMLInputElement | undefined = $state();
  let lista: HTMLElement | undefined = $state();
  let aktiv = $state(0);
  let latszik = $state(LEPES);

  type Elem = { kulcs: string; fajl: KeresesFajl; hely?: SorTalalat };

  const kivagasok = $derived(felulet.kereso.kivagasok);
  const szavak = $derived(keresoSzavak(allapot.q));
  const talalatok = $derived(allapot.eredmeny?.talalatok ?? []);
  const kartyak = $derived(talalatok.slice(0, latszik));

  /** A fájlok kártyái: a kivágás sorok az azonos sorú egyezések egyesítésével; a lapos sorrend a billentyűzeté. */
  const modell = $derived(
    kartyak.map((f) => {
      const sorok = sorokraEgyesit(f);
      return { fajl: f, sorok: sorok.slice(0, KIVAGAS_MAX), tobb: Math.max(0, sorok.length - KIVAGAS_MAX) };
    }),
  );

  const elemek = $derived.by<Elem[]>(() => {
    const ki: Elem[] = [];
    for (const k of modell) {
      ki.push({ kulcs: `f:${k.fajl.ut}`, fajl: k.fajl });
      if (kivagasok) for (const h of k.sorok) ki.push({ kulcs: `h:${k.fajl.ut}:${h.sor}`, fajl: k.fajl, hely: h });
    }
    return ki;
  });
  const sorszamok = $derived(new Map(elemek.map((e, i) => [e.kulcs, i])));
  const aktivElem = $derived<Elem | undefined>(elemek[aktiv]);

  $effect.pre(() => {
    void allapot.eredmeny;
    aktiv = 0;
    latszik = LEPES;
  });

  // az aktív elem látható marad (a kártya fejlécénél az egész kártya tetejéig)
  $effect(() => {
    const i = aktiv;
    void tick().then(() => document.getElementById(`${id}-${i}`)?.scrollIntoView?.({ block: 'nearest' }));
  });

  onMount(() => {
    const le = kapcsolat.figyel('index', () => allapot.indexKesz());
    // C25c: a PDF-szöveg kinyerésének haladása (a core az `index` eseményt nem ismétli: arra a fa és a gráf is újratöltene)
    const le2 = kapcsolat.figyel('pdf_szoveg', (e) => (allapot.pdfSzoveg = e as unknown as PdfSzovegAllapot));
    return () => (le(), le2());
  });

  const pdfFolyamat = $derived(pdfFolyamatban(allapot.pdfSzoveg ?? fajlok.index?.pdf_szoveg));
  const cap = $derived(!!allapot.eredmeny && allapot.eredmeny.osszes > allapot.eredmeny.talalatok.length);
  const tipusOf = (ut: string) => fajlok.info(ut)?.tipus;

  function bezar() {
    felulet.atfedes = null;
  }

  function fejSor(f: KeresesFajl) {
    const ut = f.tipus === 'felirat' && f.media ? f.media : f.ut; // a felirat-találat fejléce a videó (oda nyit)
    return { ut, nev: fajlNev(ut), mappa: mappa(ut), felirat: f.tipus === 'felirat' };
  }

  /** A kártya egyezésszáma: a szó szerinti találatok; a jelentés szerinti (hibrid) találatnak nincs. */
  const egyezes = (f: KeresesFajl) => f.talalatok.length;

  function megnyit(f: KeresesFajl, h: SorTalalat | undefined, mod: NyitasMod) {
    bezar();
    const cel = talalatCel(f, h);
    if (f.tipus) {
      // C25c: a PDF az oldalára, a felirat a médiája másodpercére — a horgony a fül nézetéé (mint a `[[x.pdf#page=N]]` linknél)
      felulet.munkaterulet.megnyit(cel.ut, mod);
      const ful = felulet.munkaterulet.aktivFul;
      if (cel.horgony && ful) ful.nezet = { ...(ful.nezet ?? {}), horgony: cel.horgony };
      return;
    }
    felulet.munkaterulet.megnyit(f.ut, mod);
    const elso = h ?? sorokraEgyesit(f)[0]; // a kártyán a ↵ az első egyezésre ugrik
    if (elso) szerkesztok.ugras(f.ut, elso.sor, utf16Oszlop(elso.szoveg, elso.oszlop));
    else if (f.darab) szerkesztok.ugras(f.ut, f.darab.sor_kezd, 0); // csak jelentés szerinti találat
  }

  /** ⌥↵: link a találatra a legutóbb aktív szerkesztő kurzorához (a beírt cél a core `linkcel`-éből, L42). */
  async function linkBeszur(f: KeresesFajl, h: SorTalalat | undefined) {
    const p = szerkesztok.aktiv ?? szerkesztok.utolso;
    if (!p || p.mod() === 'olvaso' || !p.nezet()) {
      ertesitesek.ertesit({ szint: 'figyelmeztetes', cim: 'Nincs hova linket szúrni', szoveg: 'Nyiss meg egy jegyzetet a szerkesztőben.', idotartam: 4000 });
      return;
    }
    const cel = talalatCel(f, h);
    try {
      let szoveg = await linkek.linkCel(cel.ut, p.ut);
      if (cel.horgony) szoveg += `#${cel.horgony}`;
      const v = p.nezet();
      if (!v) return;
      bezar();
      v.dispatch(v.state.update(v.state.replaceSelection(`[[${szoveg}]]`), { userEvent: 'input.link', scrollIntoView: true }));
      await tick();
      v.focus();
    } catch (e) {
      ertesitesek.ertesit({ szint: 'hiba', cim: 'A link nem szúrható be', szoveg: e instanceof Error ? e.message : String(e) });
    }
  }

  /** Tab: a keresés a jegyzeten belülre vált — a kijelölt kártya jegyzetében (megnyitva), különben az aktívban. */
  async function fajlonBelul() {
    const kartya = aktivElem?.fajl;
    const ut = kartya && !kartya.tipus ? kartya.ut : szerkesztok.aktiv?.ut;
    if (!ut) return;
    const q = szavak.join(' ');
    bezar();
    if (szerkesztok.aktiv?.ut !== ut) felulet.munkaterulet.megnyit(ut, 'aktiv');
    for (let i = 0; i < 60 && szerkesztok.aktiv?.ut !== ut; i++) await new Promise((r) => setTimeout(r, 25));
    const v = szerkesztok.aktiv?.ut === ut ? szerkesztok.aktiv.nezet() : null;
    if (!v) return;
    openSearchPanel(v);
    if (q) v.dispatch({ effects: setSearchQuery.of(new SearchQuery({ search: q })) });
  }

  function lep(d: number) {
    const n = elemek.length;
    if (!n) return;
    if (d > 0 && aktiv === n - 1) {
      if (latszik < talalatok.length) {
        latszik += LEPES; // a lista vége közeledik: tovább rajzolunk
        aktiv += 1;
      } else aktiv = 0;
    } else if (d < 0 && aktiv === 0) {
      latszik = talalatok.length; // az elejéről visszafelé az utolsóra: az egész lista kell
      void tick().then(() => (aktiv = elemek.length - 1));
    } else aktiv += d;
  }

  function gorges() {
    if (lista && latszik < talalatok.length && lista.scrollTop + lista.clientHeight > lista.scrollHeight - 400) latszik += LEPES;
  }

  function billentyu(e: KeyboardEvent) {
    if (e.isComposing) return;
    const ctrl = e.ctrlKey && !e.metaKey && !e.altKey;
    if (e.key === 'ArrowDown' || (ctrl && e.key === 'n')) lep(1);
    else if (e.key === 'ArrowUp' || (ctrl && e.key === 'p')) lep(-1);
    else if (e.key === 'PageDown') aktiv = Math.min(elemek.length - 1, aktiv + 8);
    else if (e.key === 'PageUp') aktiv = Math.max(0, aktiv - 8);
    else if (e.key === 'Enter' && !e.shiftKey) {
      const s = aktivElem;
      if (!s || allapot.folyamat || allapot.eredmeny?.q !== allapot.q.trim()) allapot.beallit(allapot.q, true);
      else if (e.altKey && !e.metaKey) void linkBeszur(s.fajl, s.hely);
      else megnyit(s.fajl, s.hely, nyitasMod(e));
    } else if (e.key === 'Tab' && !e.shiftKey) void fajlonBelul();
    else if (e.key === 'Tab') {
      /* a fókusz a mezőben marad */
    } else if ((e.metaKey || e.ctrlKey) && !e.altKey && !e.shiftKey && e.key.toLowerCase() === 'g') felulet.kereso.kivagasok = !kivagasok;
    else return;
    e.preventDefault();
    e.stopPropagation();
  }

  function kattint(e: MouseEvent, f: KeresesFajl, h?: SorTalalat) {
    megnyit(f, h, nyitasMod(e));
  }
</script>

{#snippet kiemelt(szoveg: string)}
  {#each szoKiemeles(szoveg, szavak) as d, i (i)}{#if d.jelolt}<mark>{d.t}</mark>{:else}{d.t}{/if}{/each}
{/snippet}

<Atfedes cimke="Keresés a vaultban" nev="kereso" szeles onbezar={bezar}>
  <div class="kereso">
    <div class="mezo-sor">
      <span class="lupe"><Ikon ikon={Search} meret={16} /></span>
      <input
        bind:this={mezo}
        class="mezo"
        type="text"
        role="combobox"
        aria-expanded={elemek.length > 0}
        aria-controls="{id}-lista"
        aria-autocomplete="list"
        aria-activedescendant={elemek.length ? `${id}-${aktiv}` : undefined}
        aria-label="Keresés"
        aria-describedby="{id}-allapot"
        placeholder="Keresés a vaultban…"
        spellcheck="false"
        autocomplete="off"
        autocapitalize="off"
        value={allapot.q}
        oninput={(e) => allapot.beallit(e.currentTarget.value)}
        onkeydown={billentyu}
        data-autofocus
        {@attach (el) => {
          el.focus();
          el.select();
        }}
      />
      {#if allapot.q}
        <button type="button" class="torles" aria-label="Keresés törlése" title="Keresés törlése" onclick={() => (allapot.beallit('', true), mezo?.focus())}>
          <Ikon ikon={X} meret={14} />
        </button>
      {/if}
      <span id="{id}-allapot" class="allapot" role="status" aria-live="polite">
        {#if allapot.jelentes && allapot.betoltes && !allapot.hiba}
          A jelentés szerinti rész betöltés alatt — addig a szó szerinti találatok látszanak.
        {:else if allapot.hiba}
          <!-- a hibát külön, rendelkező régióban mutatjuk -->
        {:else if allapot.rovid}
          Legalább {MIN_HOSSZ} karakter kell a kereséshez.
        {:else if allapot.indexEpul}
          Az index még épül — a keresés hamarosan elérhető.
        {:else if allapot.folyamat && !allapot.eredmeny}
          Keresés…
        {:else if allapot.eredmeny}
          {#if pdfFolyamat}PDF-szöveg indexelése: {pdfFolyamat.kesz}/{pdfFolyamat.osszes}.{' '}{/if}
          {#if allapot.eredmeny.osszes === 0}
            Nincs találat: „{allapot.eredmeny.q}”.
          {:else}
            {allapot.eredmeny.legalabb ? 'legalább ' : ''}{allapot.eredmeny.osszes} találó fájl{cap ? ` (az első ${KERESES_LIMIT} látszik)` : ''}
          {/if}
        {/if}
      </span>
      <label class="jelentes" title="Szó szerinti és jelentés szerinti (vektoros) találatok együtt, rerankerrel (C25b)">
        <input type="checkbox" checked={allapot.jelentes} onchange={(e) => allapot.jelentesValt(e.currentTarget.checked)} />
        Jelentés szerint
      </label>
    </div>

    {#if allapot.hiba}
      <p class="hiba" role="alert">{allapot.hiba}</p>
    {/if}

    <div class="eredmenyek gorgeto" bind:this={lista} onscroll={gorges}>
      {#if !allapot.q.trim()}
        <div class="sugo">
          <p class="sugo-cim">Keresőnyelv</p>
          <dl>
            <dt>szó szó</dt><dd>mindkettő szerepel (ékezet- és kis-nagybetű-független)</dd>
            <dt>"pontos kifejezés"</dt><dd>egymás után, ebben a sorrendben</dd>
            <dt>a OR b</dt><dd>bármelyik</dd>
            <dt>-szó</dt><dd>ne szerepeljen</dd>
            <dt>(a OR b) c</dt><dd>csoportosítás zárójellel</dd>
            <dt>path:mappa</dt><dd>az útban; <code>file:név</code> a fájlnévben</dd>
            <dt>tag:#címke</dt><dd>címkével (az alcímkék is)</dd>
            <dt>line:(a b)</dt><dd>ugyanabban a sorban</dd>
            <dt>/regex/</dt><dd>reguláris kifejezés a tartalomban</dd>
          </dl>
        </div>
      {:else if elemek.length}
        <div id="{id}-lista" class="lista" role="listbox" aria-label="Találatok">
          {#each modell as k (k.fajl.ut)}
            {@const fej = fejSor(k.fajl)}
            {@const fi = sorszamok.get(`f:${k.fajl.ut}`) ?? 0}
            <div class="kartya" role="group" aria-label={fej.nev}>
              <!-- A billentyűzet a combobox mezőjében él (aria-activedescendant), a sor csak egérrel kattintható. -->
              <!-- svelte-ignore a11y_click_events_have_key_events -->
              <div
                id="{id}-{fi}"
                class="fejlec"
                class:aktiv={fi === aktiv}
                role="option"
                tabindex="-1"
                aria-selected={fi === aktiv}
                title={k.fajl.ut}
                onpointermove={() => (aktiv = fi)}
                onmousedown={(e) => e.preventDefault()}
                onclick={(e) => kattint(e, k.fajl)}
              >
                <span class="ikon"><JegyzetIkon ut={fej.ut} tipus={tipusOf(fej.ut)} meret={14} /></span>
                <span class="nev">{@render kiemelt(fej.nev)}</span>
                {#if egyezes(k.fajl)}<span class="db">{egyezes(k.fajl)} egyezés</span>{:else if k.fajl.darab}<span class="db">jelentés szerint</span>{/if}
                {#if fej.felirat}<span class="db">átirat</span>{/if}
              </div>
              {#if fej.mappa}<div class="mappa">{@render kiemelt(fej.mappa)}</div>{/if}
              {#if kivagasok}
                {#each k.sorok as h (h.sor)}
                  {@const hi = sorszamok.get(`h:${k.fajl.ut}:${h.sor}`) ?? 0}
                  <!-- svelte-ignore a11y_click_events_have_key_events -->
                  <div
                    id="{id}-{hi}"
                    class="kivagas"
                    class:aktiv={hi === aktiv}
                    role="option"
                    tabindex="-1"
                    aria-selected={hi === aktiv}
                    title={`${k.fajl.ut}:${helyCimke(h)}`}
                    onpointermove={() => (aktiv = hi)}
                    onmousedown={(e) => e.preventDefault()}
                    onclick={(e) => kattint(e, k.fajl, h)}
                  >
                    <span class="sorszam">{helyCimke(h)}</span>
                    <span class="sor">{#each darabok(h, 60, 150) as d, di (di)}{#if d.jelolt}<mark>{d.t}</mark>{:else}{d.t}{/if}{/each}</span>
                  </div>
                {/each}
                {#if k.tobb}<div class="tobb">+{k.tobb} további sor</div>{/if}
              {/if}
            </div>
          {/each}
        </div>
      {/if}
    </div>

    <div class="lablec">
      <span><kbd>↑↓</kbd> lépés</span>
      <span><kbd>↵</kbd> megnyitás</span>
      <span><Billentyu akkord="Mod+Enter" /> új fülben</span>
      <span><Billentyu akkord="Mod+Alt+Enter" /> osztásban</span>
      <span><kbd>Tab</kbd> keresés a fájlban</span>
      <span><Billentyu akkord="Mod+G" /> kivágások {kivagasok ? 'elrejtése' : 'mutatása'}</span>
      <span><Billentyu akkord="Alt+Enter" /> link beszúrása</span>
      <span><kbd>esc</kbd> bezárás</span>
    </div>
  </div>
</Atfedes>

<style>
  .kereso {
    display: flex;
    flex-direction: column;
    flex: 1;
    min-height: 0;
  }

  .mezo-sor {
    flex: none;
    display: flex;
    align-items: center;
    gap: var(--t-3);
    min-height: var(--magassag-mezo);
    padding: 0 var(--t-5);
    border-bottom: var(--keret-vastag) solid var(--keret);
  }

  .lupe {
    flex: none;
    display: flex;
    color: var(--szoveg-halvany);
  }

  .mezo {
    flex: 1;
    min-width: 0;
    height: var(--magassag-mezo);
    border: 0;
    background: transparent;
    color: var(--szoveg);
    font-size: var(--betu-h4);
    line-height: var(--sor-mezo);
    user-select: text;
    -webkit-user-select: text;
  }

  .mezo::placeholder {
    color: var(--szoveg-halvany);
  }

  .mezo:focus-visible {
    outline: none;
  }

  .torles {
    flex: none;
    display: flex;
    align-items: center;
    justify-content: center;
    width: var(--magassag-gomb-kicsi);
    height: var(--magassag-gomb-kicsi);
    border-radius: var(--kerekites-kicsi);
    color: var(--szoveg-halvany);
  }

  .torles:hover {
    background: var(--hatter-hover);
    color: var(--szoveg);
  }

  .allapot {
    flex: none;
    max-width: 40%;
    font-size: var(--betu-ui);
    line-height: var(--sor-ui);
    color: var(--szoveg-halvany);
    text-align: right;
  }

  .jelentes {
    flex: none;
    display: flex;
    align-items: center;
    gap: var(--t-2);
    font-size: var(--betu-ui);
    color: var(--szoveg-masodlagos);
    cursor: pointer;
  }

  .hiba {
    flex: none;
    margin: var(--t-2) var(--t-2) 0;
    padding: var(--t-2) var(--t-3);
    border-radius: var(--kerekites);
    background: var(--hiba-hatter);
    color: var(--hiba);
    font-size: var(--betu-ui);
    line-height: var(--sor-ui);
    overflow-wrap: anywhere;
  }

  .eredmenyek {
    flex: 1;
    min-height: 0;
  }

  .lista {
    display: flex;
    flex-direction: column;
    gap: var(--t-1);
    padding: var(--t-2);
  }

  .kartya {
    display: flex;
    flex-direction: column;
    gap: 2px;
    padding: var(--t-2) 0;
    border-radius: var(--kerekites);
    /* a nem látszó kártya rajza elmarad: a 200 találat sem akasztja a görgetést */
    content-visibility: auto;
    contain-intrinsic-size: auto 96px;
  }

  .fejlec,
  .kivagas {
    cursor: pointer;
  }

  .fejlec {
    display: flex;
    align-items: baseline;
    gap: var(--t-2);
    padding: 0 var(--t-3);
    color: var(--szoveg);
  }

  .fejlec.aktiv {
    background: var(--hatter-kijelolt);
    border-radius: var(--kerekites);
    padding-top: var(--t-1);
    padding-bottom: var(--t-1);
  }

  .ikon {
    flex: none;
    align-self: center;
    color: var(--szoveg-halvany);
  }

  .nev {
    min-width: 0;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    font-size: var(--betu-mezo);
    line-height: var(--sor-mezo);
    font-weight: var(--suly-felkover);
  }

  .db {
    flex: none;
    font-size: var(--betu-ui);
    line-height: var(--sor-ui);
    color: var(--szoveg-halvany);
  }

  .mappa {
    padding: 0 var(--t-3);
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    font-size: var(--betu-ui);
    line-height: var(--sor-ui);
    color: var(--szoveg-halvany);
  }

  .kivagas {
    display: flex;
    gap: var(--t-2);
    padding: 0 var(--t-3);
    border-radius: var(--kerekites);
    color: var(--szoveg-masodlagos);
  }

  .kivagas.aktiv {
    background: var(--hatter-kijelolt);
  }

  .sorszam {
    flex: none;
    min-width: 4ch;
    text-align: right;
    font-size: var(--betu-ui);
    line-height: var(--sor-ui);
    color: var(--szoveg-halvany);
    font-variant-numeric: tabular-nums;
  }

  .sor {
    min-width: 0;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    font-size: var(--betu-ui);
    line-height: var(--sor-ui);
  }

  .tobb {
    padding: 0 var(--t-3) 0 calc(var(--t-3) + 4ch + var(--t-2));
    font-size: var(--betu-kicsi);
    line-height: var(--sor-kicsi);
    color: var(--szoveg-halvany);
  }

  mark {
    padding: 0 1px;
    border-radius: var(--kerekites-jel);
    background: var(--jeloles-hatter);
    color: inherit;
  }

  .sugo {
    padding: var(--t-4) var(--t-5);
    font-size: var(--betu-ui);
    line-height: var(--sor-ui);
    color: var(--szoveg-masodlagos);
  }

  .sugo-cim {
    margin: 0 0 var(--t-2);
    font-weight: var(--suly-felkover);
    color: var(--szoveg-halvany);
  }

  dl {
    display: grid;
    grid-template-columns: max-content 1fr;
    gap: var(--t-1) var(--t-4);
    margin: 0;
  }

  dt {
    font-family: var(--betu-mono);
    color: var(--szoveg);
  }

  dd {
    margin: 0;
  }

  code {
    font-family: var(--betu-mono);
  }

  .lablec {
    flex: none;
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: var(--t-1) var(--t-5);
    min-height: var(--magassag-lista-sor);
    padding: var(--t-2) var(--t-5);
    border-top: var(--keret-vastag) solid var(--keret);
    background: var(--hatter-oldalsav);
    color: var(--szoveg-halvany);
    font-size: var(--betu-kicsi);
    line-height: var(--sor-kicsi);
  }

  kbd {
    color: var(--szoveg-masodlagos);
  }
</style>
