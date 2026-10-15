def general(rng, meret):
    if meret == "nagy":
        n = 200000
        k = n // 2
        a = [rng.randint(-10**9, 10**9) for _ in range(n)]
    else:
        n = rng.randint(1, 8)
        k = rng.randint(1, n)
        a = [rng.randint(-6, 6) for _ in range(n)]
    return f"{n} {k}\n{' '.join(map(str, a))}\n"


def ervenyes(s):
    try:
        t = [int(x) for x in s.split()]
        n, k = t[0], t[1]
        a = t[2:]
        return 1 <= k <= n <= 200000 and len(a) == n and all(-10**9 <= x <= 10**9 for x in a)
    except (ValueError, IndexError):
        return False
