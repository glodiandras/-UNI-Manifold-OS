# Családfa mélysége

Egy családfa n személyét 1-től n-ig számozzuk. Mindenkinél ismerjük a szülőjét; pontosan egy személynek (az ősnek) nincs
szülője a fában. Az ős mélysége 0, mindenki más mélysége eggyel nagyobb a szülőjénél. Mekkora a legnagyobb mélység?

## Bemenet

Az első sorban n (1 ≤ n ≤ 100 000). A második sorban n egész szám: p_1 … p_n, ahol p_i az i-edik személy szülője, illetve 0,
ha i az ős. A szülő-kapcsolatok fát alkotnak (nincs kör).

## Kimenet

Egyetlen szám: a legnagyobb mélység.

## Tesztek

```teszt Példa
--- bemenet
5
0 1 1 2 4
--- kimenet
3
```

```teszt Egyetlen személy
--- bemenet
1
0
--- kimenet
0
```

```teszt Az ős nem az első
--- bemenet
4
2 0 2 3
--- kimenet
2
```
