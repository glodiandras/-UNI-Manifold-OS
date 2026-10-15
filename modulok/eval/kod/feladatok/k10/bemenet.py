def general(rng, meret):
    n = 100000 if meret == "nagy" else rng.randint(1, 8)
    sorrend = list(range(1, n + 1))
    rng.shuffle(sorrend)
    p = [0] * (n + 1)
    for i in range(1, n):
        p[sorrend[i]] = sorrend[i - 1] if meret == "nagy" else sorrend[rng.randint(0, i - 1)]
    return f"{n}\n{' '.join(map(str, p[1:]))}\n"


def ervenyes(s):
    try:
        t = [int(x) for x in s.split()]
        n = t[0]
        p = [0] + t[1:]
        if not (1 <= n <= 100000 and len(p) == n + 1 and all(0 <= x <= n for x in p)):
            return False
        if sum(1 for x in p[1:] if x == 0) != 1:
            return False
        allapot = [0] * (n + 1)
        for v in range(1, n + 1):
            ut = []
            u = v
            while u != 0 and allapot[u] == 0:
                allapot[u] = 1
                ut.append(u)
                u = p[u]
            if u != 0 and allapot[u] == 1:
                return False
            for x in ut:
                allapot[x] = 2
        return True
    except (ValueError, IndexError):
        return False
