#pragma once
#include <array>
#include <cmath>
#include <cstdint>
#include <cstdio>
#include <string>
#include <tuple>
#include <vector>
using std::uint8_t;
using std::uint32_t;
struct String : std::string {
  using std::string::string;
  using std::string::operator+=;
  explicit String(uint32_t n) : std::string(std::to_string(n)) {}
  String(float v, int decimals) {
    char tmp[32];
    std::snprintf(tmp, sizeof tmp, "%.*f", decimals, (double)v);
    assign(tmp);
  }
};
inline uint32_t fakeMs;
inline uint32_t millis() { return fakeMs; }
inline uint32_t micros() { return fakeMs * 1000; }
struct { template<typename T> void begin(T &) {} } inline Modulino;
struct { uint8_t addr = 0; std::array<bool,128> device{};
  void beginTransmission(uint8_t a) {addr = a;}
  int endTransmission() {return device[addr] ? 0 : 1;}
} inline Wire1;
struct ModulinoMovement {
  explicit ModulinoMovement(uint8_t) {}
  bool begin() {return true;}
  bool available() {return true;}
  int update() {return 1;}
  float getX() {return -4;} float getY() {return 1;} float getZ() {return .13f;}
  float getRoll() {return -1999.9f;} float getPitch() {return -1999.9f;} float getYaw() {return -1999.9f;}
};
using Event=std::tuple<char,uint32_t,int,int>;
inline std::vector<Event> events;
struct ModulinoVibro {
  explicit ModulinoVibro(uint8_t) {}
  void begin(){}
  void off(){events.emplace_back('v',millis(),0,0);}
  void on(int ms,bool block,int level){if(block) std::abort(); events.emplace_back('v',millis(),ms,level);}
};
struct ModulinoBuzzer {
  explicit ModulinoBuzzer(uint8_t){}
  void begin(){}
  void noTone(){events.emplace_back('b',millis(),0,0);}
  void tone(int hz,int ms){events.emplace_back('b',millis(),ms,hz);}
};
