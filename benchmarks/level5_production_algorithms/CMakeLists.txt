cmake_minimum_required(VERSION 3.20)

if(NOT DEFINED CMAKE_CUDA_ARCHITECTURES)
  set(CMAKE_CUDA_ARCHITECTURES 70)
endif()

project(hipforge_level5_production_algorithms LANGUAGES CXX CUDA)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CUDA_STANDARD 17)
set(CMAKE_CUDA_STANDARD_REQUIRED ON)

find_package(CUDAToolkit REQUIRED)

add_executable(level5_production_algorithms
  src/algorithms.cu
  src/main.cu
)

target_include_directories(level5_production_algorithms PRIVATE
  ${CMAKE_CURRENT_SOURCE_DIR}/include
)

target_link_libraries(level5_production_algorithms PRIVATE CUDA::cudart)
set_target_properties(level5_production_algorithms PROPERTIES CUDA_SEPARABLE_COMPILATION ON)

