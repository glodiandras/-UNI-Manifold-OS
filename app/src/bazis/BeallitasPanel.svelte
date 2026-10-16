<!--
  A nézet beállításai (C12b): név, típus, csoportosítás (Kanbanban ez az oszlopok forrása), sorok száma, és típusonként:
  táblázat sormagassága; kártya borítóképe, mérete, illesztése, képaránya. A mezők a nézet nyers YAML-kulcsait írják
  (az ismeretlen kulcsok érintetlenek maradnak); minden változás azonnal a fájlba megy.
-->
<script lang="ts">
  import { t, tk } from '../lib/i18n';
  import type { BazisModell } from './modell.svelte';
  import { csoport, csoportBeallit, egeszBevitel, nezetKulcs, type Irany } from './muveletek';
  import type { Elerheto, NezetTipus, Valasz } from './tipusok';

  let { modell, v }: { modell: BazisModell; v: Valasz } = $props();

  const nezet = $derived(v.nezet?.index ?? 0);
  const beall = $derived(v.nezet?.beallitas ?? {});
  const tipus = $derived<NezetTipus>(v.nezet?.tipus ?? 'table');
  const cs = $derived(csoport(v));

  const elerheto = $derived.by((): Elerheto[] => {
    const ki = [...(v.fajl?.elerheto ?? [])];
    for (const o of v.oszlopok) if (!ki.some((e) => e.id === o.id)) ki.push({ id: o.id, nev: o.nev, ter: o.ter, tipus: o.tipus });
    return ki;
  });
  const kepIdk = $derived.by(() => {
    const k = typeof beall.image === 'string' ? beall.image : '';
    return k && !elerheto.some((e) => e.id === k) ? [{ id: k, nev: k, ter: 'note', tipus: '' } as Elerheto, ...elerheto] : elerheto;
  });
  const csoportIdk = $derived.by(() =>
    cs && !elerheto.some((e) => e.id === cs.property)
      ? [{ id: cs.property, nev: cs.property, ter: 'note', tipus: '' } as Elerheto, ...elerheto]
      : elerheto,
  );

  const TIPUSOK: Array<{ id: NezetTipus; felirat: string }> = [
    { id: 'table', felirat: tk('Táblázat') },
    { id: 'cards', felirat: tk('Kártyák') },
    { id: 'kanban', felirat: tk('Kanban') },
  ];
  const SORMAGASSAG = [
    { id: 'short', felirat: tk('Alacsony') },
    { id: 'medium', felirat: tk('Közepes') },
    { id: 'tall', felirat: tk('Magas') },
    { id: 'extra tall', felirat: tk('Extra magas') },
  ];

  const ir = (kulcs: string, ertek: unknown) => void modell.alkalmaz(nezetKulcs(nezet, kulcs, ertek));
  let hibasBevitel = $state<string | null>(null);

  function egesz(kulcs: string, szoveg: string, felirat: string) {
    const n = egeszBevitel(szoveg);
    if (n === undefined) {
      hibasBevitel = t('{felirat}: pozitív egész szám kell.', { felirat: t(felirat) });
      return;
    }
    hibasBevitel = null;
    ir(kulcs, n);
  }

  function szam(kulcs: string, szoveg: string, felirat: string) {
    const s = szoveg.trim().replace(',', '.');
    if (s === '') {
      hibasBevitel = null;
      return ir(kulcs, null);
    }
    const n = Number(s);
    if (!Number.isFinite(n) || n <= 0) {
      hibasBevitel = t('{felirat}: pozitív szám kell.', { felirat: t(felirat) });
      return;
    }
    hibasBevitel = null;
    ir(kulcs, n);
  }

  let nev = $state('');
  $effect(() => {
    nev = v.nezet?.nev ?? '';
  });
  function nevMent() {
    const n = nev.trim();
    if (n && n !== v.nezet?.nev) ir('name', n);
    else nev = v.nezet?.nev ?? '';
  }
</script>

<div class="beallitas">
  <label class="sor">
    <span>{t('Név')}</span>
    <input
      type="text"
      bind:value={nev}
      onblur={nevMent}
      onkeydown={(e) => e.key === 'Enter' && (e.currentTarget as HTMLInputElement).blur()}
    />
  </label>
  <div class="sor">
    <span id="nezet-tipus">{t('Típus')}</span>
    <div class="szegmens" role="group" aria-labelledby="nezet-tipus">
      {#each TIPUSOK as ti (ti.id)}
        <button type="button" aria-pressed={tipus === ti.id} onclick={() => tipus !== ti.id && ir('type', ti.id)}>{t(ti.felirat)}</button>
      {/each}
    </div>
  </div>
  <div class="sor">
    <span id="csoport-cim">{tipus === 'kanban' ? t('Oszlopok (csoportosítás)') : t('Csoportosítás')}</span>
    <div class="ketto">
      <select
        aria-labelledby="csoport-cim"
        value={cs?.property ?? ''}
        onchange={(e) => void modell.alkalmaz(csoportBeallit(nezet, e.currentTarget.value || null, cs?.direction ?? 'ASC'))}
      >
        <option value="">{t('(nincs)')}</option>
        {#each csoportIdk as e (e.id)}<option value={e.id}>{e.nev}</option>{/each}
      </select>
      {#if cs}
        <select
          aria-label={t('Csoportok sorrendje')}
          value={cs.direction}
          onchange={(e) => void modell.alkalmaz(csoportBeallit(nezet, cs.property, e.currentTarget.value as Irany))}
        >
          <option value="ASC">{t('növekvő')}</option>
          <option value="DESC">{t('csökkenő')}</option>
        </select>
      {/if}
    </div>
  </div>
  <label class="sor">
    <span>{t('Sorok száma legfeljebb')}</span>
    <input
      type="text"
      inputmode="numeric"
      placeholder={t('korlát nélkül')}
      value={typeof beall.limit === 'number' ? String(beall.limit) : ''}
      onchange={(e) => egesz('limit', e.currentTarget.value, tk('Sorok száma'))}
    />
  </label>
  {#if tipus === 'table'}
    <label class="sor">
      <span>{t('Sormagasság')}</span>
      <select value={String(beall.rowHeight ?? 'short')} onchange={(e) => ir('rowHeight', e.currentTarget.value === 'short' ? null : e.currentTarget.value)}>
        {#each SORMAGASSAG as s (s.id)}<option value={s.id}>{t(s.felirat)}</option>{/each}
      </select>
    </label>
  {:else if tipus === 'cards'}
    <label class="sor">
      <span>{t('Borítókép')}</span>
      <select value={typeof beall.image === 'string' ? beall.image : ''} onchange={(e) => ir('image', e.currentTarget.value || null)}>
        <option value="">{t('(nincs)')}</option>
        {#each kepIdk as e (e.id)}<option value={e.id}>{e.nev}</option>{/each}
      </select>
    </label>
    <label class="sor">
      <span>{t('Kártya szélessége (px)')}</span>
      <input
        type="text"
        inputmode="numeric"
        placeholder={t('alap')}
        value={typeof beall.cardSize === 'number' ? String(beall.cardSize) : ''}
        onchange={(e) => egesz('cardSize', e.currentTarget.value, tk('Kártya szélessége'))}
      />
    </label>
    <label class="sor">
      <span>{t('Kép illesztése')}</span>
      <select value={String(beall.imageFit ?? 'cover')} onchange={(e) => ir('imageFit', e.currentTarget.value === 'cover' ? null : e.currentTarget.value)}>
        <option value="cover">{t('kitölti')}</option>
        <option value="contain">{t('belefér')}</option>
      </select>
    </label>
    <label class="sor">
      <span>{t('Képarány (szél. / mag.)')}</span>
      <input
        type="text"
        inputmode="decimal"
        placeholder={t('alap')}
        value={typeof beall.imageAspectRatio === 'number' ? String(beall.imageAspectRatio) : ''}
        onchange={(e) => szam('imageAspectRatio', e.currentTarget.value, tk('Képarány'))}
      />
    </label>
  {/if}
  {#if hibasBevitel}<p class="hiba" role="alert">{hibasBevitel}</p>{/if}
  {#if modell.irasHiba}<p class="hiba" role="alert">{modell.irasHiba}</p>{/if}
</div>

<style>
  .beallitas {
    display: flex;
    flex-direction: column;
    gap: var(--t-2);
  }

  .sor {
    display: grid;
    grid-template-columns: 1fr 1.2fr;
    align-items: center;
    gap: var(--t-2);
    color: var(--szoveg-masodlagos);
  }

  input,
  select {
    box-sizing: border-box;
    min-width: 0;
    height: 26px;
    padding: 0 var(--t-1);
    border: 1px solid var(--keret-mezo);
    border-radius: var(--kerekites-kicsi);
    background: var(--hatter);
    color: var(--szoveg);
    font: inherit;
  }

  .ketto {
    display: flex;
    gap: var(--t-1);
  }

  .ketto select {
    flex: 1;
  }

  .szegmens {
    display: flex;
    border: 1px solid var(--keret-mezo);
    border-radius: var(--kerekites-kicsi);
    overflow: hidden;
  }

  .szegmens button {
    flex: 1;
    height: var(--magassag-suru);
    padding: 0 var(--t-1);
    border: 0;
    background: transparent;
    color: var(--szoveg-masodlagos);
    font: inherit;
    cursor: pointer;
  }

  /* a szegmens-kapcsoló kiválasztott eleme a gráfé és a többi kapcsolóé (kijelölt háttér; az akcent ritka) */
  .szegmens button[aria-pressed='true'] {
    background: var(--hatter-kijelolt);
    color: var(--szoveg);
  }

  .hiba {
    margin: 0;
    color: var(--hiba);
    font-size: var(--betu-kicsi);
  }
</style>
