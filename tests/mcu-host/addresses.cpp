#include <cassert>
#include <iostream>
#include "sketch.ino"
int main(int argc, char *argv[]) {
  assert(argc==2);
  int address=std::atoi(argv[1]);
  if (address) Wire1.device[address]=true;
  setup();
  assert(sampleHz==64 && primaryAddress==address);
  assert(statusJson().size()<220);
  if (!address) {
    assert(readPrimary()=="{\"rows\":[],\"dropped\":0}");
    Wire1.device[0x6a]=true; Wire1.device[0x6b]=true;
    refreshModules();
    assert(primaryAddress==0x6b);
  }
  uint8_t other=primaryAddress==0x6a ? 0x6b : 0x6a;
  Wire1.device[other]=true;
  refreshModules();
  assert(secondary && secondary->online);
  const int original=primaryAddress;
  Wire1.device[original]=false;
  refreshModules();
  assert(primaryAddress==original && !primary->online && secondary->online);
  assert(setRate(100) && sampleHz==100);
  assert(setRate(64) && sampleHz==64);
  assert(!setRate(1000));
  std::cout<<"PASS starting address "<<address<<" and stable body-site assignment after removal\n";
}
