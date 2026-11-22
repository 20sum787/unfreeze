#include <cassert>
#include <iostream>
#include "CueOutputs.h"
#include "MovementStream.h"

int main() {
  Wire1.device[Config::Movement] = true;
  Wire1.device[Config::Vibro] = true;
  Wire1.device[Config::Buzzer] = true;
  CueOutputs out;
  out.refresh();
  assert(out.hasVibro && out.hasBuzzer);
  events.clear();
  fakeMs = 0xffffff00;
  assert(out.startVibro(40,90)==1);
  assert(!out.startVibro(40,90));
  assert(out.startBuzzer(1000,90)==1);
  assert(events.size()==2);
  for(int n=1; n<=3; n++){fakeMs+=667; out.tick(fakeMs);}
  assert(events.size()==8);
  fakeMs+=181+35; out.tick(fakeMs);
  assert(!out.vibroActive() && !out.buzzerActive());
  assert(!out.startVibro(39,90) && !out.startBuzzer(3001,90));
  events.clear();
  assert(out.startVibro(40,90) && out.startBuzzer(1000,90));
  assert(out.stop(1) && !out.vibroActive() && out.buzzerActive());
  fakeMs+=667*2+40; out.tick(fakeMs);
  assert(events.size()==3); // two onset commands + one explicit haptic stop; late beats skipped
  assert(out.stop(3));
  assert(out.benchPulse(2));
  assert(!out.benchPulse(1));
  assert(events.back()==Event('b',fakeMs,1000,440));
  fakeMs+=1000; out.tick(fakeMs);
  assert(!out.buzzerActive() && out.benchPulse(1));
  assert(events.back()==Event('v',fakeMs,1000,40));
  assert(out.stop(3));
  // Exercise the deadline across millis() rollover, including a clipped final beat.
  fakeMs = 0xffffff00;
  const uint32_t start = fakeMs;
  events.clear();
  assert(out.freezePulses(45, 100) == 5000);
  assert(out.freezeAlarm() == 5000);
  assert(events.back() == Event('b', start, 5000, 2400));
  for (int elapsed = 1; elapsed <= 5000; ++elapsed) {
    ++fakeMs;
    out.tick(fakeMs);
    assert(out.vibroActive() == (elapsed < 5000));
    assert(out.buzzerActive() == (elapsed < 5000));
  }
  assert(events.size() == 10);
  for (int beat = 0; beat < 9; ++beat) {
    assert(events[beat ? beat + 1 : 0] == Event('v', start + beat * 600, 180, 45));
  }
  assert(out.freezePulses(45, 145) == 5000);
  fakeMs += 4968; out.tick(fakeMs);
  assert(events.back() == Event('v', fakeMs, 32, 45));
  assert(out.freezeAlarm() == 5000 && out.stop(3));
  assert(!out.vibroActive() && !out.buzzerActive());
  Wire1.device[Config::Buzzer]=false;
  out.refresh();
  assert(!out.hasBuzzer && !out.startBuzzer(1000,90));
  MovementStream stream(Config::Movement);
  stream.refresh(); assert(stream.online);
  for (uint32_t i=0; i<40; i++){
    ++fakeMs;
    stream.readSlot(UINT32_MAX-41+i,i==0?5:0);
  }
  assert(stream.samples==40 && stream.missed==5);
  uint32_t latestSeq = 0;
  float latestAccel[3]{};
  assert(stream.latest(latestSeq, latestAccel) && latestSeq == UINT32_MAX-2);
  assert(latestAccel[0] == -4 && latestAccel[1] == 1);
  String rows=stream.drain();
  assert(rows.find(std::to_string(UINT32_MAX-41+8)) != String::npos);
  assert(rows.find("\"dropped\":8")!=String::npos);
  assert(rows.size()<220);
  assert(rows.find("-40000e-4,10000e-4,1300e-4,-199990e-2")!=String::npos);
  for (int pair = 1; pair < Config::FifoRows/2; ++pair) stream.drain();
  assert(stream.latest(latestSeq, latestAccel) && latestSeq == UINT32_MAX-2);
  assert(stream.drain().find("\"rows\":[]")!=String::npos);
  stream.clear();
  assert(!stream.latest(latestSeq, latestAccel));
  assert(stream.drain().find("\"rows\":[]")!=String::npos);
  std::cout<<"PASS pulse counts, rollover, late-beat skip, isolated cancel, disconnected hardware, ring overflow, bounded response; sample response "<<rows.size()<<" bytes\n";
}
