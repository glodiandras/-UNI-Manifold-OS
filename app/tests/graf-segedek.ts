// A gráf-fizika tesztek és a perf-készlet közös segédje (T008): determinisztikus, szintetikus gráf.

/** Szintetikus, a vaulthoz hasonló gráf: csomósodó fürtök + néhány összekötő él. Determinisztikus. */
export function szintetikus(n: number, m: number) {
  let mag = 12345;
  const rnd = () => (mag = (Math.imul(mag, 1664525) + 1013904223) >>> 0) / 4294967296;
  const el = new Set<string>();
  const elek: number[] = [];
  while (el.size < m) {
    const a = Math.floor(rnd() * n);
    const b = rnd() < 0.8 ? Math.min(n - 1, a + 1 + Math.floor(rnd() * 12)) : Math.floor(rnd() * n);
    if (a === b || el.has(`${Math.min(a, b)},${Math.max(a, b)}`)) continue;
    el.add(`${Math.min(a, b)},${Math.max(a, b)}`);
    elek.push(a, b);
  }
  const poz = new Float32Array(2 * n);
  for (let i = 0; i < n; i++) {
    poz[2 * i] = (rnd() - 0.5) * 20 * Math.sqrt(n);
    poz[2 * i + 1] = (rnd() - 0.5) * 20 * Math.sqrt(n);
  }
  return { n, elek: Int32Array.from(elek), poz };
}
