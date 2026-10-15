#include <bits/stdc++.h>
using namespace std;

int main() {
    int n, q;
    cin >> n >> q;
    vector<long long> a(n + 1);
    for (int i = 1; i <= n; i++) cin >> a[i];
    for (int k = 0; k < q; k++) {
        int l, r;
        cin >> l >> r;
        long long s = 0;
        for (int i = l; i <= r; i++) s += a[i];
        cout << s << "\n";
    }
    return 0;
}
