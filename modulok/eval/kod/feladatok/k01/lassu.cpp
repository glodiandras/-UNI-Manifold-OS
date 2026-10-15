#include <bits/stdc++.h>
using namespace std;

int main() {
    int n;
    cin >> n;
    vector<long long> a(n);
    for (auto &x : a) cin >> x;
    int best = 0;
    for (int i = 0; i < n; i++) {
        for (int j = i; j < n; j++) {
            bool novekvo = true;
            for (int k = i + 1; k <= j; k++)
                if (!(a[k - 1] < a[k])) novekvo = false;
            if (novekvo) best = max(best, j - i + 1);
        }
    }
    cout << best << "\n";
    return 0;
}
