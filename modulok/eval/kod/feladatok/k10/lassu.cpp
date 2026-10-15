#include <bits/stdc++.h>
using namespace std;

int main() {
    int n;
    cin >> n;
    vector<int> p(n + 1);
    for (int i = 1; i <= n; i++) cin >> p[i];
    int best = 0;
    for (int v = 1; v <= n; v++) {
        int lepes = 0;
        for (int u = v; p[u] != 0; u = p[u]) lepes++;
        best = max(best, lepes);
    }
    cout << best << "\n";
    return 0;
}
