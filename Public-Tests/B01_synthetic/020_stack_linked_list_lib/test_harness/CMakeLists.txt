# © 2026 Massachusetts Institute of Technology
# MIT License

cmake_minimum_required(VERSION 3.10)
project(test_harness)
add_executable(test_harness main.c)

SET(LIBRARY_LOCATION "../project/build" CACHE STRING "Location of the library to link against")

find_library(PROJECT_LIB SimpleList HINTS "${LIBRARY_LOCATION}/lib")
target_link_libraries(test_harness PRIVATE "${PROJECT_LIB}")

target_include_directories(test_harness
    PRIVATE "${LIBRARY_LOCATION}/include")
