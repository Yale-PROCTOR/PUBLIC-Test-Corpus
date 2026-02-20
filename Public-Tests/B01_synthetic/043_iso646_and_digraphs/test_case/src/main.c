// © 2026 Massachusetts Institute of Technology
// MIT License

%:include <stdio.h>
%:include <iso646.h>

void driver(int x, int y) <%
    int result = x bitor compl y;
    printf("%d", result);
    puts("");
%>

int main() <%
    int x = 0, y = 0;
    scanf("%d", &x);
    scanf("%d", &y);
    driver(x, y);
    return 0;
%>
