#include <bits/stdc++.h>
using namespace std;

int main() {
    int n, q;
    cin >> n >> q;
    vector<long long> a(n);
    for (auto &x : a) cin >> x;
    for (int k = 0; k < q; k++) {
        long long l, r;
        cin >> l >> r;
        int db = 0;
        for (long long x : a)
            if (l <= x && x <= r) db++;
        cout << db << "\n";
    }
    return 0;
}
