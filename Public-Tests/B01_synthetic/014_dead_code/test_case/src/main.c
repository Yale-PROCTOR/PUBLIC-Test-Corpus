// © 2026 Massachusetts Institute of Technology
// MIT License

#include <stdio.h>
#include <stdlib.h>

void printLine(const char *line)
{
    if (line != NULL)
    {
        printf("%s\n", line);
    }
}

static void helperBad()
{
    printLine("helperBad()");
}

void bad()
{
    printLine("bad()");
}

static void helperGood()
{
    printLine("helperGood()");
}

void good()
{
    printLine("good()");
    helperGood();
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
