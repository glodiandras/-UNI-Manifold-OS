#include <bits/stdc++.h>
using namespace std;

int main() {
    ios::sync_with_stdio(false);
    cin.tie(nullptr);
    int n;
    long long s;
    cin >> n >> s;
    map<long long, long long> db;
    long long parok = 0;
    for (int i = 0; i < n; i++) {
        long long x;
        cin >> x;
        if (db.count(s - x)) parok += db[s - x];
        db[x]++;
    }
    cout << parok << "\n";
    return 0;
}
