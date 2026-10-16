<!--
  Lista-értékű tulajdonság (címkék, forrás, NN, aliasok): chipek × gombbal, és egy bevitelmező az új elemnek
  (↩ vagy vessző hozzáad; üres mezőben a Backspace az utolsó chipet törli). A wikilink elemek link-chipek: kattintásra
  megnyílnak (⌘ új fül, ⌘⌥ osztás). A módosítást a hívó írja be (a core ellenőrzi a sémát); itt csak a bevitel van.
  A bevitelmező gépelés közben javasol (`javasol`: a vault címkéi, a séma értékkészlete, link-mezőnél a fájlok): a
  kiemelt javaslatot az ↩ vagy a Tab veszi fel, erős találat nélkül az ↩ a gépelt szöveget.
-->
<script lang="ts">
  import { t } from '../../lib/i18n';
  import Ikon from '../../lib/ikon/Ikon.svelte';
  import { X } from '../../lib/ikon/ikonok';
  import { wikiReszek } from './ertek';
  import type { JavaslatElem, JavaslatLista } from './javaslat';
  import JavaslatMezo from './JavaslatMezo.svelte';

  let {
    elemek,
    cimke,
    irhato,
    link = false,
    onvaltozas,
    onnyit,
    javasol,
  }: {
    elemek: string[];
    cimke: string;
    irhato: boolean;
    /** a bevitt név wikilinkké alakul (NN, Source) */
    link?: boolean;
    onvaltozas: (uj: string[]) => void;
    onnyit?: (nyers: string, e: MouseEvent) => void;
    /** a gépelés közbeni javaslatok (a meglévő elemek nélkül) */
    javasol?: (q: string) => JavaslatLista | Promise<JavaslatLista>;
  } = $props();

  let bevitel = $state('');

  function hozzaad(): boolean {
    const t = bevitel.trim();
    if (!t) return false;
    bevitel = '';
    onvaltozas([...elemek, link && !wikiReszek(t) ? `[[${t}]]` : t]);
    return true;
  }

  /** A kiválasztott javaslat új elemként; a link a core link-céljával (`feloldas`), a gépelt horgony megmarad. */
  async function javaslatValaszt(e: JavaslatElem) {
    bevitel = '';
    const ertek = e.feloldas ? await e.feloldas() : e.ertek;
    if (ertek && !elemek.includes(ertek)) onvaltozas([...elemek, ertek]);
  }

  const nincsJavaslat = () => ({ elemek: [], eros: false });

  function billentyu(e: KeyboardEvent) {
    if (e.key === 'Enter' || e.key === ',') {
      if (bevitel.trim()) {
        e.preventDefault();
        hozzaad();
      } else if (e.key === ',') e.preventDefault();
    } else if (e.key === 'Backspace' && bevitel === '' && elemek.length) {
      e.preventDefault();
      onvaltozas(elemek.slice(0, -1));
    }
  }
</script>

<ul class="lista" aria-label={cimke}>
  {#each elemek as e, i (`${i}:${e}`)}
    {@const w = wikiReszek(e)}
    <li class="chip" class:link={!!w}>
      {#if w && onnyit}
        <button type="button" class="szoveg nyit" title={e} onclick={(ev) => onnyit?.(e, ev)}>{w.felirat}</button>
      {:else}
        <span class="szoveg" title={e}>{w ? w.felirat : e}</span>
      {/if}
      {#if irhato}
        <button type="button" class="torol" aria-label={t('{e} eltávolítása', { e })} onclick={() => onvaltozas(elemek.filter((_, j) => j !== i))}>
          <Ikon ikon={X} meret={14} />
        </button>
      {/if}
    </li>
  {/each}
  {#if irhato}
    <li class="uj">
      <JavaslatMezo
        size={1}
        osztaly="bevitel"
        cimke={t('{cimke}: új elem', { cimke })}
        placeholder={elemek.length ? '+' : t('Új elem')}
        bind:value={bevitel}
        javasol={javasol ?? nincsJavaslat}
        onvalaszt={(e) => void javaslatValaszt(e)}
        onkeydown={billentyu}
        onblur={() => void hozzaad()}
      />
    </li>
  {/if}
</ul>

<style>
  .lista {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: var(--t-1);
    min-width: 0;
    margin: 0;
    padding: 0;
    list-style: none;
  }

  .chip {
    display: inline-flex;
    align-items: center;
    max-width: 100%;
    height: var(--magassag-suru);
    padding: 0 var(--t-1) 0 var(--t-2);
    border-radius: var(--kerekites-kicsi);
    background: var(--hatter-aktiv);
    color: var(--szoveg);
    font-size: var(--betu-kicsi);
    line-height: var(--sor-kicsi);
  }

  .chip.link {
    color: var(--akcent-szoveg);
  }

  .szoveg {
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .nyit {
    padding: 0;
    color: inherit;
  }

  .nyit:hover {
    text-decoration: underline;
  }

  .torol {
    display: grid;
    place-items: center;
    width: 18px;
    height: 18px;
    margin-left: 2px;
    border-radius: var(--kerekites-kicsi);
    color: var(--szoveg-halvany);
  }

  .torol:hover {
    background: var(--hatter-hover);
    color: var(--szoveg);
  }

  .uj {
    flex: 1 1 80px;
    min-width: 80px;
  }

  .uj :global(.bevitel) {
    width: 100%;
    min-width: 0;
    height: var(--magassag-suru);
    padding: 0 var(--t-1);
    border: 0;
    background: transparent;
    font-size: var(--betu-ui);
  }

  .uj :global(.bevitel::placeholder) {
    color: var(--szoveg-halvany);
  }

  .uj :global(.bevitel:focus-visible) {
    outline-offset: 0;
    border-radius: var(--kerekites-kicsi);
  }
</style>
