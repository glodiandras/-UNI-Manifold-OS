import { describe, expect, it } from 'vitest';
import { belep, legfelso, modalisNyitva } from '../src/lib/fokusz/hatokor';

describe('hatókör-verem', () => {
  it('a kilépés idempotens és csak a saját bejegyzést veszi ki', () => {
    const a = belep('paletta');
    const b = belep('paletta');
    expect(legfelso()).toBe('paletta');
    a();
    a();
    expect(modalisNyitva()).toBe(true);
    b();
    expect(modalisNyitva()).toBe(false);
    expect(legfelso()).toBeNull();
  });
});
