def general(rng, meret):
    if meret == "nagy":
        n = 200000
        x = rng.randint(-10**9, 10**9)
        a = [x] * n
        s = 2 * x
    else:
        n = rng.randint(1, 8)
        a = [rng.randint(-3, 3) for _ in range(n)]
        s = rng.randint(-4, 4)
    return f"{n} {s}\n{' '.join(map(str, a))}\n"


def ervenyes(s):
    try:
        t = [int(x) for x in s.split()]
        n, cel = t[0], t[1]
        a = t[2:]
        return (1 <= n <= 200000 and -2 * 10**9 <= cel <= 2 * 10**9 and len(a) == n
                and all(-10**9 <= x <= 10**9 for x in a))
    except (ValueError, IndexError):
        return False
