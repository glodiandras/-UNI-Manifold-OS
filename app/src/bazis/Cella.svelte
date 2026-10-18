<!--
  Egy cella értéke (C12): a core típusos JSON-értékéből szöveg, címke, link, jelölőnégyzet. Csak olvas; a
  cellaszerkesztés a C12b-ben ide (a `CellaSzerkeszto`-ba) kapcsolódik. A link a core feloldását használja
  (`link.ut`), a kattintás ugyanúgy nyit, mint a jegyzetben: ⌘ új fül, ⌘⌥ osztás, feloldatlan linknél új jegyzet.
-->
<script lang="ts">
  import { t } from '../lib/i18n';
  import Ikon from '../lib/ikon/Ikon.svelte';
  import { Check } from '../lib/ikon/ikonok';
  import { linkek } from '../lib/vault/linkek.svelte';
  import { kulsoLink } from '../szerkeszto/linkek/kulso';
  import { linkMegnyit, nyitasMod } from '../szerkeszto/linkek/navigacio';
  import Cella from './Cella.svelte';
  import { datumSzoveg, ertekSzoveg, fajta, szamSzoveg } from './ertek';
  import { biztosKepUt, biztosSzin, htmlBeszur, ikonKeres } from './gazdagCella';
  import type { Ertek } from './tipusok';

  /** `forras`: a sor fájlja (a feloldatlan link ebből jön létre); `ez`: a nézetet tartalmazó fájl (`this`): a már
   *  feloldott link a teljes útjával ebből nyílik, így a sor saját fájljára mutató link is navigál (nem „önlink”). */
  let { ertek, forras, ez = null }: { ertek: Ertek; forras: string; ez?: string | null } = $props();
  const f = $derived(fajta(ertek));
  const tv = $derived(ertek !== null && typeof ertek === 'object' ? ertek : null);

  /** a `kep()` értékének vault-helyi képútja (a külső URL és a szabálytalan út nem tölthető); a média-URL a core tokenes végpontjáról jön */
  const kepSzin = $derived(tv?.t === 'kep' ? biztosSzin(tv.szin) : null);
  const kepUt = $derived(tv?.t === 'kep' ? biztosKepUt(tv.ut) : null);
  let kepSrc = $state<string | null>(null);
  $effect(() => {
    const ut = kepUt;
    let el = true;
    if (ut) void linkek.mediaUrl(ut, 96).then((u) => el && (kepSrc = u), () => el && (kepSrc = null));
    else kepSrc = null;
    return () => {
      el = false;
    };
  });
  const ikon = $derived(tv?.t === 'ikon' ? ikonKeres(tv.nev) : null);

  /** a szanitizált HTML-be a cellában csak a külső link kattintható (a héj megnyitója; `href` nincs) */
  function htmlAkcio(node: HTMLElement, forras: string) {
    htmlBeszur(node, forras);
    return {
      update: (uj: string) => htmlBeszur(node, uj),
      destroy: () => node.replaceChildren(),
    };
  }

  function htmlKattint(e: MouseEvent) {
    const a = (e.target as Element | null)?.closest<HTMLElement>('[data-url]');
    if (!a?.dataset.url) return;
    e.preventDefault();
    e.stopPropagation();
    kulsoLink(a.dataset.url);
  }

  function linkKattint(e: MouseEvent, l: { cel: string; ut: string | null; alcel?: string; kulso?: boolean }) {
    e.preventDefault();
    e.stopPropagation();
    if (l.kulso) {
      kulsoLink(l.cel);
      return;
    }
    void linkMegnyit({ forras: l.ut ? (ez ?? forras) : forras, cel: l.ut ?? l.cel, alcel: l.alcel ?? null }, nyitasMod(e));
  }
</script>

{#if f === 'ures'}
  <span class="ures"></span>
{:else if f === 'logikai'}
  <span class="m-jelolo jelolo" class:be={ertek === true} role="img" aria-label={ertek ? t('igen') : t('nem')}>
    {#if ertek}<Ikon ikon={Check} meret={14} />{/if}
  </span>
{:else if f === 'szam'}
  <span class="szam">{szamSzoveg(ertek as number)}</span>
{:else if f === 'szoveg'}
  <span class="szoveg" title={ertek as string}>{ertek}</span>
{:else if tv?.t === 'lista'}
  <span class="lista">
    {#each tv.e as x, i (i)}
      <span class="elem"><Cella ertek={x} {forras} {ez} /></span>
    {/each}
  </span>
{:else if tv?.t === 'datum'}
  <span class="datum" title={tv.iso}>{datumSzoveg(tv.iso, tv.ido)}</span>
{:else if tv?.t === 'link'}
  <a
    class="link"
    class:hianyzo={!tv.ut && !tv.kulso}
    href={tv.kulso ? tv.cel : '#'}
    title={tv.alcel ? `${tv.cel} › ${tv.alcel}` : tv.cel}
    onclick={(e) => linkKattint(e, tv)}>{tv.nev}{tv.alcel ? ` › ${tv.alcel}` : ''}</a
  >
{:else if tv?.t === 'cimke'}
  <span class="cimke">{tv.v}</span>
{:else if tv?.t === 'hiba'}
  <span class="hiba" title={tv.u}>{t('Hiba')}</span>
{:else if tv?.t === 'kep'}
  {#if kepSzin}
    <span class="szin" role="img" aria-label={kepSzin} title={kepSzin} style:background={kepSzin}></span>
  {:else if kepUt && kepSrc}
    <img class="kep" src={kepSrc} alt="" title={kepUt} decoding="async" loading="lazy" />
  {:else if tv.url}
    <span class="szoveg kulso" title={tv.url}>{t('külső kép — nem tölthető be')}</span>
  {:else}
    <span class="szoveg" title={ertekSzoveg(ertek)}>{ertekSzoveg(ertek)}</span>
  {/if}
{:else if tv?.t === 'ikon'}
  {#if ikon}
    <span class="ikon-cella" role="img" aria-label={tv.nev} title={tv.nev}><Ikon {ikon} meret={14} /></span>
  {:else}
    <span class="szoveg" title={tv.nev}>{tv.nev}</span>
  {/if}
{:else if tv?.t === 'html'}
  <!-- svelte-ignore a11y_no_static_element_interactions, a11y_click_events_have_key_events -->
  <span class="html" title={ertekSzoveg(ertek)} use:htmlAkcio={tv.v} onclick={htmlKattint}></span>
{:else}
  <span class="szoveg" title={ertekSzoveg(ertek)}>{ertekSzoveg(ertek)}</span>
{/if}

<style>
  .szam {
    font-variant-numeric: tabular-nums;
  }

  .szoveg,
  .szam,
  .datum,
  .link {
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    min-width: 0;
  }

  .datum {
    font-variant-numeric: tabular-nums;
  }

  .link {
    color: var(--akcent-szoveg);
    text-decoration: none;
    cursor: pointer;
  }

  .link:hover {
    text-decoration: underline;
  }

  .link.hianyzo {
    color: var(--szoveg-halvany);
    text-decoration: underline dotted;
  }

  .lista {
    display: inline-flex;
    gap: var(--t-1);
    min-width: 0;
    overflow: hidden;
  }

  .elem {
    flex: none;
    max-width: 14em;
    padding: 0 var(--t-1);
    border-radius: var(--kerekites-kicsi);
    background: var(--hatter-hover);
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .cimke {
    color: var(--akcent-szoveg);
  }

  .hiba {
    color: var(--hiba);
  }

  .szin {
    flex: none;
    width: var(--t-4);
    height: var(--t-4);
    border: var(--keret-vastag) solid var(--keret-eros);
    border-radius: var(--kerekites-kicsi);
  }

  .kep {
    flex: none;
    max-width: 100%;
    max-height: 100%;
    object-fit: contain;
    border-radius: var(--kerekites-kicsi);
  }

  .kulso {
    color: var(--szoveg-halvany);
  }

  .ikon-cella {
    display: inline-flex;
    color: var(--szoveg-masodlagos);
  }

  .html {
    display: inline-block;
    min-width: 0;
    max-width: 100%;
    max-height: 100%;
    overflow: hidden;
  }

  .html :global(a[data-url]) {
    color: var(--akcent-szoveg);
    cursor: pointer;
    text-decoration: underline;
  }

</style>
