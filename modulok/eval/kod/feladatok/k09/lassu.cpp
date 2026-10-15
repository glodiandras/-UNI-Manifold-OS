#include <bits/stdc++.h>
using namespace std;

int main() {
    int n, m;
    cin >> n >> m;
    const int VEGTELEN = 1000000;
    vector<vector<int>> d(n + 1, vector<int>(n + 1, VEGTELEN));
    for (int i = 1; i <= n; i++) d[i][i] = 0;
    for (int i = 0; i < m; i++) {
        int a, b;
        cin >> a >> b;
        d[a][b] = min(d[a][b], 1);
        d[b][a] = min(d[b][a], 1);
    }
    for (int k = 1; k <= n; k++)
        for (int i = 1; i <= n; i++)
            for (int j = 1; j <= n; j++)
                d[i][j] = min(d[i][j], d[i][k] + d[k][j]);
    cout << (d[1][n] >= VEGTELEN ? -1 : d[1][n]) << "\n";
    return 0;
}
