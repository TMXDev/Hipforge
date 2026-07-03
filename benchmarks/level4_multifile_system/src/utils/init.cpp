#include "hipforge_level4/utils/init.h"

namespace hipforge::level4::utils {

std::vector<float> make_signal(int count, float scale) {
  std::vector<float> values(count);
  for (int i = 0; i < count; ++i) {
    values[i] = static_cast<float>((i * 17 + 3) % 101) * scale;
  }
  return values;
}

std::vector<double> make_signal64(int count, double scale) {
  std::vector<double> values(count);
  for (int i = 0; i < count; ++i) {
    values[i] = static_cast<double>((i * 11 + 7) % 97) * scale;
  }
  return values;
}

}  // namespace hipforge::level4::utils

