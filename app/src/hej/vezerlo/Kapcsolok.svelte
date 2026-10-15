<!-- Az Asszisztens és a Tracker kapcsolója (C17; 10. döntés: alapból mindkettő be). -->
<script lang="ts">
  import { trackerKliens } from '../../lib/tracker/kliens.svelte';
  import { vezerloKapcsolok } from '../../lib/vezerlo/kapcsolok.svelte';

  const KAPCSOLOK = [
    { nev: 'asszisztens', cim: 'Asszisztens', leiras: 'Az asszisztens javaslatai (linkek, szokásminta, hiányzó forrás-horgonyok). A kártyák, összefoglalók, grafikonok csak kifejezett kérésre készülnek.' },
    { nev: 'tracker', cim: 'Tracker', leiras: 'Az app eseményeit számolja (aktív idő, szerkesztett karakter, parancshasználat, késleltetés); a vaulton kívül, helyben él, törölhető. Az appon kívüli tevékenységet nem látja.' },
  ] as const;
</script>

<ul>
  {#each KAPCSOLOK as k (k.nev)}
    <li>
      <label class="kapcsolo">
        <input
          type="checkbox"
          role="switch"
          checked={vezerloKapcsolok.ertek[k.nev]}
          onchange={(e) => void vezerloKapcsolok.allit(k.nev, e.currentTarget.checked)}
        />
        <span class="cim">{k.cim}</span>
      </label>
      <p>{k.leiras}</p>
      {#if k.nev === 'tracker' && trackerKliens.nemFogad}
        <p class="hiba" role="alert">A Tracker nem tud írni: {trackerKliens.nemFogad}. Új adat addig nem gyűlik.</p>
      {/if}
    </li>
  {/each}
</ul>
{#if vezerloKapcsolok.hiba}<p class="hiba" role="alert">{vezerloKapcsolok.hiba}</p>{/if}

<style>
  ul {
    list-style: none;
    margin: 0;
    padding: 0;
    display: flex;
    flex-direction: column;
    gap: var(--t-2);
  }

  .kapcsolo {
    display: flex;
    align-items: center;
    gap: var(--t-2);
    min-height: var(--magassag-sor);
    cursor: pointer;
  }

  .cim {
    color: var(--szoveg);
  }

  p {
    margin: 0 0 0 calc(var(--t-4) + var(--t-2));
    color: var(--szoveg-halvany);
    font-size: var(--betu-kicsi);
    line-height: var(--sor-kicsi);
  }

  li .hiba {
    margin: var(--t-1) 0 0 calc(var(--t-4) + var(--t-2));
  }

  .hiba {
    margin: var(--t-2) 0 0;
    padding: var(--t-2);
    border-radius: var(--kerekites);
    background: var(--hiba-hatter);
    color: var(--hiba);
  }
</style>
