<!--
  Egy canvas-kártya (C14): a node helye és mérete világkoordinátában (a szülő réteg transzformál), a színe, a tartalma
  típusonként (szöveg, jegyzet, kép, hang/videó, PDF és más fájl, link, csoport). A tartalom csak „részletes”
  állapotban rajzolódik (látható, és a nagyítás elég nagy); a fájl változására (`frissites`) újrarajzol. A húzás, a
  kijelölés és a szerkesztés a `Vaszon`-é: a kártya csak jelöli a fogókat (`data-fogo`, `data-kapcs`).
-->
<script lang="ts">
  import { t } from '../lib/i18n';
  import Ikon from '../lib/ikon/Ikon.svelte';
  import { fajlIkon, TIPUS_NEV } from '../lib/ikon/fajlIkon';
  import { fajlNev } from '../lib/vault/fajlok.svelte';
  import { kepVodor } from '../szerkeszto/beagyazas/nagyito';
  import { sima } from './beagyazas';
  import { FOGOK } from './geometria';
  import { OLDALAK, szinCss, type Csomopont } from './modell';
  import { fajlTipus, jegyzetRajzol, kepRajzol, linkRajzol, mediaRajzol, szovegRajzol } from './tartalom';

  let {
    c,
    canvasUt,
    kijelolt = false,
    fogok = false,
    kapcsolhato = false,
    reszletes = false,
    z = 1,
    frissites = 0,
    letezik = true,
    szerkeszt = false,
    szerkesztoHely,
    onfokusz,
  }: {
    c: Csomopont;
    canvasUt: string;
    kijelolt?: boolean;
    /** az átméretező és az él-fogók (egyetlen kijelölt node, írható canvas) */
    fogok?: boolean;
    /** az él-fogók az oldalakon (írható canvas; rámutatásra és kijelöléskor látszanak) */
    kapcsolhato?: boolean;
    reszletes?: boolean;
    z?: number;
    frissites?: number;
    /** a fájl-kártya célja létezik-e a vaultban */
    letezik?: boolean;
    /** a szövegkártya szerkesztés alatt áll (a szerkesztőt a `szerkesztoHely` csatolja) */
    szerkeszt?: boolean;
    szerkesztoHely?: (el: HTMLElement) => () => void;
    onfokusz?: (id: string) => void;
  } = $props();

  let torzs: HTMLElement | undefined = $state();
  let szerkHely: HTMLElement | undefined = $state();

  const tipus = $derived(c.type === 'file' && typeof c.file === 'string' ? fajlTipus(c.file) : null);
  const szin = $derived(szinCss(c.color));
  const nev = $derived(
    c.type === 'file'
      ? fajlNev(String(c.file ?? ''))
      : c.type === 'link'
        ? String(c.url ?? '')
        : c.type === 'group'
          ? String(c.label ?? '')
          : c.type === 'text'
            ? sima(String(c.text ?? '').split('\n', 1)[0]).slice(0, 80)
            : c.type,
  );
  const cimke = $derived(
    c.type === 'file'
      ? t('{tipus}: {nev}', { tipus: tipus ? t(TIPUS_NEV[tipus]) : t('fájl'), nev })
      : c.type === 'text'
        ? t('Szövegkártya: {nev}', { nev: nev || t('üres') })
        : c.type === 'link'
          ? t('Link: {nev}', { nev })
          : c.type === 'group'
            ? t('Csoport: {nev}', { nev: nev || t('névtelen') })
            : t('Ismeretlen kártya ({tipus})', { tipus: c.type }),
  );
  // a kép vödre a képernyőn mért szélességből: csak a vödör változására töltődik újra
  const vodor = $derived(tipus === 'kep' ? kepVodor(c.width * z, typeof window === 'undefined' ? 1 : window.devicePixelRatio || 1) : 0);

  $effect(() => {
    const el = torzs;
    if (!el || szerkeszt) return;
    void frissites;
    if (!reszletes || c.type === 'group') {
      el.replaceChildren();
      return;
    }
    if (c.type === 'text') return szovegRajzol(el, String(c.text ?? ''), canvasUt);
    if (c.type === 'link') return linkRajzol(el, String(c.url ?? ''));
    if (c.type !== 'file' || !letezik) {
      el.replaceChildren();
      return;
    }
    const ut = String(c.file ?? '');
    if (tipus === 'md') return jegyzetRajzol(el, ut, typeof c.subpath === 'string' ? c.subpath : undefined, canvasUt);
    if (tipus === 'kep') return kepRajzol(el, ut, vodor);
    if (tipus === 'video' || tipus === 'hang') return mediaRajzol(el, ut, tipus);
    el.replaceChildren();
  });

  $effect(() => {
    if (szerkeszt && szerkHely && szerkesztoHely) return szerkesztoHely(szerkHely);
  });
</script>

<!-- svelte-ignore a11y_no_noninteractive_tabindex (a kártya a vászon billentyűs útja: Tab lép, ↩ szerkeszt/megnyit) -->
<div
  class="kartya tipus-{c.type}"
  class:kijelolt
  class:szines={!!szin}
  class:hianyzik={c.type === 'file' && !letezik}
  class:szerkeszt
  data-id={c.id}
  style:left="{c.x}px"
  style:top="{c.y}px"
  style:width="{c.width}px"
  style:height="{c.height}px"
  style:--szin={szin}
  style:--szin-hatter={szin && c.color && /^[1-6]$/.test(c.color) ? `var(--canvas-szin-${c.color}-hatter)` : null}
  role="group"
  aria-label={kijelolt ? t('{cimke} (kijelölve)', { cimke }) : cimke}
  tabindex="0"
  onfocus={() => onfokusz?.(c.id)}
>
  {#if c.type === 'file'}
    <div class="kartya-cim" title={String(c.file ?? '')}>
      <Ikon ikon={fajlIkon(tipus ?? 'egyeb')} meret={14} />
      <span>{nev}{typeof c.subpath === 'string' && c.subpath ? ` › ${c.subpath.replace(/^#\^?/, '')}` : ''}</span>
    </div>
  {:else if c.type === 'group'}
    <div class="csoport-cimke" data-cimke>{nev}</div>
  {/if}

  {#if szerkeszt}
    <div class="kartya-torzs kartya-szerk szerkeszto" bind:this={szerkHely}></div>
  {:else}
    <div class="kartya-torzs" class:gorgetheto={reszletes && (tipus === 'md' || c.type === 'text')} bind:this={torzs}></div>
  {/if}

  {#if c.type === 'file' && !letezik}
    <div class="kartya-uzenet hiba">{t('Nem található: {fajl}', { fajl: String(c.file ?? '') })}</div>
  {:else if c.type === 'file' && reszletes && tipus !== 'md' && tipus !== 'kep' && tipus !== 'video' && tipus !== 'hang'}
    <div class="kartya-uzenet"><Ikon ikon={fajlIkon(tipus ?? 'egyeb')} meret={20} /><span>{nev}</span></div>
  {:else if !reszletes && c.type !== 'group'}
    <div class="kartya-vazlat">{nev}</div>
  {/if}

  {#if fogok}
    {#each FOGOK as f (f)}
      <span class="fogo fogo-{f}" data-fogo={f} aria-hidden="true"></span>
    {/each}
  {/if}
  {#if kapcsolhato}
    {#each OLDALAK as o (o)}
      <span class="kapcs kapcs-{o}" data-kapcs={o} aria-hidden="true" title={t('Húzd egy másik kártyára: új él')}></span>
    {/each}
  {/if}
</div>
