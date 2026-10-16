<!--
  Címkefa (C11b): a vault címkéi egymásba ágyazva (`Fizika/Mechanika`), számlálóval; egy címkére kattintva alatta a
  hozzá tartozó jegyzetek listája (a címke gyerekeivel együtt, a keresés `tag:` operátora). ARIA `tree` gördülő
  tabindexszel: ↑↓ lép, → kinyit / belép, ← becsuk / a szülőre lép, Home, End, ↩ vagy szóköz kijelöli a címkét (újra:
  megszünteti), a lista során ↩ megnyit, ⌘↩ új fülben. Az adatot a core adja (`/api/vault/cimkek`); a felület nem
  számol címkét.
-->
<script lang="ts">
  import { t, tk, tp, locale } from '../lib/i18n';
  import { onMount, tick } from 'svelte';
  import { ApiHiba, kerdez } from '../lib/core/api';
  import Ikon from '../lib/ikon/Ikon.svelte';
  import { ArrowUpDown, ChevronDown, ChevronRight, Tag, X } from '../lib/ikon/ikonok';
  import { kornyezet } from '../lib/kornyezet';
  import IkonGomb from '../lib/ui/IkonGomb.svelte';
  import JegyzetIkon from '../lib/ui/JegyzetIkon.svelte';
  import type { ListaRendezes } from '../lib/elrendezes/felulet.svelte';
  import { cimkeFa, cimkek } from '../lib/vault/cimkek.svelte';
  import { fajlNev, mappa } from '../lib/vault/fajlok.svelte';
  import { nyitasMod } from '../szerkeszto/linkek/navigacio';
  import { lebegoMenu } from '../szerkeszto/notion/menu';

  const { felulet, fajlok } = kornyezet();

  let nyitott = $state(new Set<string>());
  let kivalasztott = $state<string | null>(null);
  let fokuszKulcs = $state<string | null>(null);
  let fa: HTMLElement | undefined = $state();

  const RENDEZES: { id: ListaRendezes; nev: string }[] = [
    { id: 'nev', nev: tk('Címke neve (A–Z)') },
    { id: 'nev-forditott', nev: tk('Címke neve (Z–A)') },
    { id: 'db', nev: tk('Darabszám: csökkenő') },
    { id: 'db-forditott', nev: tk('Darabszám: növekvő') },
  ];
  const rendezes = $derived(felulet.oldalsav.cimkeRendezes ?? 'nev');
  const rendezesCim = $derived(t('Rendezés: {mod}', { mod: t(RENDEZES.find((r) => r.id === rendezes)?.nev ?? RENDEZES[0].nev) }));

  function rendezesMenu(e: MouseEvent) {
    const gomb = e.currentTarget as HTMLElement, r = gomb.getBoundingClientRect();
    const akciok = new Map(RENDEZES.map((m) => [m.id, () => { felulet.oldalsav.cimkeRendezes = m.id; }]));
    lebegoMenu({ focus: () => gomb.focus() }, r.left, r.bottom, RENDEZES.map((m) => ({ id: m.id, nev: t(m.nev), kijelolt: m.id === rendezes })), akciok, t('Címkék rendezése'));
  }

  const sorok = $derived(cimkeFa(cimkek.lista, nyitott, rendezes));
  const tabKulcs = $derived(sorok.some((s) => s.kis === fokuszKulcs) ? fokuszKulcs : (sorok[0]?.kis ?? null));
  const aktivUt = $derived(felulet.munkaterulet.aktivFul?.ut ?? null);

  onMount(() => {
    cimkek.megjelenik();
    return () => (cimkek.latszik = false);
  });

  // ------------------------------------------------------------------ a kijelölt címke jegyzetei

  let talalat = $state.raw<string[]>([]);
  let osszes = $state(0);
  let hiba = $state<string | null>(null);
  let betolt = $state(false);
  let sorszam = 0;

  async function listaTolt(kis: string | null) {
    const en = ++sorszam;
    if (!kis) {
      talalat = [];
      osszes = 0;
      hiba = null;
      return;
    }
    betolt = true;
    try {
      const d = await kerdez<{ osszes: number; talalatok: { ut: string }[] }>(
        `/api/vault/kereses?q=${encodeURIComponent(`tag:#${kis}`)}&limit=500`,
        { idokorlat: 8000 },
      );
      if (en !== sorszam) return;
      talalat = d.talalatok.map((t) => t.ut).sort((a, b) => fajlNev(a).localeCompare(fajlNev(b), locale(), { numeric: true }));
      osszes = d.osszes;
      hiba = null;
    } catch (e) {
      if (en !== sorszam) return;
      talalat = [];
      hiba = e instanceof ApiHiba && e.statusz === 503 ? t('Az index még épül…') : e instanceof Error ? e.message : String(e);
    } finally {
      if (en === sorszam) betolt = false;
    }
  }

  // a kijelölés és a vault változása (a címkelista frissülése) újratölti a listát
  $effect(() => {
    void cimkek.lista;
    void listaTolt(kivalasztott);
  });

  // ------------------------------------------------------------------ nyitás, kijelölés, billentyűk

  function valt(kis: string, nyit?: boolean) {
    const be = new Set(nyitott);
    if (nyit ?? !be.has(kis)) be.add(kis);
    else be.delete(kis);
    nyitott = be;
  }

  function sorElem(kis: string): HTMLElement | null {
    return fa ? ([...fa.querySelectorAll<HTMLElement>('[data-cimke]')].find((e) => e.dataset.cimke === kis) ?? null) : null;
  }

  async function fokuszra(kis: string) {
    fokuszKulcs = kis;
    await tick();
    const e = sorElem(kis);
    e?.focus();
    e?.scrollIntoView({ block: 'nearest' });
  }

  function kijelol(kis: string) {
    fokuszKulcs = kis;
    kivalasztott = kivalasztott === kis ? null : kis;
  }

  function billentyu(e: KeyboardEvent) {
    const sor = (e.target as HTMLElement).closest<HTMLElement>('[data-cimke]');
    if (!sor || e.isComposing) return;
    const i = sorok.findIndex((s) => s.kis === sor.dataset.cimke);
    if (i < 0) return;
    const cs = sorok[i];
    let kesz = true;
    if (e.key === 'ArrowDown') void fokuszra(sorok[Math.min(sorok.length - 1, i + 1)].kis);
    else if (e.key === 'ArrowUp') void fokuszra(sorok[Math.max(0, i - 1)].kis);
    else if (e.key === 'Home') void fokuszra(sorok[0].kis);
    else if (e.key === 'End') void fokuszra(sorok[sorok.length - 1].kis);
    else if (e.key === 'ArrowRight') {
      if (cs.van_gyerek && !nyitott.has(cs.kis)) valt(cs.kis, true);
      else if (cs.van_gyerek && sorok[i + 1]) void fokuszra(sorok[i + 1].kis);
    } else if (e.key === 'ArrowLeft') {
      if (cs.van_gyerek && nyitott.has(cs.kis)) valt(cs.kis, false);
      else if (cs.melyseg > 0) {
        const szulo = cs.kis.slice(0, cs.kis.lastIndexOf('/'));
        if (sorok.some((s) => s.kis === szulo)) void fokuszra(szulo);
      }
    } else if (e.key === 'Enter' || e.key === ' ') kijelol(cs.kis);
    else kesz = false;
    if (kesz) e.preventDefault();
  }

  function listaNyit(ut: string, e: MouseEvent | KeyboardEvent) {
    felulet.munkaterulet.megnyit(ut, nyitasMod(e));
  }

  const kivCsucs = $derived(cimkek.lista.find((c) => c.kis === kivalasztott));
</script>

<div class="cimkek">
  <div class="fej">
    <span class="cim">{cimkek.lista.length ? tp('{n} címke', cimkek.lista.length) : t('Címkék')}</span>
    <IkonGomb ikon={ArrowUpDown} cimke={rendezesCim} aria-haspopup="listbox" kicsi onclick={rendezesMenu} />
  </div>

  <div class="fa gorgeto" role="tree" aria-label={t('Címkék')} tabindex="-1" bind:this={fa} onkeydown={billentyu}>
    {#each sorok as s (s.kis)}
      <!-- a billentyűt a fa kezeli (↑↓←→ ↩ szóköz) -->
      <!-- svelte-ignore a11y_click_events_have_key_events -->
      <div
        class="sor"
        class:kijelolt={s.kis === kivalasztott}
        role="treeitem"
        aria-level={s.melyseg + 1}
        aria-selected={s.kis === kivalasztott}
        aria-expanded={s.van_gyerek ? nyitott.has(s.kis) : undefined}
        data-cimke={s.kis}
        tabindex={s.kis === tabKulcs ? 0 : -1}
        title={s.cimke}
        style:padding-left={`${8 + s.melyseg * 16}px`}
        onclick={() => kijelol(s.kis)}
        onfocus={() => (fokuszKulcs = s.kis)}
      >
        {#if s.van_gyerek}
          <button
            type="button"
            class="nyil"
            tabindex="-1"
            aria-label={nyitott.has(s.kis) ? t('Becsukás') : t('Kinyitás')}
            onclick={(e) => (e.stopPropagation(), valt(s.kis))}
          >
            <Ikon ikon={nyitott.has(s.kis) ? ChevronDown : ChevronRight} meret={14} />
          </button>
        {:else}
          <span class="nyil"></span>
        {/if}
        <Ikon ikon={Tag} meret={14} />
        <span class="nev">{s.nev}</span>
        <span class="db" title={s.db !== s.ossz ? t('{db} jegyzet ezzel a címkével, {ossz} a gyerekeivel együtt', { db: s.db, ossz: s.ossz }) : undefined}>{s.ossz}</span>
      </div>
    {:else}
      <p class="ures">
        {cimkek.hiba ?? (cimkek.betoltve ? t('A vaultban nincs címke.') : t('A címkék töltődnek…'))}
      </p>
    {/each}
  </div>

  {#if kivalasztott}
    <div class="lista-fej">
      <span class="lista-cim">
        <Ikon ikon={Tag} meret={14} />
        <strong>{kivCsucs?.cimke ?? kivalasztott}</strong>
        <span class="db">{osszes}</span>
      </span>
      <button type="button" class="zar" aria-label={t('A szűrés megszüntetése')} title={t('A szűrés megszüntetése')} onclick={() => (kivalasztott = null)}>
        <Ikon ikon={X} meret={14} />
      </button>
    </div>
    <ul class="lista gorgeto" aria-label={t('A címkéhez tartozó jegyzetek')}>
      {#each talalat as ut (ut)}
        <li>
          <button
            type="button"
            class="sor lista-sor"
            class:aktiv={ut === aktivUt}
            title={ut}
            onclick={(e) => listaNyit(ut, e)}
          >
            <JegyzetIkon {ut} tipus={fajlok.info(ut)?.tipus ?? 'md'} meret={14} />
            <span class="nev">{fajlNev(ut)}</span>
            {#if mappa(ut)}<span class="mappa">{mappa(ut)}</span>{/if}
          </button>
        </li>
      {:else}
        <li class="ures" role="status">{hiba ?? (betolt ? t('Betöltés…') : t('Nincs jegyzet ezzel a címkével.'))}</li>
      {/each}
    </ul>
  {/if}
</div>

<style>
  .cimkek {
    display: flex;
    flex-direction: column;
    height: 100%;
    min-height: 0;
  }

  .fej {
    flex: none;
    display: flex;
    align-items: center;
    justify-content: space-between;
    height: var(--magassag-sor);
    padding: 0 var(--t-3);
    color: var(--szoveg-halvany);
    font-size: var(--betu-kicsi);
  }

  .fa {
    flex: 1 1 50%;
    min-height: 0;
    padding: 0 var(--t-1) var(--t-2);
  }

  .sor {
    display: flex;
    align-items: center;
    gap: var(--t-1);
    width: 100%;
    height: var(--magassag-sor);
    padding-right: var(--t-2);
    border-radius: var(--kerekites);
    color: var(--szoveg-masodlagos);
    text-align: left;
    user-select: none;
    -webkit-user-select: none;
  }

  .sor:hover {
    background: var(--hatter-hover);
    color: var(--szoveg);
  }

  .sor:focus-visible {
    outline: var(--fokusz-vastag) solid var(--fokusz-gyuru);
    outline-offset: var(--fokusz-tav-befele);
  }

  .sor.kijelolt,
  .sor.aktiv {
    background: var(--hatter-kijelolt);
    color: var(--szoveg);
  }

  .nyil {
    flex: none;
    display: flex;
    align-items: center;
    justify-content: center;
    width: 14px;
    color: var(--szoveg-halvany);
  }

  .nev {
    flex: 1;
    min-width: 0;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .db {
    flex: none;
    font-size: var(--betu-kicsi);
    color: var(--szoveg-halvany);
    font-variant-numeric: tabular-nums;
  }

  .mappa {
    flex: none;
    max-width: 45%;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    font-size: var(--betu-kicsi);
    color: var(--szoveg-halvany);
  }

  .lista-fej {
    flex: none;
    display: flex;
    align-items: center;
    justify-content: space-between;
    height: var(--magassag-lista-sor);
    padding: 0 var(--t-2) 0 var(--t-3);
    border-top: var(--keret-vastag) solid var(--keret);
    font-size: var(--betu-ui);
  }

  .lista-cim {
    display: flex;
    align-items: center;
    gap: var(--t-2);
    min-width: 0;
    color: var(--szoveg-masodlagos);
  }

  .lista-cim strong {
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    font-weight: var(--suly-felkover);
    color: var(--szoveg);
  }

  .zar {
    display: grid;
    place-items: center;
    width: var(--magassag-suru);
    height: var(--magassag-suru);
    border-radius: var(--kerekites-kicsi);
    color: var(--szoveg-halvany);
  }

  .zar:hover {
    background: var(--hatter-hover);
    color: var(--szoveg);
  }

  .lista {
    flex: 1 1 50%;
    min-height: 0;
    margin: 0;
    padding: 0 var(--t-1) var(--t-2);
    list-style: none;
  }

  .lista-sor {
    padding-left: var(--t-2);
  }

  .ures {
    margin: var(--t-2) var(--t-3);
    color: var(--szoveg-halvany);
    font-size: var(--betu-kicsi);
    line-height: var(--sor-kicsi);
  }
</style>
