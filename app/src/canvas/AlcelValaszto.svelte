<!--
  A jegyzetkártya fejezetének vagy blokkjának választója (09-canvas-13): ugyanaz a lista, mint a `[[jegyzet#` kiegészítésé
  (a core fejezet-listája és a jegyzet `^blokk` azonosítói). A választás a kártya `subpath`-ja (a spec szerint `#`-tel
  kezdődik); az „Egész jegyzet” törli a kulcsot. PDF-nél oldalszám (`#page=N`), Basesnél a nézet neve szabad szövegként.
  Az Esc és a bezárás nem változtat semmit.
-->
<script lang="ts">
  import { onMount } from 'svelte';
  import { ApiHiba, kerdez } from '../lib/core/api';
  import { t } from '../lib/i18n';
  import Ikon from '../lib/ikon/Ikon.svelte';
  import { Hash, TriangleAlert } from '../lib/ikon/ikonok';
  import Atfedes from '../lib/ui/Atfedes.svelte';
  import ListaValaszto from '../lib/ui/ListaValaszto.svelte';
  import { fajlNev } from '../lib/vault/fajlok.svelte';

  let {
    ut,
    tipus,
    jelenlegi = '',
    onvalaszt,
    onbezar,
  }: {
    ut: string;
    tipus: 'md' | 'pdf' | 'base';
    /** a kártya mostani `subpath`-ja */
    jelenlegi?: string;
    /** a választott `subpath` (üres szöveg: az egész) */
    onvalaszt: (subpath: string) => void;
    onbezar: () => void;
  } = $props();

  interface Elem {
    kulcs: string;
    nev: string;
    jelzo: string;
    ertek: string;
  }

  const LIMIT = 200;
  let lekerdezes = $state('');
  let fejezetek = $state<Elem[]>([]);
  let blokkok = $state<Elem[]>([]);
  let hiba = $state<string | null>(null);
  let betoltve = $state(false);

  onMount(() => {
    if (tipus !== 'md') {
      betoltve = true;
      return;
    }
    let el = true;
    void (async () => {
      try {
        const j = await kerdez<{ fejezetek?: { szint: number; szoveg: string }[] }>(`/api/vault/jegyzet?ut=${encodeURIComponent(ut)}`, { idokorlat: 5000 });
        if (!el) return;
        fejezetek = (j.fejezetek ?? []).slice(0, LIMIT).map((f, i) => ({ kulcs: `h${i}`, nev: f.szoveg, jelzo: `H${f.szint}`, ertek: `#${f.szoveg}` }));
        const f = await kerdez<{ tartalom: string }>(`/api/vault/fajl?ut=${encodeURIComponent(ut)}`, { idokorlat: 5000 });
        if (!el) return;
        const lista: Elem[] = [];
        for (const sor of f.tartalom.split(/\r?\n/)) {
          const m = /^(.*?)\s\^([A-Za-z0-9-]+)\s*$/.exec(sor);
          if (m && lista.length < LIMIT) lista.push({ kulcs: `b${lista.length}`, nev: m[1].trim() || `^${m[2]}`, jelzo: `^${m[2]}`, ertek: `#^${m[2]}` });
        }
        blokkok = lista;
      } catch (e) {
        if (el) hiba = e instanceof ApiHiba ? e.message : String(e);
      } finally {
        if (el) betoltve = true;
      }
    })();
    return () => {
      el = false;
    };
  });

  const egesz: Elem = { kulcs: 'egesz', nev: t('Whole note'), jelzo: '', ertek: '' };

  const elemek = $derived.by((): Elem[] => {
    const q = lekerdezes.trim();
    const ki: Elem[] = [];
    const szuro = (e: Elem) => !q || `${e.nev} ${e.jelzo}`.toLowerCase().includes(q.toLowerCase());
    if (tipus === 'md') {
      if (!q) ki.push(egesz);
      ki.push(...fejezetek.filter(szuro), ...blokkok.filter(szuro));
    } else {
      ki.push({ ...egesz, nev: tipus === 'pdf' ? t('Whole document') : t('Default view') });
      if (q) {
        const szam = /^\d+$/.test(q);
        ki.push({
          kulcs: 'sajat',
          nev: tipus === 'pdf' ? (szam ? t('Page {n}', { n: q }) : t('Use “{szoveg}”', { szoveg: q })) : t('View “{szoveg}”', { szoveg: q }),
          jelzo: '',
          ertek: tipus === 'pdf' ? (szam ? `#page=${q}` : `#${q}`) : `#${q}`,
        });
      }
    }
    return ki;
  });

  const cim = $derived(
    tipus === 'md' ? t('Heading or block of {nev}', { nev: fajlNev(ut) }) : tipus === 'pdf' ? t('Page of {nev}', { nev: fajlNev(ut) }) : t('View of {nev}', { nev: fajlNev(ut) }),
  );
  const ures = $derived(!betoltve ? t('Loading…') : t('No heading or block matches “{kif}”', { kif: lekerdezes.trim() }));
</script>

<Atfedes cimke={cim} nev="canvas-alcel" {onbezar}>
  {#if hiba}
    <p class="alcel-hiba" role="alert"><Ikon ikon={TriangleAlert} meret={16} /><span>{t('The list could not be loaded: {hiba}', { hiba })} {t('You can still choose the whole note.')}</span></p>
  {/if}
  <ListaValaszto
    {elemek}
    kulcs={(e) => e.kulcs}
    bind:lekerdezes
    helyorzo={tipus === 'md' ? t('Search headings and blocks…') : tipus === 'pdf' ? t('Page number…') : t('View name…')}
    cimke={cim}
    {ures}
    onvalaszt={(e) => onvalaszt(e.ertek)}
    {onbezar}
  >
    {#snippet sor(e: Elem)}
      <span class="ikon"><Ikon ikon={Hash} meret={16} /></span>
      <span class="nev" class:valasztott={e.ertek === jelenlegi}>{e.nev}</span>
      <span class="jelzo">{e.jelzo}</span>
    {/snippet}
    {#snippet lablec()}
      <span><kbd>↑↓</kbd> {t('choose')}</span>
      <span><kbd>↩</kbd> {t('apply')}</span>
      <span><kbd>esc</kbd> {t('keep as is')}</span>
    {/snippet}
  </ListaValaszto>
</Atfedes>

<style>
  .ikon {
    color: var(--szoveg-halvany);
  }

  .nev {
    flex: 1 1 auto;
    min-width: 0;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .nev.valasztott {
    font-weight: var(--suly-felkover);
  }

  .jelzo {
    flex: none;
    color: var(--szoveg-halvany);
    font-size: var(--betu-kicsi);
  }

  .alcel-hiba {
    display: flex;
    align-items: center;
    gap: var(--t-2);
    margin: 0;
    padding: var(--t-2) var(--t-3);
    color: var(--hiba);
    background: var(--hiba-hatter);
    font-size: var(--betu-kicsi);
  }

  kbd {
    color: var(--szoveg-masodlagos);
  }
</style>
