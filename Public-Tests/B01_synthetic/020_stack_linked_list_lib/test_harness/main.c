// © 2026 Massachusetts Institute of Technology
// MIT License

#include <stdio.h>
#include <stdlib.h>
#include <stdbool.h>
#include "simplestruct.h"


int main(int argc, char **argv) {
    if (argc != 4) {
        printf("Harness takes exactly three (integer) arguments!\n");
        return 1;
    }

    char *end;
    int param1 = strtol(argv[1], &end, 10);
    if (end == argv[1]) {
        // end is set to start of string if nothing parsed
        printf("First argument must be an integer!\n");
        return 1;
    }

    int param2 = strtol(argv[2], &end, 10);
    if (end == argv[2]) {
        printf("Second argument must be an integer!\n");
        return 1;
    }

    int param3 = strtol(argv[3], &end, 10);
    if (end == argv[3]) {
        printf("Third argument must be an integer!\n");
        return 1;
    }
    struct ListNode list3 = {param3, NULL};
    struct ListNode list2 = {param2, &list3};
    struct ListNode list1 = {param1, &list2};

    int smallest = smallestValue(&list1);

    printf("Smallest Value: %d\n", smallest);
    return 0;
}
