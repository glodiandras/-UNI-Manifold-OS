<!--
  Tulajdonság-szerkesztő a frontmatter fölött (C11b): szöveg, szám, dátum, jelölő, lista és link mezők, a Status
  választólistával. Az írás a nyitott dokumentumon át megy (a core csak a frontmatter-blokk új szövegét számolja),
  a frontmatter bájthű marad. A vault sémáját sértő értéket a mező alatt jelzi, és csak „Mégis beírom” után írja be;
  a hiba szintűt (érvénytelen érték, formai hibás frontmatter) nem. A panel mindhárom módban (Live Preview, Forrás,
  Olvasó) ugyanaz, összecsukható (tartós: `felulet.tulajdonsagok`).
  Gépelés közben a mezők javasolnak (`JavaslatMezo`, `javaslat.ts`): a címke-mező a vault címkéit és a séma értékkészletét,
  a link-mező (Source, NN, Canvas) a vault fájljait (a beírt cél a core link-céljából), a Status az engedett értékeket
  (fókuszra nyíló listaként), a többi szöveges mező a kulcs vaultban használt értékeit, az új tulajdonság neve a séma- és a
  vault-kulcsokat. A javaslat csak bevitel: a beírás ugyanazon a `modosit`-on át megy, a séma-sértő érték megerősítéssel.
-->
<script lang="ts">
  import type { Text } from '@codemirror/state';
  import { onMount, untrack } from 'svelte';
  import { csend } from '../../lib/elrendezes/csend.svelte';
  import Ikon from '../../lib/ikon/Ikon.svelte';
  import { ChevronRight, Pencil, Plus, SlidersHorizontal, Trash2, TriangleAlert } from '../../lib/ikon/ikonok';
  import type { Csere } from '../dokumentum/kulonbseg';
  import { linkMegnyit, nyitasMod } from '../linkek/navigacio';
  import { linkek } from '../../lib/vault/linkek.svelte';
  import { tulajdonsagApi } from './api';
  import { LINK_KULCSOK, LISTA_KULCSOK, csupaLink, datumBevitel, ertekSzoveg, linkke, listaBevitel, listaElemek, szamBevitel, wikiReszek } from './ertek';
  import ListaMezo from './ListaMezo.svelte';
  import JavaslatMezo from './JavaslatMezo.svelte';
  import {
    JavaslatTar,
    ertekLista,
    javaslatFajta,
    kulcsLista,
    linkLista as linkJavaslatok,
    type JavaslatElem,
    type JavaslatFajta,
    type JavaslatLista,
    type LinkForras,
  } from './javaslat';
  import { TulajdonsagModell } from './modell.svelte';
  import type { Elemzes, KulcsJavaslat, Tulajdonsag, TulajdonsagApi, TulajdonsagTipus } from './tipusok';

  let {
    ut,
    szoveg,
    alkalmaz,
    valtozat,
    irhato,
    nyitva = $bindable(true),
    api = tulajdonsagApi(),
    kiegeszites,
    linkCel = (u: string, f: string) => linkek.linkCel(u, f),
    onelemzes,
  }: {
    ut: string;
    szoveg: () => Text;
    alkalmaz: (c: Csere) => void;
    /** nő, ha a szöveg változott */
    valtozat: number;
    irhato: boolean;
    nyitva?: boolean;
    api?: TulajdonsagApi;
    /** a link-mezők javaslatainak forrása: a vault fájljai és a legutóbbiak (a szerkesztő `[[` kiegészítésével közös) */
    kiegeszites?: LinkForras;
    /** a beírandó link-cél (a core legrövidebb egyértelmű alakja, L42) */
    linkCel?: (ut: string, forras: string) => Promise<string>;
    /** CX-006: minden új elemzés után (az élő nézet a formai hibás frontmattert nyersen mutatja) */
    onelemzes?: (e: Elemzes) => void;
  } = $props();

  const m = new TulajdonsagModell(
    untrack(() => ut),
    untrack(() => api),
    () => szoveg(),
    (c) => alkalmaz(c),
  );
  const id = $props.id();
  const tar = new JavaslatTar(untrack(() => api));

  $effect(() => {
    void valtozat;
    untrack(() => void m.frissit());
  });
  onMount(() => void m.frissit());
  $effect(() => {
    const e = m.elemzes;
    if (e) untrack(() => onelemzes?.(e));
  });

  const tul = $derived(m.elemzes?.tulajdonsagok ?? []);
  const problemak = $derived(m.elemzes?.problemak ?? []);
  /** Csendben (C38) az összecsukott panel fejléce egy halvány „N tulajdonság” sor; a séma-chip ettől függetlenül látszik. */
  const halk = $derived(csend.be && !nyitva);
  const statusok = $derived(m.sema?.osztaly?.ertekek ? (m.sema.status_ertekkeszlet ?? []) : []);
  let problemakNyitva = $state(false);

  // ---------------------------------------------------------------- mezők

  type Fajta = 'jelolo' | 'datum' | 'datumido' | 'szam' | 'lista' | 'link' | 'status' | 'csak' | 'szoveg';

  function fajta(t: Tulajdonsag): Fajta {
    if (t.tipus === 'unknown' || (typeof t.ertek === 'object' && t.ertek !== null && !Array.isArray(t.ertek))) return 'csak';
    if (t.kulcs === 'Status' && statusok.length) return 'status';
    if (t.tipus === 'checkbox') return 'jelolo';
    if (t.tipus === 'date') return 'datum';
    if (t.tipus === 'datetime') return 'datumido';
    if (t.tipus === 'number') return 'szam';
    if (Array.isArray(t.ertek) || t.tipus === 'tags' || t.tipus === 'multitext' || t.tipus === 'aliases' || (LISTA_KULCSOK as readonly string[]).includes(t.kulcs))
      return 'lista';
    if (typeof t.ertek === 'string' && wikiReszek(t.ertek)) return 'link';
    return 'szoveg';
  }

  const linkKulcs = (k: string) => (LINK_KULCSOK as readonly string[]).includes(k);
  let linkSzerkeszt = $state<string | null>(null);
  const listaTipus = (t: Tulajdonsag): TulajdonsagTipus => (t.tipus === 'tags' || t.tipus === 'aliases' ? t.tipus : 'multitext');
  const linkLista = (t: Tulajdonsag) => linkKulcs(t.kulcs) || csupaLink(t.ertek);

  function beallit(kulcs: string, ertek: unknown, tipus?: TulajdonsagTipus) {
    void m.muvelet({ muvelet: 'beallit', kulcs, ertek, tipus });
  }

  function torol(kulcs: string) {
    void m.muvelet({ muvelet: 'torol', kulcs });
  }

  function szovegValtozas(t: Tulajdonsag, e: Event & { currentTarget: HTMLInputElement }) {
    const v = e.currentTarget.value;
    if (v === ertekSzoveg(t.ertek)) return;
    if (fajta(t) === 'szam') {
      const n = szamBevitel(v);
      if (n === undefined) {
        m.elutasitott = { kulcs: t.kulcs, uzenet: 'A szám alakja: 12 vagy 3,5.' };
        return;
      }
      beallit(t.kulcs, n, 'number');
    } else beallit(t.kulcs, v === '' ? null : linkKulcs(t.kulcs) ? linkke(v) : v, 'text');
    linkSzerkeszt = null;
  }

  function enterBlur(e: KeyboardEvent & { currentTarget: HTMLInputElement }) {
    if (e.key === 'Enter') e.currentTarget.blur();
    else if (e.key === 'Escape') {
      e.stopPropagation();
      m.verzio++;
    }
  }

  // ---------------------------------------------------------------- javaslatok

  const URES: JavaslatLista = { elemek: [], eros: false };

  /** Egy mező javaslat-forrása. `jelenlegi`: a mező tárolt értéke — változatlan szövegnél a teljes lista jön (a fókuszra
   *  nyíló Status-lista ne csak a már beírt értéket mutassa). `kizar`: a lista-mező meglévő elemei. */
  function javaslo(kulcs: string, o: { fajta: JavaslatFajta; jelenlegi?: string; kizar?: () => string[] }) {
    return async (q: string): Promise<JavaslatLista> => {
      const kizar = o.kizar?.() ?? [];
      const query = o.jelenlegi !== undefined && q === o.jelenlegi ? '' : q;
      if (o.fajta === 'link') return kiegeszites ? linkJavaslatok(kiegeszites, query, kulcs, ut, linkCel, kizar) : URES;
      return ertekLista(await tar.ertekek(ut, kulcs), query, kizar);
    };
  }

  const javaslatErtek = async (e: JavaslatElem) => (e.feloldas ? await e.feloldas() : e.ertek);

  async function szovegJavaslat(t: Tulajdonsag, e: JavaslatElem) {
    const v = await javaslatErtek(e);
    if (v !== ertekSzoveg(t.ertek)) beallit(t.kulcs, v, 'text');
    linkSzerkeszt = null;
  }

  function chipNyit(nyers: string, e: MouseEvent) {
    const w = wikiReszek(nyers);
    if (w) void linkMegnyit({ forras: ut, cel: w.cel, alcel: w.alcel }, nyitasMod(e));
  }

  // ---------------------------------------------------------------- új tulajdonság

  const UJ_TIPUSOK: { id: TulajdonsagTipus; nev: string }[] = [
    { id: 'text', nev: 'Szöveg' },
    { id: 'number', nev: 'Szám' },
    { id: 'date', nev: 'Dátum' },
    { id: 'datetime', nev: 'Dátum és idő' },
    { id: 'checkbox', nev: 'Jelölő' },
    { id: 'multitext', nev: 'Lista' },
    { id: 'tags', nev: 'Címkék' },
  ];
  let ujNyitva = $state(false);
  let ujNev = $state('');
  let ujTipus = $state<TulajdonsagTipus>('text');
  let ujErtek = $state('');
  let ujJelolo = $state(false);
  const ismertNevek = $derived((m.sema?.osztaly?.mezosorrend ?? []).filter((k) => !m.elemzes?.kulcsok.includes(k)));
  /** a legutóbb lekért kulcs-javaslatok (a kiválasztott kulcs típusához) */
  let kulcsAdat: KulcsJavaslat[] = [];

  async function kulcsJavasol(q: string): Promise<JavaslatLista> {
    let lista = await tar.kulcsok(ut).catch(() => [] as KulcsJavaslat[]);
    // a core nélkül (vagy hibánál) a séma kulcsai, ahogy a korábbi névlista
    if (!lista.length) lista = ismertNevek.map((k) => ({ kulcs: k, db: 0, sema: true, tipus: null }));
    kulcsAdat = lista;
    return kulcsLista(lista, q, m.elemzes?.kulcsok ?? []);
  }

  /** A választott kulcs a típusát is beállítja (a vault `types.json`-ja, különben a séma lista-kulcsai). */
  function kulcsValaszt(e: JavaslatElem) {
    ujNev = e.ertek;
    const t =
      kulcsAdat.find((k) => k.kulcs === e.ertek)?.tipus ??
      (e.ertek === 'Tags' ? 'tags' : (LISTA_KULCSOK as readonly string[]).includes(e.ertek) ? 'multitext' : null);
    if (t && UJ_TIPUSOK.some((u) => u.id === t)) ujTipus = t;
  }

  const ujListas = $derived(ujTipus === 'multitext' || ujTipus === 'tags');
  /** a lista-érték már beírt része (a vessző előtti elemek): a javaslat csak az utolsó elemre szól */
  let ujElotag = '';

  async function ujErtekJavasol(q: string): Promise<JavaslatLista> {
    const kulcs = ujNev.trim();
    if (!kulcs) return URES;
    const i = ujListas ? q.lastIndexOf(',') : -1;
    ujElotag = i >= 0 ? q.slice(0, i + 1) : '';
    const kesz = listaBevitel(ujElotag);
    return javaslo(kulcs, { fajta: javaslatFajta(kulcs), kizar: () => kesz })(q.slice(i + 1).trim());
  }

  async function ujErtekValaszt(e: JavaslatElem) {
    const elotag = ujElotag;
    const v = await javaslatErtek(e);
    ujErtek = ujListas ? `${elotag ? `${elotag} ` : ''}${v}, ` : v;
  }

  async function ujFelvesz() {
    const kulcs = ujNev.trim();
    if (!kulcs) return;
    let ertek: unknown = ujErtek;
    if (ujTipus === 'checkbox') ertek = ujJelolo;
    else if (ujTipus === 'number') {
      const n = szamBevitel(ujErtek);
      if (n === undefined) {
        m.elutasitott = { kulcs, uzenet: 'A szám alakja: 12 vagy 3,5.' };
        return;
      }
      ertek = n;
    } else if (ujTipus === 'multitext' || ujTipus === 'tags') {
      ertek = listaBevitel(ujErtek).map((x) => (linkKulcs(kulcs) ? linkke(x) : x));
    } else if (ujErtek === '') ertek = null;
    else if (linkKulcs(kulcs)) ertek = linkke(ujErtek);
    const ok = await m.muvelet({ muvelet: 'beallit', kulcs, ertek, tipus: ujTipus });
    if (ok) {
      ujNev = ujErtek = '';
      ujJelolo = false;
      ujNyitva = false;
    }
  }

  const ujFuggo = $derived(m.fuggo && !tul.some((t) => t.kulcs === m.fuggo?.muvelet.kulcs) ? m.fuggo : null);
  const ujElutasitva = $derived(m.elutasitott && !tul.some((t) => t.kulcs === m.elutasitott?.kulcs) ? m.elutasitott : null);
</script>

{#snippet megerosites(fuggo: NonNullable<typeof m.fuggo>)}
  <div class="figyelmeztetes" role="alert">
    <span class="figy-ikon"><Ikon ikon={TriangleAlert} meret={14} /></span>
    <div class="figy-szoveg">
      {#each fuggo.problemak as p, i (i)}<p>{p.uzenet}</p>{/each}
      <p class="figy-info">A vault sémája szerint ez eltérés; a legacy séma-próba találatot ad rá.</p>
      <div class="figy-gombok">
        <button type="button" class="m-gomb semleges gomb" onclick={() => void m.megerosit()}>Mégis beírom</button>
        <button type="button" class="m-gomb semleges gomb halvany" onclick={() => m.elvet()}>Mégse</button>
      </div>
    </div>
  </div>
{/snippet}

{#snippet elutasitas(uzenet: string)}
  <p class="hiba" role="alert">{uzenet}</p>
{/snippet}

<section class="tul" aria-labelledby="{id}-cim">
  <header class="fej" data-csend-terulet>
    <h2 class="cim" id="{id}-cim">
      <button type="button" class="kapcsolo" class:halk aria-expanded={nyitva} aria-controls="{id}-lista" onclick={() => (nyitva = !nyitva)}>
        <span class="nyil" class:nyitva><Ikon ikon={ChevronRight} meret={14} /></span>
        {#if halk}
          <!-- C38: csendben az összecsukott panel egy halvány sor -->
          <span>{tul.length ? `${tul.length} tulajdonság` : 'Tulajdonságok'}</span>
        {:else}
          <Ikon ikon={SlidersHorizontal} meret={14} />
          <span>Tulajdonságok</span>
          {#if tul.length}<span class="db">{tul.length}</span>{/if}
        {/if}
      </button>
    </h2>
    {#if problemak.length}
      <button
        type="button"
        class="jelzes"
        class:hiba-szint={problemak.some((p) => p.szint === 'hiba')}
        aria-expanded={problemakNyitva}
        aria-controls="{id}-problemak"
        title="A vault sémája szerinti eltérések"
        onclick={() => ((problemakNyitva = !problemakNyitva), (nyitva = true))}
      >
        <Ikon ikon={TriangleAlert} meret={14} />
        {problemak.length} eltérés
      </button>
    {/if}
    <span class="tavoltarto"></span>
    {#if irhato}
      <button type="button" class="uj-gomb" aria-expanded={ujNyitva} data-csend-rejt onclick={() => ((ujNyitva = !ujNyitva), (nyitva = true))}>
        <Ikon ikon={Plus} meret={14} /> Új tulajdonság
      </button>
    {/if}
  </header>

  <div class="torzs" id="{id}-lista" hidden={!nyitva}>
    {#if m.hiba}<p class="hiba" role="alert">{m.hiba}</p>{/if}
    {#if problemakNyitva && problemak.length}
      <ul class="problemak" id="{id}-problemak" aria-label="Séma-eltérések">
        {#each problemak as p, i (i)}<li class:hiba={p.szint === 'hiba'}>{p.uzenet}</li>{/each}
      </ul>
    {/if}

    {#if m.elemzes && !m.elemzes.van && !ujNyitva}
      <p class="ures">A jegyzetnek nincs frontmattere{irhato ? '; az „Új tulajdonság” létrehozza.' : '.'}</p>
    {/if}

    {#each tul as t (t.kulcs)}
      {@const f = fajta(t)}
      <div class="sor" class:ervenytelen={!t.ervenyes}>
        <label class="kulcs" for="{id}-{t.kulcs}" title={t.kulcs}>{t.kulcs}</label>
        <div class="ertek">
          {#key `${m.verzio}:${t.kulcs}`}
            {#if f === 'jelolo'}
              <input id="{id}-{t.kulcs}" type="checkbox" class="jelolo" checked={t.ertek === true} disabled={!irhato} onchange={(e) => beallit(t.kulcs, e.currentTarget.checked, 'checkbox')} />
            {:else if f === 'datum' || f === 'datumido'}
              <input
                id="{id}-{t.kulcs}"
                type={f === 'datum' ? 'date' : 'datetime-local'}
                class="mezo"
                value={datumBevitel(f === 'datum' ? 'date' : 'datetime', t.ertek)}
                disabled={!irhato}
                onchange={(e) => beallit(t.kulcs, e.currentTarget.value === '' ? null : e.currentTarget.value, f === 'datum' ? 'date' : 'datetime')}
              />
            {:else if f === 'status'}
              <!-- az engedett értékek fókuszra nyíló listája; az értékkészleten kívüli gépelt érték megerősítést kér (22(b)) -->
              <JavaslatMezo
                id="{id}-{t.kulcs}"
                osztaly="mezo status"
                cimke={t.kulcs}
                value={ertekSzoveg(t.ertek)}
                placeholder="—"
                readonly={!irhato}
                nyitFokuszra
                javasol={javaslo(t.kulcs, { fajta: 'ertek', jelenlegi: ertekSzoveg(t.ertek) })}
                onvalaszt={(e) => void szovegJavaslat(t, e)}
                onchange={(e) => szovegValtozas(t, e)}
                onkeydown={enterBlur}
              />
            {:else if f === 'lista'}
              <ListaMezo
                elemek={listaElemek(t.ertek)}
                cimke={t.kulcs}
                {irhato}
                link={linkLista(t)}
                onvaltozas={(uj) => beallit(t.kulcs, uj, listaTipus(t))}
                onnyit={chipNyit}
                javasol={javaslo(t.kulcs, { fajta: linkLista(t) ? 'link' : 'ertek', kizar: () => listaElemek(t.ertek) })}
              />
            {:else if f === 'link' && linkSzerkeszt !== t.kulcs}
              {@const w = wikiReszek(t.ertek)}
              <span class="linkchip">
                <button type="button" class="nyit" title={String(t.ertek)} onclick={(e) => chipNyit(String(t.ertek), e)}>{w?.felirat}</button>
                {#if irhato}
                  <button type="button" class="szerk" aria-label="{t.kulcs} szerkesztése" title="Szerkesztés" onclick={() => (linkSzerkeszt = t.kulcs)}>
                    <Ikon ikon={Pencil} meret={14} />
                  </button>
                {/if}
              </span>
            {:else if f === 'csak'}
              <code class="csak" title="Nem szerkeszthető itt: forrásmódban írható">{ertekSzoveg(t.ertek)}</code>
            {:else if f === 'szam'}
              <input
                id="{id}-{t.kulcs}"
                type="text"
                class="mezo"
                inputmode="decimal"
                value={ertekSzoveg(t.ertek)}
                placeholder="Üres"
                readonly={!irhato}
                onchange={(e) => szovegValtozas(t, e)}
                onkeydown={enterBlur}
              />
            {:else}
              <JavaslatMezo
                id="{id}-{t.kulcs}"
                osztaly="mezo"
                cimke={t.kulcs}
                value={ertekSzoveg(t.ertek)}
                placeholder="Üres"
                readonly={!irhato}
                javasol={javaslo(t.kulcs, { fajta: javaslatFajta(t.kulcs, t.ertek), jelenlegi: ertekSzoveg(t.ertek) })}
                onvalaszt={(e) => void szovegJavaslat(t, e)}
                onchange={(e) => szovegValtozas(t, e)}
                onblur={() => (linkSzerkeszt = null)}
                onkeydown={enterBlur}
              />
            {/if}
          {/key}
        </div>
        {#if irhato}
          <button type="button" class="torol" aria-label="{t.kulcs} törlése" title="Törlés" onclick={() => torol(t.kulcs)}>
            <Ikon ikon={Trash2} meret={14} />
          </button>
        {/if}
      </div>
      {#if m.elutasitott?.kulcs === t.kulcs}{@render elutasitas(m.elutasitott.uzenet)}{/if}
      {#if m.fuggo?.muvelet.kulcs === t.kulcs}{@render megerosites(m.fuggo)}{/if}
    {/each}

    {#if ujNyitva && irhato}
      <form class="uj" onsubmit={(e) => (e.preventDefault(), void ujFelvesz())}>
        <JavaslatMezo osztaly="mezo nev" cimke="Új tulajdonság neve" placeholder="Név" bind:value={ujNev} javasol={kulcsJavasol} onvalaszt={kulcsValaszt} />
        <select class="mezo tipus" aria-label="Típus" bind:value={ujTipus}>
          {#each UJ_TIPUSOK as t (t.id)}<option value={t.id}>{t.nev}</option>{/each}
        </select>
        {#if ujTipus === 'checkbox'}
          <input type="checkbox" class="jelolo" aria-label="Érték" bind:checked={ujJelolo} />
        {:else if ujTipus === 'date'}
          <input type="date" class="mezo" aria-label="Érték" bind:value={ujErtek} />
        {:else if ujTipus === 'datetime'}
          <input type="datetime-local" class="mezo" aria-label="Érték" bind:value={ujErtek} />
        {:else}
          <JavaslatMezo
            osztaly="mezo ertek"
            cimke="Érték"
            placeholder={ujListas ? 'Vesszővel elválasztva' : 'Érték'}
            inputmode={ujTipus === 'number' ? 'decimal' : undefined}
            bind:value={ujErtek}
            javasol={ujTipus === 'number' ? () => URES : ujErtekJavasol}
            onvalaszt={(e) => void ujErtekValaszt(e)}
          />
        {/if}
        <button type="submit" class="m-gomb semleges gomb" disabled={!ujNev.trim() || m.dolgozik}>Hozzáadás</button>
        <button type="button" class="m-gomb semleges gomb halvany" onclick={() => ((ujNyitva = false), m.elvet())}>Mégse</button>
      </form>
      {#if ujElutasitva}{@render elutasitas(ujElutasitva.uzenet)}{/if}
      {#if ujFuggo}{@render megerosites(ujFuggo)}{/if}
    {/if}
  </div>
</section>

<style>
  .tul {
    flex: none;
    max-height: 40%;
    display: flex;
    flex-direction: column;
    border-bottom: var(--keret-vastag) solid var(--keret);
    background: var(--hatter);
    font-size: var(--betu-ui);
    line-height: var(--sor-ui);
  }

  .fej {
    flex: none;
    display: flex;
    align-items: center;
    gap: var(--t-2);
    min-height: var(--magassag-sor);
    padding: 0 var(--t-4);
  }

  .cim {
    margin: 0;
    font: inherit;
  }

  .kapcsolo {
    display: flex;
    align-items: center;
    gap: var(--t-2);
    height: var(--magassag-sor);
    padding: 0 var(--t-1);
    border-radius: var(--kerekites);
    color: var(--szoveg-masodlagos);
    font-weight: var(--suly-kozepes);
  }

  .kapcsolo.halk {
    color: var(--szoveg-halvany);
    font-weight: var(--suly-normal);
  }

  .kapcsolo:hover {
    background: var(--hatter-hover);
    color: var(--szoveg);
  }

  .nyil {
    display: grid;
    color: var(--szoveg-halvany);
    transition: transform var(--mozgas-gyors) var(--mozgas-gorbe);
  }

  .nyil.nyitva {
    transform: rotate(90deg);
  }

  .db {
    color: var(--szoveg-halvany);
    font-variant-numeric: tabular-nums;
  }

  .jelzes {
    display: flex;
    align-items: center;
    gap: var(--t-1);
    height: var(--magassag-suru);
    padding: 0 var(--t-2);
    border-radius: var(--kerekites-kicsi);
    background: var(--figyelmeztetes-hatter);
    color: var(--figyelmeztetes);
    font-size: var(--betu-kicsi);
  }

  .jelzes.hiba-szint {
    background: var(--hiba-hatter);
    color: var(--hiba);
  }

  .tavoltarto {
    flex: 1;
  }

  .uj-gomb {
    display: flex;
    align-items: center;
    gap: var(--t-1);
    height: var(--magassag-suru);
    padding: 0 var(--t-2);
    border-radius: var(--kerekites);
    color: var(--akcent-szoveg);
    font-size: var(--betu-kicsi);
  }

  .uj-gomb:hover {
    background: var(--hatter-hover);
  }

  .torzs {
    flex: 1;
    min-height: 0;
    overflow: auto;
    padding: var(--t-1) var(--t-4) var(--t-3);
  }

  .torzs[hidden] {
    display: none;
  }

  .sor {
    display: grid;
    grid-template-columns: 104px minmax(0, 1fr) 24px;
    align-items: start;
    gap: var(--t-2);
    min-height: var(--magassag-sor);
    padding: 2px 0;
  }

  .kulcs {
    padding-top: 4px;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    color: var(--szoveg-halvany);
  }

  .ertek {
    min-width: 0;
    padding-top: 3px;
  }

  .ertek :global(.mezo),
  .mezo {
    width: 100%;
    height: var(--magassag-suru);
    padding: 0 var(--t-2);
    border: var(--keret-vastag) solid transparent;
    border-radius: var(--kerekites-kicsi);
    background: transparent;
    font-size: var(--betu-ui);
  }

  .ertek :global(.mezo:hover:not(:disabled):not([readonly])),
  .mezo:hover:not(:disabled):not([readonly]) {
    background: var(--hatter-hover);
  }

  .ertek :global(.mezo:focus-visible),
  .mezo:focus-visible {
    border-color: var(--keret-mezo);
    background: var(--hatter);
    outline-offset: 0;
  }

  .ertek :global(.mezo::placeholder),
  .uj :global(.mezo::placeholder),
  .mezo::placeholder {
    color: var(--szoveg-halvany);
  }

  select.mezo,
  .ertek :global(.mezo.status) {
    width: auto;
    min-width: 120px;
  }

  .jelolo {
    margin: 5px var(--t-2);
    accent-color: var(--akcent);
  }

  .linkchip .nyit {
    padding: 0 var(--t-2);
    color: var(--akcent-szoveg);
  }

  .linkchip .nyit:hover {
    text-decoration: underline;
  }

  .linkchip {
    display: inline-flex;
    align-items: center;
    max-width: 100%;
  }

  .linkchip .szerk {
    display: grid;
    place-items: center;
    width: var(--magassag-suru);
    height: var(--magassag-suru);
    border-radius: var(--kerekites-kicsi);
    color: var(--szoveg-halvany);
    opacity: 0;
  }

  .sor:hover .szerk,
  .szerk:focus-visible {
    opacity: 1;
  }

  .csak {
    display: block;
    padding: 0 var(--t-2);
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    color: var(--szoveg-halvany);
    font-family: var(--betu-mono);
    font-size: 0.875em;
  }

  .torol {
    display: grid;
    place-items: center;
    width: var(--magassag-suru);
    height: var(--magassag-suru);
    margin-top: 2px;
    border-radius: var(--kerekites-kicsi);
    color: var(--szoveg-halvany);
    opacity: 0;
  }

  .sor:hover .torol,
  .sor:focus-within .torol,
  .torol:focus-visible {
    opacity: 1;
  }

  .torol:hover {
    background: var(--hatter-hover);
    color: var(--hiba);
  }

  .ervenytelen .ertek {
    color: var(--hiba);
  }

  .hiba {
    margin: 0 0 var(--t-1) calc(104px + var(--t-2));
    color: var(--hiba);
    font-size: var(--betu-kicsi);
    line-height: var(--sor-kicsi);
  }

  .problemak {
    margin: 0 0 var(--t-2);
    padding: 0 0 0 var(--t-4);
    color: var(--figyelmeztetes);
    font-size: var(--betu-kicsi);
    line-height: var(--sor-kicsi);
  }

  .problemak li.hiba {
    margin: 0;
    color: var(--hiba);
  }

  .ures {
    margin: var(--t-1) 0;
    color: var(--szoveg-halvany);
  }

  .figyelmeztetes {
    display: flex;
    gap: var(--t-2);
    margin: 2px 0 var(--t-2) calc(104px + var(--t-2));
    padding: var(--t-2) var(--t-3);
    border-radius: var(--kerekites);
    background: var(--figyelmeztetes-hatter);
    color: var(--figyelmeztetes);
    font-size: var(--betu-kicsi);
    line-height: var(--sor-kicsi);
  }

  .figy-ikon {
    padding-top: 1px;
  }

  .figy-szoveg p {
    margin: 0 0 var(--t-1);
  }

  .figy-info {
    color: var(--szoveg-masodlagos);
  }

  .figy-gombok {
    display: flex;
    gap: var(--t-2);
    margin-top: var(--t-2);
  }

  .gomb {
    height: var(--magassag-suru);
  }

  .gomb.halvany {
    border-color: transparent;
    color: var(--szoveg-masodlagos);
  }

  .uj {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: var(--t-2);
    margin-top: var(--t-2);
  }

  .uj :global(.mezo) {
    height: var(--magassag-suru);
    padding: 0 var(--t-2);
    border: var(--keret-vastag) solid var(--keret-mezo);
    border-radius: var(--kerekites-kicsi);
    background: transparent;
    font-size: var(--betu-ui);
  }

  .uj :global(.mezo:focus-visible) {
    background: var(--hatter);
    outline-offset: 0;
  }

  .uj :global(.mezo.nev) {
    width: 140px;
  }

  .uj :global(.mezo.ertek) {
    flex: 1 1 160px;
    min-width: 120px;
  }

  .uj .tipus {
    border-color: var(--keret-mezo);
  }

  .uj .mezo {
    border-color: var(--keret-mezo);
    width: auto;
    flex: 1 1 160px;
    min-width: 120px;
  }
</style>
