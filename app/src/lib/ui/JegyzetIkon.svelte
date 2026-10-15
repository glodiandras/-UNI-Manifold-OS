<!--
  A jegyzet ikonja (C11b): a frontmatter `icon` kulcsa (emoji vagy a core által feloldott képfájl), ennek hiányában a
  fájltípus szerinti Lucide-ikon. A fülön, a fájlfában, a keresőpanelben és a szerkesztő morzsájában ugyanez jelenik meg.
-->
<script lang="ts">
  import { fajlIkon } from '../ikon/fajlIkon';
  import Ikon from '../ikon/Ikon.svelte';
  import type { FajlTipus } from '../vault/fajlok.svelte';
  import { ikonFajta, ikonok } from '../vault/ikonok.svelte';
  import { linkek } from '../vault/linkek.svelte';

  let { ut, tipus, meret = 14 }: { ut: string | null | undefined; tipus: FajlTipus | undefined; meret?: 14 | 16 | 20 } = $props();

  const f = $derived(ikonFajta(ikonok.kap(ut)?.icon));
  let src = $state<string | null>(null);

  $effect(() => {
    const kep = f.fajta === 'kep' ? f.szoveg : null;
    let el = true;
    if (!kep) src = null;
    else void linkek.mediaUrl(kep, meret * 4).then((u) => el && (src = u));
    return () => {
      el = false;
    };
  });
</script>

{#if f.fajta === 'emoji'}
  <span class="emoji" style:font-size="{meret}px" style:width="{meret}px" style:height="{meret}px" aria-hidden="true">{f.szoveg}</span>
{:else if f.fajta === 'kep' && src}
  <img class="kep" {src} alt="" width={meret} height={meret} decoding="async" />
{:else}
  <Ikon ikon={fajlIkon(tipus, ut)} {meret} />
{/if}

<style>
  .emoji {
    flex: none;
    display: grid;
    place-items: center;
    line-height: 1;
    overflow: hidden;
  }

  .kep {
    flex: none;
    display: block;
    object-fit: cover;
    border-radius: var(--kerekites-jel);
  }
</style>
