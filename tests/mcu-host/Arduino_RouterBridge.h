#pragma once
#include "Arduino_Modulino.h"
struct { void begin(unsigned) {} template<class F> bool provide_safe(const char *, F) { return true; } } inline Bridge;
struct { void begin(int) {} template<class T> void println(const T &) {} } inline Monitor;
