#include <bits/stdc++.h>
using namespace std;

int main() {
    ios::sync_with_stdio(false);
    cin.tie(nullptr);
    int n, q;
    cin >> n >> q;
    vector<long long> a(n);
    for (auto &x : a) cin >> x;
    sort(a.begin(), a.end());
    while (q--) {
        long long l, r;
        cin >> l >> r;
        auto bal = lower_bound(a.begin(), a.end(), l);
        auto jobb = upper_bound(a.begin(), a.end(), r);
        cout << (jobb - bal) << "\n";
    }
    return 0;
}
