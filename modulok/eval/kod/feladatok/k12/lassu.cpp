#include <bits/stdc++.h>
using namespace std;

int main() {
    string s;
    cin >> s;
    char legjobb = 'a';
    int legtobb = -1;
    for (char c = 'a'; c <= 'z'; c++) {
        int db = 0;
        for (char x : s)
            if (x == c) db++;
        if (db > legtobb) {
            legtobb = db;
            legjobb = c;
        }
    }
    cout << legjobb << " " << legtobb << "\n";
    return 0;
}
