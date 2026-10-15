def general(rng, meret):
    if meret == "nagy":
        return "".join(rng.choice("abcdefghijklmnopqrstuvwxyz") for _ in range(200000)) + "\n"
    abc = rng.choice(["ab", "yz", "abz", "xyz", "abcdefghijklmnopqrstuvwxyz"])
    return "".join(rng.choice(abc) for _ in range(rng.randint(1, 8))) + "\n"


def ervenyes(s):
    t = s.split()
    return len(t) == 1 and 1 <= len(t[0]) <= 200000 and all("a" <= c <= "z" for c in t[0])
