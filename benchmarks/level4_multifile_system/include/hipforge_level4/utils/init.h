#pragma once

#include <vector>

namespace hipforge::level4::utils {

std::vector<float> make_signal(int count, float scale);
std::vector<double> make_signal64(int count, double scale);

}  // namespace hipforge::level4::utils

