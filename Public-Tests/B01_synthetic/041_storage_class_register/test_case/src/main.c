// © 2026 Massachusetts Institute of Technology
// MIT License

#include <stdio.h>

void driver(int x) {
    register int y = 2*x;
    y += 300;
    printf("%d\n", y);
}

int main() {
    int x = 0;
    scanf("%d", &x);
    driver(x);
    return 0;
}