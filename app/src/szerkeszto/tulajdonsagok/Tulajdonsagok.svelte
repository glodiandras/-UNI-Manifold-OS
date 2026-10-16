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
  import { t as tx, tp as tpx } from '../../lib/i18n';
  import type { Text } from '@codemirror/state';
  import { onMount, tick, untrack } from 'svelte';
  import { csend } from '../../lib/elrendezes/csend.svelte';
  import Ikon from '../../lib/ikon/Ikon.svelte';
  import { Calendar, Check, ChevronRight, ClipboardPaste, Copy, FileClock, Hash, Link, List, Pencil, Plus, Scissors, SlidersHorizontal, Tags, Trash2, TriangleAlert, Type } from '../../lib/ikon/ikonok';
  import type { Csere } from '../dokumentum/kulonbseg';
  import { linkMegnyit, nyitasMod } from '../linkek/navigacio';
  import { lebegoMenu, type MenuElem } from '../notion/menu';
  import { tulajdonsagVagolapSzoveg, vagolapTulajdonsag } from './vagolap';
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
  import { TulajdonsagModell, tipusValtozas } from './modell.svelte';
  import { rogzitettTipus, type Elemzes, type KulcsJavaslat, type TaroltTulajdonsagTipus, type Tulajdonsag, type TulajdonsagApi, type TulajdonsagTipus } from './tipusok';

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
    () => irhato,
  );
  const id = $props.id();
  const tar = new JavaslatTar(untrack(() => api));

  $effect(() => {
    void valtozat;
    void tipusValtozas.verzio;
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
    if (!t.ervenyes || t.tipus === 'unknown' || (typeof t.ertek === 'object' && t.ertek !== null && !Array.isArray(t.ertek))) return 'csak';
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

  // ---------------------------------------------------------------- kulcs átnevezése, sor-menü (03-properties-06/07)

  let atnevKulcs = $state<string | null>(null);
  let atnevErtek = $state('');
  /** az Escape vagy a sikeres Enter után érkező blur nem ment újra */
  let atnevKesz = false;

  function atnevezNyit(t: Tulajdonsag) {
    if (!irhato || m.dolgozik || m.tipusDolgozik) return;
    atnevKesz = false;
    atnevKulcs = t.kulcs;
    atnevErtek = t.kulcs;
    m.elutasitott = null;
    void tick().then(() => {
      const mezo = document.getElementById(`${id}-atnev`) as HTMLInputElement | null;
      mezo?.focus();
      mezo?.select();
    });
  }

  async function atnevezMent() {
    const regi = atnevKulcs, uj = atnevErtek.trim();
    if (atnevKesz || regi === null) return;
    atnevKesz = true;
    if (!uj || uj === regi) { atnevKulcs = null; return; }
    const ok = await m.muvelet({ muvelet: 'atnevez', kulcs: regi, uj_kulcs: uj });
    if (ok || m.fuggo) atnevKulcs = null; // siker, vagy séma-megerősítés vár (a sor alatt)
    else atnevKesz = false; // elutasítva: a mező nyitva marad a hibával, javítható
  }

  function atnevBillentyu(e: KeyboardEvent) {
    if (e.isComposing) return;
    if (e.key === 'Enter') { e.preventDefault(); void atnevezMent(); }
    else if (e.key === 'Escape') { e.preventDefault(); e.stopPropagation(); atnevKesz = true; atnevKulcs = null; }
  }

  async function vagolapraIr(szoveg: string): Promise<boolean> {
    try {
      await navigator.clipboard.writeText(szoveg);
      return true;
    } catch {
      m.hiba = tx('A vágólap nem érhető el.');
      return false;
    }
  }

  async function masol(t: Tulajdonsag): Promise<boolean> {
    return vagolapraIr(tulajdonsagVagolapSzoveg(t));
  }

  async function kivag(t: Tulajdonsag) {
    if (await masol(t)) torol(t.kulcs);
  }

  /** Beillesztés: a vágólap `kulcs: érték` szövege beállítja azt a kulcsot (újat is felvesz); kulcs nélküli szöveg ennek a sornak
   *  az értéke. Az érték ellenőrzése a core-é (a hibás vagy séma-sértő érték a sor alatt látszik). */
  async function beilleszt(t: Tulajdonsag) {
    let szoveg = '';
    try {
      szoveg = await navigator.clipboard.readText();
    } catch {
      m.hiba = tx('A vágólap nem érhető el.');
      return;
    }
    const v = vagolapTulajdonsag(szoveg);
    if (!v) { m.elutasitott = { kulcs: t.kulcs, uzenet: tx('A vágólap szövege nem tulajdonság.') }; return; }
    const kulcs = v.kulcs ?? t.kulcs;
    const letezo = tul.find((x) => x.kulcs === kulcs);
    const tipus: TulajdonsagTipus = letezo && letezo.tipus !== 'unknown' ? letezo.tipus : v.tipus;
    let ertek = v.ertek;
    if (tipus === 'text' && Array.isArray(ertek)) ertek = ertek.join(', ');
    else if ((tipus === 'multitext' || tipus === 'tags' || tipus === 'aliases') && !Array.isArray(ertek)) ertek = ertek === null || ertek === '' ? [] : [String(ertek)];
    else if (tipus === 'number' && typeof ertek === 'string') ertek = szamBevitel(ertek) ?? ertek;
    beallit(kulcs, ertek, tipus);
  }

  function sorMenu(t: Tulajdonsag, x: number, y: number, fokusz: () => void) {
    const elemek: MenuElem[] = [];
    const akciok = new Map<string, () => void>();
    const hozzaad = (id: string, nev: string, ikon: MenuElem['ikon'], fn: () => void, veszely = false) => {
      elemek.push({ id, nev, ikon, veszely });
      akciok.set(id, fn);
    };
    if (irhato) hozzaad('atnevez', tx('Átnevezés|menu'), Pencil, () => atnevezNyit(t));
    if (irhato) hozzaad('kivag', tx('Kivágás|menu'), Scissors, () => void kivag(t));
    hozzaad('masol', tx('Másolás|menu'), Copy, () => void masol(t));
    if (irhato) hozzaad('beilleszt', tx('Beillesztés|menu'), ClipboardPaste, () => void beilleszt(t));
    if (irhato) hozzaad('torol', tx('Tulajdonság törlése'), Trash2, () => torol(t.kulcs), true);
    lebegoMenu({ focus: fokusz }, x, y, elemek, akciok, tx('A(z) „{kulcs}” tulajdonság menüje', { kulcs: t.kulcs }));
  }

  function sorKontextus(e: MouseEvent, t: Tulajdonsag) {
    const cel = e.target as HTMLElement;
    if (cel.closest('textarea')) return; // a szövegmező saját (másolás/beillesztés) menüje marad
    e.preventDefault();
    const sor = e.currentTarget as HTMLElement;
    sorMenu(t, e.clientX, e.clientY, () => (sor.querySelector<HTMLElement>('input, button') ?? sor).focus());
  }

  function sorBillentyu(e: KeyboardEvent, t: Tulajdonsag) {
    if (!(e.key === 'ContextMenu' || (e.key === 'F10' && e.shiftKey))) return;
    e.preventDefault();
    const cel = e.target as HTMLElement, r = cel.getBoundingClientRect();
    sorMenu(t, r.left, r.bottom, () => cel.focus());
  }

  function szovegValtozas(t: Tulajdonsag, e: Event & { currentTarget: HTMLInputElement }) {
    const v = e.currentTarget.value;
    if (v === ertekSzoveg(t.ertek)) return;
    if (fajta(t) === 'szam') {
      const n = szamBevitel(v);
      if (n === undefined) {
        m.elutasitott = { kulcs: t.kulcs, uzenet: tx('A szám alakja: 12 vagy 3,5.') };
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

  // ---------------------------------------------------------------- vault-szintű tulajdonságtípus

  const TIPUSOK: { id: TaroltTulajdonsagTipus; nev: () => string; ikon: typeof Type }[] = [
    { id: 'text', nev: () => tx('Szöveg|tipus'), ikon: Type },
    { id: 'multitext', nev: () => tx('Lista|tipus'), ikon: List },
    { id: 'number', nev: () => tx('Szám|tipus'), ikon: Hash },
    { id: 'checkbox', nev: () => tx('Jelölő|tipus'), ikon: Check },
    { id: 'date', nev: () => tx('Dátum|tipus'), ikon: Calendar },
    { id: 'datetime', nev: () => tx('Dátum és idő'), ikon: FileClock },
    { id: 'tags', nev: () => tx('Címkék'), ikon: Tags },
    { id: 'aliases', nev: () => tx('Aliasok'), ikon: Link },
  ];
  const tipusAdat = (tipus: TulajdonsagTipus) => TIPUSOK.find((t) => t.id === tipus);
  let tipusKulcs = $state<string | null>(null);
  let tipusCel = $state<TaroltTulajdonsagTipus>('text');
  let tipusMezo: HTMLSelectElement | undefined = $state();
  let tipusNyito: HTMLButtonElement | null = null;

  async function tipusNyit(t: Tulajdonsag, nyito: HTMLButtonElement) {
    if (!irhato || m.tipusDolgozik) return;
    tipusNyito = nyito;
    tipusKulcs = t.kulcs;
    tipusCel = rogzitettTipus(t.kulcs) ?? (tipusAdat(t.tipus)?.id ?? 'text');
    m.tipusHiba = null;
    if (rogzitettTipus(t.kulcs)) return;
    if (!api.tipusok || !api.tipusBeallit) { m.tipusHiba = tx('A típusválasztó nem érhető el ehhez a munkatérhez.'); return; }
    if (await m.tipusokatTolt() && tipusKulcs === t.kulcs) {
      const nev = m.tipusAdat?.types[t.kulcs];
      tipusCel = TIPUSOK.find((t) => t.id === nev)?.id ?? tipusCel;
      await tick();
      tipusMezo?.focus();
    }
  }

  function tipusZar() {
    if (m.tipusDolgozik) return;
    tipusKulcs = null;
    if (tipusNyito?.isConnected) tipusNyito.focus();
  }

  async function tipusMent() {
    if (tipusKulcs && await m.tipusValt(tipusKulcs, tipusCel)) tipusZar();
  }

  // ---------------------------------------------------------------- új tulajdonság

  const UJ_TIPUSOK: { id: TulajdonsagTipus; nev: string }[] = [
    { id: 'text', nev: tx('Szöveg|tipus') },
    { id: 'number', nev: tx('Szám|tipus') },
    { id: 'date', nev: tx('Dátum|tipus') },
    { id: 'datetime', nev: tx('Dátum és idő') },
    { id: 'checkbox', nev: tx('Jelölő|tipus') },
    { id: 'multitext', nev: tx('Lista|tipus') },
    { id: 'tags', nev: tx('Címkék') },
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
        m.elutasitott = { kulcs, uzenet: tx('A szám alakja: 12 vagy 3,5.') };
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

<svelte:window onkeydown={(e) => { if (tipusKulcs && e.key === 'Escape' && !m.tipusDolgozik) { e.stopPropagation(); tipusZar(); } }} />

{#snippet megerosites(fuggo: NonNullable<typeof m.fuggo>)}
  <div class="figyelmeztetes" role="alert">
    <span class="figy-ikon"><Ikon ikon={TriangleAlert} meret={14} /></span>
    <div class="figy-szoveg">
      {#each fuggo.problemak as p, i (i)}<p>{p.uzenet}</p>{/each}
      <p class="figy-info">{tx('A vault sémája szerint ez eltérés; a vault-ellenőrző találatot ad rá.')}</p>
      <div class="figy-gombok">
        <button type="button" class="m-gomb semleges gomb" onclick={() => void m.megerosit()}>{tx('Mégis beírom')}</button>
        <button type="button" class="m-gomb semleges gomb halvany" onclick={() => m.elvet()}>{tx('Mégse')}</button>
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
          <span>{tul.length ? tpx('{n} tulajdonság', tul.length) : tx('Tulajdonságok')}</span>
        {:else}
          <Ikon ikon={SlidersHorizontal} meret={14} />
          <span>{tx('Tulajdonságok')}</span>
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
        title={tx('A vault sémája szerinti eltérések')}
        onclick={() => ((problemakNyitva = !problemakNyitva), (nyitva = true))}
      >
        <Ikon ikon={TriangleAlert} meret={14} />
        {tpx('{n} eltérés', problemak.length)}
      </button>
    {/if}
    <span class="tavoltarto"></span>
    {#if irhato}
      <button type="button" class="uj-gomb" aria-expanded={ujNyitva} data-csend-rejt onclick={() => ((ujNyitva = !ujNyitva), (nyitva = true))}>
        <Ikon ikon={Plus} meret={14} /> {tx('Új tulajdonság')}
      </button>
    {/if}
  </header>

  <div class="torzs" id="{id}-lista" hidden={!nyitva}>
    {#if m.hiba}<p class="hiba" role="alert">{m.hiba}</p>{/if}
    {#if m.tipusFigyelmeztetes}<p class="tipus-figyelmeztetes" role="status"><Ikon ikon={TriangleAlert} meret={14} />{m.tipusFigyelmeztetes}</p>{/if}
    {#if problemakNyitva && problemak.length}
      <ul class="problemak" id="{id}-problemak" aria-label={tx('Séma-eltérések')}>
        {#each problemak as p, i (i)}<li class:hiba={p.szint === 'hiba'}>{p.uzenet}</li>{/each}
      </ul>
    {/if}

    {#if m.elemzes && !m.elemzes.van && !ujNyitva}
      <p class="ures">{tx('A jegyzetnek nincs frontmattere')}{irhato ? '; ' + tx('az „Új tulajdonság” létrehozza.') : '.'}</p>
    {/if}

    {#each tul as t (t.kulcs)}
      {@const f = fajta(t)}
      <!-- a sor menüje: jobb klikk, ContextMenu / Shift+F10 (a billentyűs belépő a sor fókuszálható elemein él) -->
      <!-- svelte-ignore a11y_no_static_element_interactions -->
      <div class="sor" class:ervenytelen={!t.ervenyes} data-kulcs={t.kulcs} oncontextmenu={(e) => sorKontextus(e, t)} onkeydown={(e) => sorBillentyu(e, t)}>
        <div class="kulcs-cella">
          <button type="button" class="tipus-gomb" aria-label={tx('{kulcs} típusa: {tipus}', { kulcs: t.kulcs, tipus: tipusAdat(t.tipus)?.nev() ?? tx('Ismeretlen típus') })} aria-expanded={tipusKulcs === t.kulcs} aria-controls="{id}-tipus-{t.kulcs}" disabled={!irhato || m.tipusDolgozik || m.dolgozik} onclick={(e) => void tipusNyit(t, e.currentTarget)}>
            <Ikon ikon={tipusAdat(t.tipus)?.ikon ?? TriangleAlert} meret={16} />
          </button>
          {#if atnevKulcs === t.kulcs}
            <input
              id="{id}-atnev"
              class="mezo atnev"
              type="text"
              spellcheck="false"
              autocomplete="off"
              aria-label={tx('{kulcs} új neve', { kulcs: t.kulcs })}
              bind:value={atnevErtek}
              onkeydown={atnevBillentyu}
              onblur={() => void atnevezMent()}
            />
          {:else}
            <!-- svelte-ignore a11y_no_noninteractive_element_interactions (a dupla kattintás az egér-parancsikon; a billentyűs út a sor menüje) -->
            <label class="kulcs" for="{id}-{t.kulcs}" title={irhato ? tx('{kulcs} (dupla kattintás: átnevezés)', { kulcs: t.kulcs }) : t.kulcs} ondblclick={() => atnevezNyit(t)}>{t.kulcs}</label>
          {/if}
        </div>
        <div class="ertek">
          {#key `${m.verzio}:${t.kulcs}`}
            {#if f === 'jelolo'}
              <input id="{id}-{t.kulcs}" type="checkbox" class="jelolo" checked={t.ertek === true} disabled={!irhato || m.tipusDolgozik} onchange={(e) => beallit(t.kulcs, e.currentTarget.checked, 'checkbox')} />
            {:else if f === 'datum' || f === 'datumido'}
              <input
                id="{id}-{t.kulcs}"
                type={f === 'datum' ? 'date' : 'datetime-local'}
                class="mezo"
                value={datumBevitel(f === 'datum' ? 'date' : 'datetime', t.ertek)}
                disabled={!irhato || m.tipusDolgozik}
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
                readonly={!irhato || m.tipusDolgozik}
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
                irhato={irhato && !m.tipusDolgozik}
                link={linkLista(t)}
                cimkes={t.tipus === 'tags'}
                onvaltozas={(uj) => beallit(t.kulcs, uj, listaTipus(t))}
                onnyit={chipNyit}
                javasol={javaslo(t.kulcs, { fajta: linkLista(t) ? 'link' : 'ertek', kizar: () => listaElemek(t.ertek) })}
              />
            {:else if f === 'link' && linkSzerkeszt !== t.kulcs}
              {@const w = wikiReszek(t.ertek)}
              <span class="linkchip">
                <button type="button" class="nyit" title={String(t.ertek)} onclick={(e) => chipNyit(String(t.ertek), e)}>{w?.felirat}</button>
                {#if irhato}
                  <button type="button" class="szerk" aria-label={tx('{kulcs} szerkesztése', { kulcs: t.kulcs })} title={tx('Szerkesztés')} onclick={() => (linkSzerkeszt = t.kulcs)}>
                    <Ikon ikon={Pencil} meret={14} />
                  </button>
                {/if}
              </span>
            {:else if f === 'csak'}
              <code class="csak" title={tx('Nem szerkeszthető itt: forrásmódban írható')}>{ertekSzoveg(t.ertek)}</code>
            {:else if f === 'szam'}
              <input
                id="{id}-{t.kulcs}"
                type="text"
                class="mezo"
                inputmode="decimal"
                value={ertekSzoveg(t.ertek)}
                placeholder={tx('Üres')}
                readonly={!irhato || m.tipusDolgozik}
                onchange={(e) => szovegValtozas(t, e)}
                onkeydown={enterBlur}
              />
            {:else}
              <JavaslatMezo
                id="{id}-{t.kulcs}"
                osztaly="mezo"
                cimke={t.kulcs}
                value={ertekSzoveg(t.ertek)}
                placeholder={tx('Üres')}
                readonly={!irhato || m.tipusDolgozik}
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
          <button type="button" class="torol" disabled={m.tipusDolgozik} aria-label={tx('{kulcs} törlése', { kulcs: t.kulcs })} title={tx('Törlés')} onclick={() => torol(t.kulcs)}>
            <Ikon ikon={Trash2} meret={14} />
          </button>
        {/if}
      </div>
      {#if !t.ervenyes}<p class="tipus-info ervenytelen-info"><Ikon ikon={TriangleAlert} meret={14} />{tx('A meglévő érték ehhez a típushoz nem érvényes; a forrásban megmaradt.')}</p>{/if}
      {#if tipusKulcs === t.kulcs}
        <div class="tipus-menu" id="{id}-tipus-{t.kulcs}" role="group" aria-label={tx('A(z) „{kulcs}” típusa', { kulcs: t.kulcs })}>
          {#if rogzitettTipus(t.kulcs)}
            <p>{tx('A beépített címke- és aliasmezők típusa rögzített.')}</p>
          {:else}
            <p class="tipus-info">{tx('Az összes jegyzetre érvényes. A meglévő értékek megmaradnak.')}</p>
            {#if m.tipusBetolt}<p role="status">{tx('Típusok betöltése…')}</p>{/if}
            <select class="mezo" aria-label={tx('Tulajdonság típusa')} bind:this={tipusMezo} bind:value={tipusCel} disabled={m.tipusBetolt || m.tipusDolgozik || !m.tipusIrhato || m.tipusUtkozes}>
              {#each TIPUSOK as tipus (tipus.id)}<option value={tipus.id} disabled={tipus.id === 'tags' || tipus.id === 'aliases'}>{tipus.nev()}</option>{/each}
            </select>
            {#if m.tipusHiba}<p class="tipus-hiba" role="alert"><Ikon ikon={TriangleAlert} meret={14} />{m.tipusHiba}</p>{/if}
            {#if m.tipusUtkozes || m.tipusHiba}
              <button type="button" class="m-gomb semleges gomb" disabled={m.tipusBetolt || m.tipusDolgozik} onclick={() => void m.tipusokatTolt()}>{tx('Típusok újratöltése')}</button>
            {/if}
            <button type="button" class="m-gomb semleges gomb" disabled={!m.tipusIrhato || !m.tipusAdat || m.tipusBetolt || m.tipusDolgozik || m.dolgozik || m.tipusUtkozes || !!m.tipusHiba || tipusCel === 'tags' || tipusCel === 'aliases'} onclick={() => void tipusMent()}>{m.tipusDolgozik ? tx('Típus mentése…') : tx('Típus mentése')}</button>
          {/if}
          <button type="button" class="m-gomb semleges gomb halvany" disabled={m.tipusDolgozik} onclick={tipusZar}>{tx('Bezárás')}</button>
        </div>
      {/if}
      {#if m.elutasitott?.kulcs === t.kulcs}{@render elutasitas(m.elutasitott.uzenet)}{/if}
      {#if m.fuggo?.muvelet.kulcs === t.kulcs}{@render megerosites(m.fuggo)}{/if}
    {/each}

    {#if ujNyitva && irhato}
      <form class="uj" onsubmit={(e) => (e.preventDefault(), void ujFelvesz())}>
        <JavaslatMezo osztaly="mezo nev" cimke={tx('Új tulajdonság neve')} placeholder={tx('Név')} bind:value={ujNev} javasol={kulcsJavasol} onvalaszt={kulcsValaszt} />
        <select class="mezo tipus" aria-label={tx('Típus')} bind:value={ujTipus}>
          {#each UJ_TIPUSOK as t (t.id)}<option value={t.id}>{t.nev}</option>{/each}
        </select>
        {#if ujTipus === 'checkbox'}
          <input type="checkbox" class="jelolo" aria-label={tx('Érték')} bind:checked={ujJelolo} />
        {:else if ujTipus === 'date'}
          <input type="date" class="mezo" aria-label={tx('Érték')} bind:value={ujErtek} />
        {:else if ujTipus === 'datetime'}
          <input type="datetime-local" class="mezo" aria-label={tx('Érték')} bind:value={ujErtek} />
        {:else}
          <JavaslatMezo
            osztaly="mezo ertek"
            cimke={tx('Érték')}
            placeholder={ujListas ? tx('Vesszővel elválasztva') : tx('Érték')}
            inputmode={ujTipus === 'number' ? 'decimal' : undefined}
            bind:value={ujErtek}
            javasol={ujTipus === 'number' ? () => URES : ujErtekJavasol}
            onvalaszt={(e) => void ujErtekValaszt(e)}
          />
        {/if}
        <button type="submit" class="m-gomb semleges gomb" disabled={!ujNev.trim() || m.dolgozik || m.tipusDolgozik}>{tx('Hozzáadás')}</button>
        <button type="button" class="m-gomb semleges gomb halvany" onclick={() => ((ujNyitva = false), m.elvet())}>{tx('Mégse')}</button>
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

  .atnev { flex: 1; min-width: 0; width: 100%; }
  .kulcs-cella { display: flex; align-items: start; gap: var(--t-1); min-width: 0; }
  .tipus-gomb { flex: none; display: grid; place-items: center; width: var(--magassag-suru); height: var(--magassag-suru); border-radius: var(--kerekites-kicsi); color: var(--szoveg-halvany); }
  .tipus-gomb:hover:not(:disabled) { background: var(--hatter-hover); color: var(--szoveg); }
  .tipus-menu { margin: var(--t-1) 0 var(--t-2); padding: var(--t-3); border: var(--keret-vastag) solid var(--keret); border-radius: var(--kerekites); background: var(--hatter); display: flex; flex-wrap: wrap; align-items: center; gap: var(--t-2); }
  .tipus-menu p { flex-basis: 100%; margin: 0; }
  .tipus-info { color: var(--szoveg-masodlagos); font-size: var(--betu-kicsi); }
  .tipus-hiba, .ervenytelen-info { display: flex; align-items: start; gap: var(--t-2); color: var(--hiba); font-size: var(--betu-kicsi); }
  .tipus-figyelmeztetes { display: flex; align-items: start; gap: var(--t-2); color: var(--figyelmeztetes); font-size: var(--betu-kicsi); }

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
