import threading, math, time, traceback, os

# Based on timefilter.c from ffmpeg
class DLL(object):
    def __init__(self, period, bandwidth):
        o = 2 * math.pi * bandwidth * period

        self.fb2 = 1 - math.exp(-(2**0.5) * o)
        self.fb3 = (1 - math.exp(-o * o)) / period
        self.period = period
        self.count = 0
        self.lock = threading.Lock()

    def update(self, timestamp, value):
        with self.lock:
            self.count += 1
            if self.count == 1:
                self.cycle_time = timestamp
                self.cycle_value = value
            else:
                delta = value - self.cycle_value
                self.cycle_time += self.period * delta
                self.cycle_value = value

                loop_error = timestamp - self.cycle_time
                self.cycle_time += max(self.fb2, 1.0 / self.count) * loop_error
                self.period += self.fb3 * loop_error
                print("BPM %.4f ERR %.4f D %d" %(60.0 / self.period, loop_error, delta))
                #print("ts %.04f v %.04f period %.04f err %.04f ct %.04f cv %.04f" % (
                #timestamp, value, self.period, loop_error, self.cycle_time, self.cycle_value))
    def evaluate(self, timestamp):  
        with self.lock:
            return self.cycle_value + (timestamp - self.cycle_time) / self.period

    def reverse(self, value):
        with self.lock:
            return (value - self.cycle_value) * self.period + self.cycle_time

    def reset(self, timestamp, value):
        self.cycle_time = timestamp
        self.cycle_value = value

class BPMThread(threading.Thread):
    BW = 0.05
    MUL = 24
    SLACK = 0.1 / MUL
    def __init__(self, parent):
        threading.Thread.__init__(self)
        self.parent = parent
        self.dll = DLL(0.5, self.BW)
        self.dll.update(time.time(), 0)
        self.needs_reset = False
        self.period = None
        self.last_kick = None
        self.last_kick_step = None
        self.lk_count = 0
        self.active = True
        self.tick = None
        self.lock = threading.Lock()

    def reset(self, t=None):
        with self.lock:
            if t is None:
                t = time.time()
            self.dll.reset(t, 0)
            self.tick = None
            self.needs_reset = True
            self.last_kick = t

    def kick(self, t=None):
        if self.last_kick and (time.time() - self.last_kick) < 0.1:
            return
        with self.lock:
            if t is None:
                t = time.time()
            if self.needs_reset and (t - self.last_kick) < 1:
                self.period = t - self.last_kick
                self.dll = DLL(self.period, self.BW)
                self.dll.update(t, 1)
                self.needs_reset = 0
                self.tick = None
            else:
                self.needs_reset = False
                cur = self.dll.evaluate(t)
                nearest = round(cur)
                print(t, nearest)
                if self.last_kick_step == nearest:
                    self.lk_count += 1
                    if self.lk_count > 2:
                        nearest += 1
                else:
                    self.lk_count = 0
                self.dll.update(t, nearest)
                self.last_kick_step = nearest
            self.last_kick = t


    def run(self):
        try:
            compensation = 0.02
            while self.active:
                now = time.time()
                with self.lock:
                    if self.tick is None:
                        self.tick = int(self.dll.evaluate(now + compensation) * self.MUL + 1)
                    else:
                        self.tick += 1
                    next_t = self.dll.reverse(self.tick / self.MUL) - compensation
                    left = next_t - time.time()
                    tick = self.tick
                time.sleep(max(0, left))
                self.parent.clock(tick, self.dll.period / self.MUL)
        except:
            traceback.print_exc()
            os.abort()
