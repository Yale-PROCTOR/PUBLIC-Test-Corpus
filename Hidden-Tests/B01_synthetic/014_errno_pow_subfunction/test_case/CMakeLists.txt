# © 2026 Massachusetts Institute of Technology
# MIT License

cmake_minimum_required(VERSION 3.10)
project(errno-pow)
add_executable(driver
    src/main.c)
target_link_libraries(driver m)
