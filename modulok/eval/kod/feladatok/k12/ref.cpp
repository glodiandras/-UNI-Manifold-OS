#include <bits/stdc++.h>
using namespace std;

int main() {
    string s;
    cin >> s;
    array<int, 26> db{};
    for (char c : s) db[c - 'a']++;
    int legjobb = 0;
    for (int i = 1; i < 26; i++) {
        if (db[i] > db[legjobb]) legjobb = i;
    }
    cout << char('a' + legjobb) << " " << db[legjobb] << "\n";
    return 0;
}
