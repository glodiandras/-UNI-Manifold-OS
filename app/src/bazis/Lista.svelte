<!--
  A Bases List nézete (10-bases-02): soronként egy bejegyzés, felsorolásjellel, sorszámmal vagy jel nélkül. A bejegyzés főeleme a nézet
  első oszlopa (alapból a fájl neve); a további, nem üres tulajdonságok behúzott alpontok, vagy egy sorban az elválasztóval
  (`indentProperties`, `separator`, `markers`). A csoportfejlécek összecsukhatók (10-bases-06); 100-as adagokban rajzol.
-->
<script lang="ts">
  import { t } from '../lib/i18n';
  import Cella from './Cella.svelte';
  import CsoportFej from './CsoportFej.svelte';
  import { zartKulcs } from './csoportok';
  import { listaBeallitas } from './lista';
  import { oszlopNev } from './nevek';
  import type { Csoport, Ertek, Sor, Valasz } from './tipusok';

  interface Props {
    valasz: Valasz;
    ez?: string | null;
    /** az összecsukott csoportok (`zartKulcs`) és a váltásuk */
    zart?: ReadonlySet<string>;
    zartKapcsol?: (kulcs: string) => void;
  }
  let { valasz, ez = null, zart = new Set(), zartKapcsol }: Props = $props();

  const ADAG = 100;
  const beall = $derived(listaBeallitas(valasz.nezet?.beallitas));
  const nezetIndex = $derived(valasz.nezet?.index ?? 0);

  interface Blokk {
    cs: Csoport | null;
    kulcs: string;
    sorok: Sor[];
  }
  const blokkok = $derived.by((): Blokk[] => {
    if (!valasz.csoportok) return [{ cs: null, kulcs: '', sorok: valasz.sorok }];
    return valasz.csoportok.map((cs) => ({ cs, kulcs: zartKulcs(nezetIndex, cs.kulcs), sorok: valasz.sorok.slice(cs.tol, cs.tol + cs.db) }));
  });

  let darab = $state(ADAG);
  $effect(() => {
    void valasz.nezet?.index;
    darab = ADAG;
  });

  /** az adagolás: a blokkok sorai a `darab` korlátig (az összecsukott csoport sorai nem számítanak) */
  const latszo = $derived.by(() => {
    let maradt = darab;
    return blokkok.map((b) => {
      if (b.cs && zart.has(b.kulcs)) return { ...b, sorok: [] as Sor[], zart: true };
      const sorok = b.sorok.slice(0, Math.max(0, maradt));
      maradt -= sorok.length;
      return { ...b, sorok, zart: false };
    });
  });
  const hatra = $derived(
    blokkok.filter((b) => !(b.cs && zart.has(b.kulcs))).reduce((s, b) => s + b.sorok.length, 0) - latszo.reduce((s, b) => s + b.sorok.length, 0),
  );

  /** a főelem a nézet első oszlopa */
  const nevIdx = 0;
  const tobbi = (sor: Sor): Array<{ o: (typeof valasz.oszlopok)[number]; e: Ertek }> =>
    valasz.oszlopok
      .map((o, i) => ({ o, e: sor.cellak[i] ?? null }))
      .filter(({ e }, i) => i !== nevIdx && !(e === null || e === '' || (typeof e === 'object' && e.t === 'lista' && e.e.length === 0)));
</script>

<div class="gorgeto" role="group" aria-label={t('Lista')}>
  {#each latszo as b, bi (b.cs ? `c${b.cs.tol}-${bi}` : 'mind')}
    {#if b.cs}
      <h3 class="csoport">
        <CsoportFej cimke={b.cs.cimke} db={b.cs.db} zart={b.zart} kapcsol={() => zartKapcsol?.(b.kulcs)} />
      </h3>
    {/if}
    {#if !b.zart && b.sorok.length}
      {#if beall.jel === 'number'}
        <ol class="lista">{@render sorok(b.sorok)}</ol>
      {:else}
        <ul class="lista" class:jelnelkul={beall.jel === 'none'} role="list">{@render sorok(b.sorok)}</ul>
      {/if}
    {/if}
  {/each}
  {#if hatra > 0}
    <button type="button" class="tovabb" onclick={() => (darab += ADAG)}>{t('További {n} a(z) {hatra} közül', { n: Math.min(hatra, ADAG), hatra })}</button>
  {/if}
  {#if valasz.sorok.length === 0}
    <p class="ures" role="status">{t('Nincs a feltételeknek megfelelő fájl.')}</p>
  {/if}
</div>

{#snippet sorok(lista: Sor[])}
  {#each lista as sor (sor.ut)}
    {@const t2 = tobbi(sor)}
    <li class="elem" data-ut={sor.ut}>
      <span class="fo"><Cella ertek={sor.cellak[nevIdx] ?? null} forras={sor.ut} {ez} /></span>
      {#if t2.length && beall.behuzas}
        <ul class="alpont" role="list">
          {#each t2 as x (x.o.id)}
            <li><span class="felirat">{oszlopNev(x.o)}</span><span class="ertek"><Cella ertek={x.e} forras={sor.ut} {ez} /></span></li>
          {/each}
        </ul>
      {:else if t2.length}
        <span class="sorban">
          {#each t2 as x, i (x.o.id)}
            <span class="elv" aria-hidden="true">{i === 0 ? ' — ' : beall.elvalaszto}</span><span class="ertek" title={oszlopNev(x.o)}><Cella ertek={x.e} forras={sor.ut} {ez} /></span>
          {/each}
        </span>
      {/if}
    </li>
  {/each}
{/snippet}

<style>
  .gorgeto {
    flex: 1;
    min-height: 0;
    overflow: auto;
    padding: var(--t-3);
    font-size: var(--betu-ui);
    line-height: var(--sor-ui);
    color: var(--szoveg);
  }

  .csoport {
    margin: var(--t-3) 0 var(--t-1);
    font-size: var(--betu-ui);
  }

  .lista {
    margin: 0;
    padding-left: var(--t-5);
  }

  .lista.jelnelkul {
    list-style: none;
    padding-left: var(--t-1);
  }

  .elem {
    padding: 2px 0;
  }

  .fo {
    display: inline-flex;
    min-width: 0;
    font-weight: var(--suly-kozepes);
  }

  .sorban {
    color: var(--szoveg-masodlagos);
  }

  .sorban > * {
    display: inline-flex;
    vertical-align: bottom;
  }

  .elv {
    color: var(--szoveg-halvany);
    white-space: pre;
  }

  .alpont {
    margin: 0;
    padding-left: var(--t-5);
    list-style: none;
    color: var(--szoveg-masodlagos);
  }

  .alpont li {
    display: flex;
    gap: var(--t-2);
    min-width: 0;
    font-size: var(--betu-kicsi);
    line-height: var(--sor-kicsi);
  }

  .felirat {
    flex: none;
    color: var(--szoveg-halvany);
  }

  .ertek {
    display: inline-flex;
    min-width: 0;
  }

  .tovabb {
    display: block;
    margin: var(--t-4) auto 0;
    height: var(--magassag-gomb);
    padding: 0 var(--t-3);
    border: 1px solid var(--keret-mezo);
    border-radius: var(--kerekites-kicsi);
    background: transparent;
    color: var(--szoveg-masodlagos);
    font: inherit;
    cursor: pointer;
  }

  .tovabb:hover {
    background: var(--hatter-hover);
  }

  .ures {
    margin: var(--t-5) var(--t-4);
    color: var(--szoveg-halvany);
  }
</style>
