// © 2026 Massachusetts Institute of Technology
// MIT License

#include <stdio.h>
#include <stdlib.h>

/*
Count from a starting point,
stopping when the count ends in 9 (base 10).
*/
int main(int argc, char **argv) {

    if (argc != 2) {
        printf("Error: should only be a single (integer) argument!\n");
        return 1;
    }

    char *end;
    int val = strtol(argv[1], &end, 10);
    if (end == argv[1]) {
        // end is set to start of string if nothing parsed
        printf("Error: first argument must be an integer!\n");
        return 1;
    }

    while (1) {
        printf("%d\n", val);
        if (val % 10 == 9) {
            break;
        }
        val++;
    }

    return 0;
}
