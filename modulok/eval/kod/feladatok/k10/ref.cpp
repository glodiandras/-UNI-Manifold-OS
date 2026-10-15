#include <bits/stdc++.h>
using namespace std;

int n;
vector<int> szulo, melyseg;

int mely(int v) {
    if (szulo[v] == 0) return 0;
    if (melyseg[v] != -1) return melyseg[v];
    melyseg[v] = mely(szulo[v]) + 1;
    return melyseg[v];
}

int main() {
    cin >> n;
    szulo.assign(n + 1, 0);
    melyseg.assign(n + 1, -1);
    for (int i = 1; i <= n; i++) cin >> szulo[i];
    int legmelyebb = 0;
    for (int v = 1; v <= n; v++) legmelyebb = max(legmelyebb, mely(v));
    cout << legmelyebb << "\n";
    return 0;
}
