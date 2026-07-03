#pragma once

#define HIPFORGE_L4_BLOCK_SIZE 128
#define HIPFORGE_L4_VECTOR_WIDTH 4
#define HIPFORGE_L4_ENABLE_BOUNDS_CHECKS 1

namespace hipforge::level4::config {

constexpr int kBlockSize = HIPFORGE_L4_BLOCK_SIZE;
constexpr int kVectorWidth = HIPFORGE_L4_VECTOR_WIDTH;

}  // namespace hipforge::level4::config

