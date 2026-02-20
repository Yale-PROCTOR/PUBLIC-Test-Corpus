// © 2026 Massachusetts Institute of Technology
// MIT License

#include <stdio.h>
#include <string.h>

void driver(char *in) {
    const char *sep = ":/\n";

    for (char *s = strtok(in, sep); s; s = strtok(NULL, sep)) {
        printf("line %s\n", s);
    }
}

int main() {
    char in[1000] = "";
    fread(in, 1, sizeof(in), stdin);
    driver(in);
    return 0;
}
