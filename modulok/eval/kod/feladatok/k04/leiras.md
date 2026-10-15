# Párok adott összeggel

Adott n egész szám és egy s célérték. Hány olyan (i, j) indexpár van, amelyre i < j és a_i + a_j = s? Az azonos értékű,
de különböző helyen álló elemek különböző elemnek számítanak.

## Bemenet

Az első sorban n és s (1 ≤ n ≤ 200 000, −2·10^9 ≤ s ≤ 2·10^9), a második sorban n egész szám (−10^9 ≤ a_i ≤ 10^9).

## Kimenet

Egyetlen szám: a megfelelő párok száma.

## Tesztek

```teszt Példa
--- bemenet
5 6
1 5 3 3 2
--- kimenet
2
```

```teszt Csupa nulla
--- bemenet
4 0
0 0 0 0
--- kimenet
6
```

```teszt Nincs pár
--- bemenet
3 10
1 2 3
--- kimenet
0
```
