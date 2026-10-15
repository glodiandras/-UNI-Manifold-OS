SZELSO = [-10**9, -1, 0, 1, 10**9]


def general(rng, meret):
    if meret == "nagy":
        n, q = 200000, 50000
        a = [rng.randint(-10**9, 10**9) for _ in range(n)]
    else:
        n, q = rng.randint(1, 8), rng.randint(1, 5)
        a = [rng.choice(SZELSO) if rng.random() < 0.5 else rng.randint(-5, 5) for _ in range(n)]
    sorok = [f"{n} {q}", " ".join(map(str, a))]
    for _ in range(q):
        l = rng.randint(1, n)
        sorok.append(f"{l} {rng.randint(l, n)}")
    return "\n".join(sorok) + "\n"


def ervenyes(s):
    try:
        t = [int(x) for x in s.split()]
        n, q = t[0], t[1]
        if not (1 <= n <= 200000 and 1 <= q <= 200000 and len(t) == 2 + n + 2 * q):
            return False
        if not all(-10**9 <= x <= 10**9 for x in t[2:2 + n]):
            return False
        k = t[2 + n:]
        return all(1 <= k[2 * i] <= k[2 * i + 1] <= n for i in range(q))
    except (ValueError, IndexError):
        return False
