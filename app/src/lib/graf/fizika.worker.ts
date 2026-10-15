// A fizika Web Workere (C13): a rajzolás és a bemenet soha nem akad a számolástól. A logika a `FizikaMotor`-ban él.

import { FizikaMotor, type Be } from './fizikaMotor';

const motor = new FizikaMotor((m) => {
  if (m.tipus === 'poz') (self as unknown as Worker).postMessage(m, [m.poz.buffer]);
  else (self as unknown as Worker).postMessage(m);
});

self.onmessage = (ev: MessageEvent<Be>) => motor.kezel(ev.data);
