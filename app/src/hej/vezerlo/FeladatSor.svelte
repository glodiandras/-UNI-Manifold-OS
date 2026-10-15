<!-- Egy feladat sora a „Most” szakaszban (C17): cím, állapot, haladássáv; kattintásra a részlet nyílik. -->
<script lang="ts">
  import { allapotCimke, haladasSzoveg, idoRovid, idotartam } from '../../lib/vezerlo/megjelenites';
  import type { Feladat } from '../../lib/vezerlo/tipusok';

  let { feladat, onnyit }: { feladat: Feladat; onnyit: (id: string) => void } = $props();

  const fut = $derived(feladat.allapot === 'fut');
  const kozben = $derived(fut || feladat.allapot === 'sorban');
  const meta = $derived(
    kozben
      ? [haladasSzoveg(feladat), feladat.indult ? `indult ${idoRovid(feladat.indult)}` : ''].filter(Boolean).join(' · ')
      : [idoRovid(feladat.vegzett), idotartam(feladat)].filter(Boolean).join(' · '),
  );
</script>

<button type="button" class="sor" data-allapot={feladat.allapot} onclick={() => onnyit(feladat.id)}>
  <span class="fej">
    <span class="cim">{feladat.cim}</span>
    <span class="allapot">{allapotCimke(feladat.allapot)}</span>
  </span>
  {#if fut}
    <span class="sav" role="progressbar" aria-label="Haladás" aria-valuemin="0" aria-valuemax="100" aria-valuenow={Math.round(feladat.szazalek)}>
      <span class="toltes" style:width="{Math.max(2, feladat.szazalek)}%"></span>
    </span>
  {/if}
  {#if meta}<span class="meta">{meta}</span>{/if}
</button>

<style>
  .sor {
    display: flex;
    flex-direction: column;
    gap: var(--t-1);
    width: 100%;
    padding: var(--t-2);
    border-radius: var(--kerekites);
    text-align: left;
    transition: background-color var(--mozgas-gyors) var(--mozgas-gorbe);
  }

  .sor:hover {
    background: var(--hatter-hover);
  }

  .sor:active {
    background: var(--hatter-aktiv);
  }

  .sor:focus-visible {
    outline-offset: var(--fokusz-tav-befele);
  }

  .fej {
    display: flex;
    align-items: baseline;
    justify-content: space-between;
    gap: var(--t-2);
    min-width: 0;
  }

  .cim {
    min-width: 0;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    color: var(--szoveg);
  }

  .allapot {
    flex: none;
    font-size: var(--betu-kicsi);
    color: var(--szoveg-halvany);
  }

  [data-allapot='kesz'] .allapot {
    color: var(--siker);
  }

  [data-allapot='hiba'] .allapot {
    color: var(--hiba);
  }

  [data-allapot='megszakadt'] .allapot,
  [data-allapot='megallitva'] .allapot {
    color: var(--figyelmeztetes);
  }

  .sav {
    display: block;
    height: 3px;
    border-radius: var(--kerekites-jel);
    background: var(--hatter-aktiv);
    overflow: hidden;
  }

  .toltes {
    display: block;
    height: 100%;
    background: var(--akcent);
    transition: width var(--mozgas-alap) var(--mozgas-gorbe);
  }

  .meta {
    font-size: var(--betu-kicsi);
    line-height: var(--sor-kicsi);
    color: var(--szoveg-halvany);
    font-variant-numeric: tabular-nums;
  }
</style>
