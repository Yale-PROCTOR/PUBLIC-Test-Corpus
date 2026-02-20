// © 2026 Massachusetts Institute of Technology
// MIT License

#include <stdio.h>
#include <stdlib.h>

/*
    Count up to the passed integer.
*/
int main(int argc, char **argv) {

    if (argc != 2) {
        printf("Error: should only be a single (integer) argument!\n");
        return 1;
    }

    char *end;
    int max_val = strtol(argv[1], &end, 10);
    if (end == argv[1]) {
        // end is set to start of string if nothing parsed
        printf("Error: first argument must be an integer!\n");
        return 1;
    }

    for (int i = 0; i <= max_val; i++) {
        printf("%d\n", i);
    }

    return 0;
}
