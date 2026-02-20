// © 2026 Massachusetts Institute of Technology
// MIT License

#include <stdio.h>

void printLine (const char * line)
{
    if(line != NULL) 
    {
        printf("%s\n", line);
    }
}

void printIntLine (int intNumber)
{
    printf("%d\n", intNumber);
}

void bad()
{
    int intOne = 1, intTwo = 1, intSum = 0;
    printIntLine(intSum);
    intOne + intTwo;
    printIntLine(intSum);
}

void good()
{
    int intOne = 1, intTwo = 1, intSum = 0;
    printIntLine(intSum);
    intSum = intOne + intTwo;
    printIntLine(intSum);
}

int main(int argc, char *argv[])
{
    printLine("Calling good()...");
    good();
    printLine("Finished good()");
    printLine("Calling bad()...");
    bad();
    printLine("Finished bad()");
    return 0;
}
