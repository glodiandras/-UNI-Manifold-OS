<!--
  A jegyzet borítóképe (C11b): a frontmatter `cover` kulcsa, sávként a tulajdonság-panel fölött. A képfájlt a core oldja fel
  (wikilink vagy fájlnév), a kép a megjelenített szélességnek megfelelő változatban jön (`?w=`). A külső URL a CSP miatt
  nem tölthető be: ilyenkor a sáv helyén egy halvány jelzés áll.
-->
<script lang="ts">
  import { t } from '../../lib/i18n';
  import { ikonFajta, ikonok } from '../../lib/vault/ikonok.svelte';
  import { linkek } from '../../lib/vault/linkek.svelte';

  let { ut }: { ut: string } = $props();

  const adat = $derived(ikonok.kap(ut)?.cover);
  const f = $derived(ikonFajta(adat));
  let src = $state<string | null>(null);

  $effect(() => {
    const kep = adat?.ut && /\.(png|jpe?g|gif|webp|avif|svg|bmp|tiff?|heic)$/i.test(adat.ut) ? adat.ut : null;
    let el = true;
    if (!kep) src = null;
    else void linkek.mediaUrl(kep, 1600).then((u) => el && (src = u));
    return () => {
      el = false;
    };
  });
</script>

{#if adat && f.fajta === 'kep' && src}
  <div class="boritok"><img {src} alt={t('A jegyzet borítóképe')} decoding="async" /></div>
{:else if adat}
  <p class="nincs" title={adat.ertek}>{t('Borítókép: {ertek} — nem tölthető be (csak a vaultban álló kép jeleníthető meg).', { ertek: adat.ertek })}</p>
{/if}

<style>
  .boritok {
    flex: none;
    height: 160px;
    overflow: hidden;
    background: var(--hatter-oldalsav);
  }

  .boritok img {
    display: block;
    width: 100%;
    height: 100%;
    object-fit: cover;
  }

  .nincs {
    flex: none;
    margin: 0;
    padding: var(--t-1) var(--t-4);
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    background: var(--hatter-oldalsav);
    color: var(--szoveg-halvany);
    font-size: var(--betu-kicsi);
    line-height: var(--sor-kicsi);
  }
</style>
