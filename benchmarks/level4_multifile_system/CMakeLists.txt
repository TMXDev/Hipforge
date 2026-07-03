cmake_minimum_required(VERSION 3.20)

if(NOT DEFINED CMAKE_CUDA_ARCHITECTURES)
  set(CMAKE_CUDA_ARCHITECTURES 70)
endif()

project(hipforge_level4_multifile_system LANGUAGES CXX CUDA)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CUDA_STANDARD 17)
set(CMAKE_CUDA_STANDARD_REQUIRED ON)

find_package(CUDAToolkit REQUIRED)

add_library(level4_core STATIC
  src/core/cross_file_kernels.cu
  src/core/macro_kernels.cu
  src/utils/init.cpp
)

target_include_directories(level4_core PUBLIC
  ${CMAKE_CURRENT_SOURCE_DIR}/include
)

target_link_libraries(level4_core PUBLIC CUDA::cudart)
set_target_properties(level4_core PROPERTIES CUDA_SEPARABLE_COMPILATION ON)

add_executable(level4_multifile_system src/app/main.cu)
target_link_libraries(level4_multifile_system PRIVATE level4_core)

