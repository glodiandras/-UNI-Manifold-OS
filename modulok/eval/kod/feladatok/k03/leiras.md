# Szakaszösszegek

Egy n elemű számsorozatra q kérdést kapunk: mennyi az l-edik és az r-edik elem közötti elemek összege (a két végpontot is
beleértve)? Az elemek sorszámozása 1-től indul.

## Bemenet

Az első sorban n és q (1 ≤ n, q ≤ 200 000). A második sorban n egész szám (−10^9 ≤ a_i ≤ 10^9). Utána q sor következik,
mindegyikben két egész: l és r (1 ≤ l ≤ r ≤ n).

## Kimenet

q sor: minden kérdésre az a_l + … + a_r összeg.

## Tesztek

```teszt Példa
--- bemenet
5 3
1 2 3 4 5
1 5
2 4
3 3
--- kimenet
15
9
3
```

```teszt Negatív elemek
--- bemenet
4 2
-1 -2 3 -4
1 2
2 4
--- kimenet
-3
-3
```
