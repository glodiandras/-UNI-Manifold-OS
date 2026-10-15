// Belépési pont: a mentett felület-állapot a mount ELŐTT megjön (≤ 2,5 s), így az első festés végleges;
// utána a héj `kesz` jelet kap, és csak ekkor mutatja az ablakot. Ha a core nem válaszolt, az alapállapot indul
// mentés nélkül, és a mentett állapot a WS `hello`-n pótlódik (`betoltesPotol`, App.svelte).

import { flushSync, mount } from 'svelte';
import App from './App.svelte';
import { hejnek } from './lib/core/hej';
import { titokBetolt } from './lib/core/titok';
import { Felulet, betolt } from './lib/elrendezes/felulet.svelte';
import { alkalmaz } from './lib/elrendezes/tema';
import './styles/tokens.css';
import './styles/alap.css';
import './styles/minta.css';

titokBetolt(); // a héj injektálta API-titok (vagy a #titok= tartalék) — az első API-kérés előtt
const betoltes = await betolt();
const felulet = new Felulet(betoltes.allapot);
felulet.betoltve = betoltes.sikerult;
felulet.munkaterulet.megnyitNezet('manifold'); // CX-007: induló áttekintő, a jegyzetfülek megőrzésével
alkalmaz(felulet.tema);
mount(App, { target: document.getElementById('app')!, props: { felulet } });
flushSync();

// A DOM kész és végleges: a héj most mutatja az ablakot. (Nem rAF: rejtett ablakban az nem fut.)
setTimeout(() => {
  document.documentElement.dataset.kesz = '1';
  hejnek({ tipus: 'kesz' });
}, 0);
