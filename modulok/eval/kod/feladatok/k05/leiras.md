# Mérések egy tartományban

Egy kísérletben n mérési eredményt rögzítettek. Utána q kérdés érkezik: hány mérés esik az [l, r] zárt intervallumba
(l ≤ érték ≤ r)?

## Bemenet

Az első sorban n és q (1 ≤ n, q ≤ 200 000), a második sorban n egész szám (−10^9 ≤ a_i ≤ 10^9). Utána q sor, mindegyikben
két egész: l és r (−10^9 ≤ l ≤ r ≤ 10^9).

## Kimenet

q sor: minden kérdésre az intervallumba eső mérések száma.

## Tesztek

```teszt Példa
--- bemenet
6 3
5 1 9 3 3 7
3 7
10 20
1 1
--- kimenet
4
0
1
```

```teszt Minden elem bent
--- bemenet
3 1
2 2 2
-5 5
--- kimenet
3
```
