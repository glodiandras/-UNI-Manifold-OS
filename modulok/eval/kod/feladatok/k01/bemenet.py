def general(rng, meret):
    if meret == "nagy":
        n = 200000
        a = [rng.randint(-10**9, 10**9) for _ in range(n)]
    else:
        n = rng.randint(1, 8)
        a = [rng.randint(-3, 3) for _ in range(n)]
    return f"{n}\n{' '.join(map(str, a))}\n"


def ervenyes(s):
    try:
        t = s.split()
        n = int(t[0])
        a = [int(x) for x in t[1:]]
        return 1 <= n <= 200000 and len(a) == n and all(-10**9 <= x <= 10**9 for x in a)
    except (ValueError, IndexError):
        return False
