// © 2026 Massachusetts Institute of Technology
// MIT License

#include <stdio.h>
#include <string.h>

void driver(const char *s1, const char *s2) {
    printf("%zu\n", strcspn(s1, s2));
}

int main() {
    char s1[100] = "", s2[100] = "";
    fgets(s1, sizeof(s1), stdin);
    fgets(s2, sizeof(s1), stdin);

    s1[strlen(s1)-1] = '\0';
    s2[strlen(s2)-1] = '\0';

    driver(s1, s2);
    return 0;
}
