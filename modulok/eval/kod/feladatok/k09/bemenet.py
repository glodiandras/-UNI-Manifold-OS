def general(rng, meret):
    if meret == "nagy":
        n = 100000
        sor = list(range(2, n))
        rng.shuffle(sor)
        lanc = [1] + sor + [n]
        elek = [(lanc[i], lanc[i + 1]) for i in range(n - 1)]
    else:
        n = rng.randint(1, 7)
        elek = []
        if n >= 2:
            for _ in range(rng.randint(0, 9)):
                a, b = rng.sample(range(1, n + 1), 2)
                elek.append((a, b))
    return f"{n} {len(elek)}\n" + "".join(f"{a} {b}\n" for a, b in elek)


def ervenyes(s):
    try:
        t = [int(x) for x in s.split()]
        n, m = t[0], t[1]
        if not (1 <= n <= 100000 and 0 <= m <= 200000 and len(t) == 2 + 2 * m):
            return False
        return all(1 <= t[2 + 2 * i] <= n and 1 <= t[3 + 2 * i] <= n and t[2 + 2 * i] != t[3 + 2 * i] for i in range(m))
    except (ValueError, IndexError):
        return False
