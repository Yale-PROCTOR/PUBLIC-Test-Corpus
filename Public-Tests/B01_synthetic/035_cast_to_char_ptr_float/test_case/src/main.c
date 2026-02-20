// © 2026 Massachusetts Institute of Technology
// MIT License

#include <stdio.h>

static void print_hex(unsigned char *p, int len) {
    for (int i = 0; i < len; i++) {
        printf("%02x", p[i]);
    }
    printf("\n");
}

void driver(float x) {
    print_hex((unsigned char *)&x, sizeof(x));
}

int main() {
    float x = 0.f;
    scanf("%f", &x);
    driver(x);
    return 0;
}