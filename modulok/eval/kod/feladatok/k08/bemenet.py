def general(rng, meret):
    if meret == "nagy":
        n, W = 100, 100000
        targyak = [(rng.randint(1, 100000), rng.randint(0, 10**9)) for _ in range(n)]
    else:
        n, W = rng.randint(1, 8), rng.randint(1, 12)
        targyak = [(rng.randint(1, 8), rng.randint(0, 9)) for _ in range(n)]
    return f"{n} {W}\n" + "".join(f"{w} {v}\n" for w, v in targyak)


def ervenyes(s):
    try:
        t = [int(x) for x in s.split()]
        n, W = t[0], t[1]
        if not (1 <= n <= 100 and 1 <= W <= 100000 and len(t) == 2 + 2 * n):
            return False
        return all(1 <= t[2 + 2 * i] <= 100000 and 0 <= t[3 + 2 * i] <= 10**9 for i in range(n))
    except (ValueError, IndexError):
        return False
