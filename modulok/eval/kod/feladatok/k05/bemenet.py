def general(rng, meret):
    if meret == "nagy":
        n, q, h = 200000, 100000, 10**9
    else:
        n, q, h = rng.randint(1, 8), rng.randint(1, 5), 6
    a = [rng.randint(-h, h) for _ in range(n)]
    sorok = [f"{n} {q}", " ".join(map(str, a))]
    for _ in range(q):
        if a and rng.random() < 0.5:
            l, r = sorted((rng.choice(a), rng.choice(a)))
        else:
            l, r = sorted((rng.randint(-h, h), rng.randint(-h, h)))
        sorok.append(f"{l} {r}")
    return "\n".join(sorok) + "\n"


def ervenyes(s):
    try:
        t = [int(x) for x in s.split()]
        n, q = t[0], t[1]
        if not (1 <= n <= 200000 and 1 <= q <= 200000 and len(t) == 2 + n + 2 * q):
            return False
        if not all(-10**9 <= x <= 10**9 for x in t[2:]):
            return False
        k = t[2 + n:]
        return all(k[2 * i] <= k[2 * i + 1] for i in range(q))
    except (ValueError, IndexError):
        return False
