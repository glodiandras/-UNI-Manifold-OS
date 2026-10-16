<!--
  A „Modellek” szakasz (C19): feladatonként a router-tábla (a mért, érvényes sorok a pontszám szerint), a kalibrált jel,
  és hogy a router munka közben (munka-keret) és tartós tétlenségben (távol-keret) melyik modellt választja. Csak olvas:
  egyszer tölt a szakasz megnyitásakor (modellt nem tölt, workert nem indít); a „Frissítés” újrakérdez.
-->
<script lang="ts">
  import { onMount } from 'svelte';
  import { ApiHiba } from '../../lib/core/api';
  import { vezerloApi } from '../../lib/vezerlo/api';
  import type { ModellAttekintes, ModellFeladat, RouterDontes } from '../../lib/vezerlo/tipusok';

  const NEV: Record<string, string> = {
    ocr_kezi: 'Füzet átírása',
    ocr_keplet: 'Képlet felismerése',
    fuzet_fejezet: 'Füzet: fejezet (1. lépés)',
    fuzet_valaszto: 'Füzet: jegyzet (2. lépés)',
    atirat: 'Hangátirat',
    szoveg: 'Szöveg: összefoglaló, kártya',
    kviz: 'Kvíz',
    matek: 'Matek-megoldás',
    matek_cas: 'Megoldás (CAS-ellenőrzött)',
    matek_ellenorzo: 'Levezetés ellenőrzése',
    grafikon: 'Grafikon',
    beagyazas: 'Keresés: beágyazás',
    rerank: 'Keresés: újrarangsorolás',
    osztalyozas: 'Osztályozás',
  };

  let adat = $state.raw<ModellAttekintes | null>(null);
  let hiba = $state<string | null>(null);
  let tolt = $state(false);

  async function frissit() {
    tolt = true;
    try {
      adat = await vezerloApi.modellek();
      hiba = null;
    } catch (e) {
      hiba = e instanceof ApiHiba ? e.message : String(e);
    } finally {
      tolt = false;
    }
  }

  onMount(() => void frissit());

  const dontesSzoveg = (d: RouterDontes): string =>
    d.modell ? d.modell : d.var_tavolra ? 'a távol-keretre vár' : 'nincs kalibrált modell';

  const kalibraltDb = (f: ModellFeladat): number => f.sorok.filter((s) => s.kalibralt && s.aktualis).length;

  /** `szoveg-v2` → `v2` (a feladat neve a fejlécben áll). */
  const rovidVerzio = (feladat: string, v: string): string => (v.startsWith(`${feladat}-`) ? v.slice(feladat.length + 1) : v);
</script>

{#if hiba && !adat}
  <p class="hiba" role="alert">A router-tábla nem érhető el: {hiba}</p>
{:else if !adat}
  <p class="halvany" role="status">Töltődik…</p>
{:else}
  <p class="halvany">
    Munka közben a {adat.keretek.munka} GB-os, tartós tétlenségben a {adat.keretek.tavol} GB-os keretbe férő legjobb
    kalibrált modell fut. ✓ = kalibrált (élesben futhat).
  </p>
  <ul class="feladatok">
    {#each adat.feladatok as f (f.feladat)}
      <li class="feladat">
        <div class="fej">
          <span class="nev">{NEV[f.feladat] ?? f.feladat}</span>
          <span class="dontes" title={`munka: ${f.dontes.munka.indok}\ntávol: ${f.dontes.tavol.indok}`}>
            munka: <b>{dontesSzoveg(f.dontes.munka)}</b> · távol: <b>{dontesSzoveg(f.dontes.tavol)}</b>
          </span>
        </div>
        {#if f.sorok.length}
          <table>
            <tbody>
              {#each f.sorok as s (s.modell)}
                <tr class:regi={!s.aktualis}>
                  <td class="jel" aria-label={s.kalibralt && s.aktualis ? 'kalibrált' : 'mért'}>{s.kalibralt && s.aktualis ? '✓' : ''}</td>
                  <td class="modell">{s.modell}</td>
                  <td class="szam">{s.pontszam.toFixed(3)}</td>
                  <td class="keret">{s.keret === 'tavol' ? 'távol' : s.keret}{s.csucs_gb ? ` · ${s.csucs_gb} GB` : ''}</td>
                  <td class="verzio" title={`${s.aranyhalmaz_verzio} · ${s.megjegyzes}`}>{rovidVerzio(f.feladat, s.aranyhalmaz_verzio)}{s.aktualis ? "" : " (elavult)"}</td>
                </tr>
              {/each}
            </tbody>
          </table>
        {:else}
          <p class="halvany">Nincs mért sor{f.aktualis_verzio ? '' : ' (nincs aranyhalmaza)'}.</p>
        {/if}
        {#if f.sorok.length && !kalibraltDb(f)}
          <p class="halvany">Nincs kalibrált modell: élesben nem fut.</p>
        {/if}
      </li>
    {/each}
  </ul>
  <button type="button" class="gomb" disabled={tolt} onclick={frissit}>Frissítés</button>
{/if}

<style>
  .feladatok {
    list-style: none;
    margin: 0 0 var(--t-3);
    padding: 0;
    display: grid;
    gap: var(--t-3);
  }

  .fej {
    display: flex;
    flex-wrap: wrap;
    align-items: baseline;
    justify-content: space-between;
    gap: var(--t-1) var(--t-3);
    font-size: var(--betu-ui);
    line-height: var(--sor-ui);
  }

  .nev {
    font-weight: var(--suly-felkover);
  }

  .dontes {
    color: var(--szoveg-halvany);
    font-size: var(--betu-kicsi);
  }

  .dontes b {
    color: var(--szoveg);
    font-weight: var(--suly-kozepes);
  }

  table {
    width: 100%;
    margin-top: var(--t-1);
    border-collapse: collapse;
    font-size: var(--betu-kicsi);
    line-height: var(--sor-kicsi);
    font-variant-numeric: tabular-nums;
  }

  td {
    padding: 2px var(--t-2) 2px 0;
    vertical-align: baseline;
    white-space: nowrap;
  }

  td.jel {
    width: 1.2em;
    color: var(--akcent-szoveg);
  }

  td.modell {
    width: 100%;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
    max-width: 0;
  }

  td.szam,
  td.keret,
  td.verzio {
    color: var(--szoveg-halvany);
    text-align: right;
  }

  tr.regi td {
    opacity: var(--atlatszosag-felig);
  }

  .halvany {
    margin: 0 0 var(--t-2);
    color: var(--szoveg-halvany);
    font-size: var(--betu-kicsi);
  }

  .hiba {
    margin: 0;
    padding: var(--t-2);
    border-radius: var(--kerekites);
    background: var(--hiba-hatter);
    color: var(--hiba);
    font-size: var(--betu-kicsi);
  }

  .gomb {
    height: var(--magassag-gomb);
    padding: 0 var(--t-3);
    border-radius: var(--kerekites);
    border: var(--keret-vastag) solid var(--keret-mezo);
    background: transparent;
    color: var(--szoveg);
    font: inherit;
    font-size: var(--betu-ui);
    cursor: pointer;
  }

  .gomb:hover:not(:disabled) {
    background: var(--hatter-hover);
  }

  .gomb:disabled {
    opacity: var(--tiltott-atlatszosag);
    cursor: default;
  }
</style>
