<!--
  Rendezés-szerkesztő (10-bases-04): a nézet `sort` kulcsai minden elrendezéshez (Táblázat, Kártyák, Lista, Kanban). Soronként:
  tulajdonság, irány, prioritás (↑↓) és törlés; alul új kulcs. Bármely tulajdonság rendezhet, azok is, amelyek nem oszlopok.
  A panel a meglévő `nezet_beallit` műveletet írja (`rendezesBeallit`), így a Táblázat fejléc-kattintásával azonos úton megy.
-->
<script lang="ts">
  import { t } from '../lib/i18n';
  import Ikon from '../lib/ikon/Ikon.svelte';
  import { ArrowDown, ArrowUp, Plus, X } from '../lib/ikon/ikonok';
  import type { BazisModell } from './modell.svelte';
  import { elerhetoNev } from './nevek';
  import {
    rendezesBeallit,
    rendezesek,
    rendezesHozzaad,
    rendezesIranyFordit,
    rendezesMozgat,
    rendezesTorol,
    rendezesTulajdonsag,
    type Rendezes,
  } from './muveletek';
  import type { Elerheto, Valasz } from './tipusok';

  let { modell, v }: { modell: BazisModell; v: Valasz } = $props();

  const nezet = $derived(v.nezet?.index ?? 0);
  const lista = $derived(rendezesek(v));
  /** a választható tulajdonságok: minden elérhető + az oszlopok + a már szereplő (akkor is, ha ismeretlen) */
  const elerheto = $derived.by((): Elerheto[] => {
    const ki = [...(v.fajl?.elerheto ?? [])];
    for (const o of v.oszlopok) if (!ki.some((e) => e.id === o.id)) ki.push({ id: o.id, nev: o.nev, ter: o.ter, tipus: o.tipus });
    for (const r of lista) if (!ki.some((e) => e.id === r.property)) ki.push({ id: r.property, nev: r.property, ter: 'note', tipus: '' });
    return ki;
  });
  const szabad = $derived(elerheto.filter((e) => !lista.some((r) => r.property === e.id)));
  const ir = (uj: Rendezes[]) => void modell.alkalmaz(rendezesBeallit(nezet, uj));
  const nev = (azon: string) => {
    const e = elerheto.find((x) => x.id === azon);
    return e ? elerhetoNev(e) : azon;
  };
</script>

<div class="rendezes">
  {#if lista.length === 0}
    <p class="segito">{t('Nincs rendezés: a fájlnév szerint növekvő a sorrend.')}</p>
  {/if}
  <ol class="sorok" aria-label={t('Rendezési szabályok')}>
    {#each lista as r, i (r.property)}
      <li class="sor">
        <span class="sorszam" aria-hidden="true">{i + 1}</span>
        <select aria-label={t('{n}. rendezési kulcs tulajdonsága', { n: i + 1 })} value={r.property} onchange={(e) => ir(rendezesTulajdonsag(lista, i, e.currentTarget.value))}>
          {#each elerheto as e (e.id)}
            <option value={e.id} disabled={e.id !== r.property && lista.some((x) => x.property === e.id)}>{elerhetoNev(e)}</option>
          {/each}
        </select>
        <button
          type="button"
          class="gomb irany"
          aria-label={t('{n}. kulcs iránya: {irany}', { n: i + 1, irany: r.direction === 'ASC' ? t('növekvő') : t('csökkenő') })}
          onclick={() => ir(rendezesIranyFordit(lista, i))}
        >
          <Ikon ikon={r.direction === 'ASC' ? ArrowUp : ArrowDown} meret={14} />
          <span>{r.direction === 'ASC' ? t('növekvő') : t('csökkenő')}</span>
        </button>
        <button type="button" class="gomb" aria-label={t('{n}. kulcs feljebb', { n: i + 1 })} disabled={i === 0} onclick={() => ir(rendezesMozgat(lista, i, -1))}>
          <Ikon ikon={ArrowUp} meret={14} />
        </button>
        <button type="button" class="gomb" aria-label={t('{n}. kulcs lejjebb', { n: i + 1 })} disabled={i === lista.length - 1} onclick={() => ir(rendezesMozgat(lista, i, 1))}>
          <Ikon ikon={ArrowDown} meret={14} />
        </button>
        <button type="button" class="gomb" aria-label={t('{nev} rendezés törlése', { nev: nev(r.property) })} onclick={() => ir(rendezesTorol(lista, i))}>
          <Ikon ikon={X} meret={14} />
        </button>
      </li>
    {/each}
  </ol>
  {#if szabad.length}
    <label class="uj">
      <Ikon ikon={Plus} meret={14} />
      <select aria-label={t('Rendezési kulcs hozzáadása')} value="" onchange={(e) => {
        const azon = e.currentTarget.value;
        e.currentTarget.value = '';
        if (azon) ir(rendezesHozzaad(lista, azon));
      }}>
        <option value="">{t('Rendezés hozzáadása…')}</option>
        {#each szabad as e (e.id)}<option value={e.id}>{elerhetoNev(e)}</option>{/each}
      </select>
    </label>
  {/if}
  {#if modell.irasHiba}<p class="hiba" role="alert">{modell.irasHiba}</p>{/if}
</div>

<style>
  .rendezes {
    display: flex;
    flex-direction: column;
    gap: var(--t-2);
  }

  .sorok {
    display: flex;
    flex-direction: column;
    gap: var(--t-1);
    margin: 0;
    padding: 0;
    list-style: none;
  }

  .sor {
    display: flex;
    align-items: center;
    gap: var(--t-1);
  }

  .sorszam {
    flex: none;
    width: var(--t-4);
    color: var(--szoveg-halvany);
    font-variant-numeric: tabular-nums;
    text-align: center;
  }

  select {
    box-sizing: border-box;
    flex: 1;
    min-width: 0;
    height: 26px;
    padding: 0 var(--t-1);
    border: 1px solid var(--keret-mezo);
    border-radius: var(--kerekites-kicsi);
    background: var(--hatter);
    color: var(--szoveg);
    font: inherit;
  }

  .gomb {
    flex: none;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    gap: var(--t-1);
    height: var(--magassag-suru);
    min-width: var(--magassag-suru);
    padding: 0 var(--t-1);
    border: 0;
    border-radius: var(--kerekites-kicsi);
    background: transparent;
    color: var(--szoveg-masodlagos);
    font: inherit;
    cursor: pointer;
  }

  .gomb:hover:not(:disabled) {
    background: var(--hatter-hover);
    color: var(--szoveg);
  }

  .gomb:disabled {
    opacity: var(--tiltott-atlatszosag);
    cursor: default;
  }

  .gomb:focus-visible,
  select:focus-visible {
    outline: var(--fokusz-vastag) solid var(--fokusz-gyuru);
    outline-offset: var(--fokusz-tav);
  }

  .uj {
    display: flex;
    align-items: center;
    gap: var(--t-1);
    color: var(--szoveg-halvany);
  }

  .segito {
    margin: 0;
    color: var(--szoveg-halvany);
    font-size: var(--betu-kicsi);
  }

  .hiba {
    margin: 0;
    color: var(--hiba);
    font-size: var(--betu-kicsi);
  }
</style>
