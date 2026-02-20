// © 2026 Massachusetts Institute of Technology
// MIT License

#include <stdio.h>

/* interactive echo; ignores arguments, copies stdin to stdout */
int main() {
    char text[128];

    while (fgets(text, 128, stdin)) {
        fputs(text, stdout);
    }
    return 0;
}

