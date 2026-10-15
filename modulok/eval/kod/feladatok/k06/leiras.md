# Legjobb k napos időszak

Egy bolt n napon át feljegyezte a napi eredményét (ez lehet negatív is). Melyik k egymást követő nap együttes eredménye a
legnagyobb? Csak ezt az összeget kell kiírni.

## Bemenet

Az első sorban n és k (1 ≤ k ≤ n ≤ 200 000), a második sorban n egész szám (−10^9 ≤ a_i ≤ 10^9).

## Kimenet

Egyetlen szám: a legnagyobb összeg, amelyet k szomszédos elem ad.

## Tesztek

```teszt Példa
--- bemenet
5 2
1 3 -2 5 4
--- kimenet
9
```

```teszt Csupa negatív
--- bemenet
3 3
-1 -2 -3
--- kimenet
-6
```

```teszt Egyes ablak
--- bemenet
4 1
-5 -1 -7 -2
--- kimenet
-1
```
