<!--
  Az útmutató egy szakasza (Learn more): a core által adott Markdown típusos blokkokból, szövegcsomópontokkal rajzolva (nincs HTML-
  beszúrás). Táblázat, lista, idézet, kódblokk és soron belüli jelölések; a fejléc a nézet saját fejléc-szintje alatt marad.
-->
<script lang="ts">
  import { blokkok, type Sor } from './dokuSzakasz';

  let { szoveg }: { szoveg: string } = $props();
  const lista = $derived(blokkok(szoveg));
</script>

{#snippet sor(s: Sor)}{#each s as r}{#if r.t === 'kod'}<code>{r.s}</code>{:else if r.t === 'felkover'}<strong>{r.s}</strong>{:else if r.t === 'dolt'}<em>{r.s}</em>{:else}{r.s}{/if}{/each}{/snippet}

<div class="doku" data-doku-szakasz>
  {#each lista as b}
    {#if b.t === 'cim'}
      <h4>{@render sor(b.sor)}</h4>
    {:else if b.t === 'bekezdes'}
      <p>{@render sor(b.sor)}</p>
    {:else if b.t === 'lista'}
      {#if b.rendezett}<ol>{#each b.elemek as e}<li>{@render sor(e)}</li>{/each}</ol>
      {:else}<ul>{#each b.elemek as e}<li>{@render sor(e)}</li>{/each}</ul>{/if}
    {:else if b.t === 'tabla'}
      <table>
        <thead><tr>{#each b.fejlec as c}<th scope="col">{@render sor(c)}</th>{/each}</tr></thead>
        <tbody>{#each b.sorok as r}<tr>{#each r as c}<td>{@render sor(c)}</td>{/each}</tr>{/each}</tbody>
      </table>
    {:else if b.t === 'idezet'}
      <blockquote>{#each b.sorok as r}<p>{@render sor(r)}</p>{/each}</blockquote>
    {:else}
      <pre>{b.szoveg}</pre>
    {/if}
  {/each}
</div>

<style>
  .doku { display: flex; flex-direction: column; gap: var(--t-2); font-size: var(--betu-ui); }
  p, h4, ul, ol, table, blockquote, pre { margin: 0; }
  h4 { font-size: var(--betu-torzs); font-weight: var(--suly-kozepes); }
  ul, ol { padding-left: var(--t-5); display: flex; flex-direction: column; gap: var(--t-1); }
  table { border-collapse: collapse; }
  th, td { text-align: left; padding: var(--t-1) var(--t-3); border: var(--keret-vastag) solid var(--keret); vertical-align: top; }
  th { font-weight: var(--suly-kozepes); color: var(--szoveg-masodlagos); }
  blockquote { padding-left: var(--t-3); border-left: var(--keret-vastag) solid var(--keret); color: var(--szoveg-masodlagos); display: flex; flex-direction: column; gap: var(--t-1); }
  code { font-family: var(--betu-mono); font-size: var(--betu-kicsi); }
  pre { padding: var(--t-3); background: var(--hatter-kod); color: var(--kod-szoveg); font-family: var(--betu-mono); font-size: var(--betu-kicsi); overflow-x: auto; }
</style>
