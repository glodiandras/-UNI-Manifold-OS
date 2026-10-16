<script lang="ts">
  import Oldalsav from '../src/hej/Oldalsav.svelte';
  import KeresoAblak from '../src/atfedes/KeresoAblak.svelte';
  import { kornyezet } from '../src/lib/kornyezet';
  const { felulet } = kornyezet();
</script>
<Oldalsav />
{#if felulet.atfedes === 'kereso'}<KeresoAblak />{/if}
