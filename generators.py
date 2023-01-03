import random

from collections import OrderedDict

class Gen(object):
    def __init__(self, parent, state):
        self.parent = parent
        self.state = state

    @property
    def statusText(self):
        return "-"
    
    def ctl_active(self, down, vel):
        pass

    def ctl_key(self, state, start, end, vel, **kw):
        pass

    def deselect(self):
        pass

    def clock(self, tick, period):
        pass

class GenPattern(Gen):
    CONFLICTS = ("sweep_right", "sweep_left", "random")

    def ctl_active(self, down, vel):
        if down:
            if self.parent.state["active"]:
                self.parent.setActive(False)
            else:
                if not self.parent.state["sticky"]:
                    chid = self.parent.chid
                    for ch in self.parent._parent.channels:
                        if ch.chid == chid:
                            continue
                        if ch.state["gen"]["type"] in self.CONFLICTS and not ch.state["sticky"]:
                            ch.setActive(False)
                self.parent.setActive(True)

class GenKey(Gen):
    NAME = "Key"
    CONFLICTS = ("key", "left", "right")
    def __init__(self, parent, state):
        super().__init__(parent, state)
    
    def ctl_active(self, down, vel):
        if down:
            if not self.parent.state["sticky"]:
                chid = self.parent.chid
                for ch in self.parent._parent.channels:
                    if ch.chid == chid:
                        continue
                    if ch.state["gen"]["type"] in self.CONFLICTS and not ch.state["sticky"]:
                        ch.setActive(False)
            self.parent.setActive(True)

    def ctl_key(self, state, start, end, vel, **kw):
        if state:
            self.parent.synth.noteon(start, end, vel)
        else:
            self.parent.synth.noteoff(start, end, vel)

    def deselect(self):
        self.parent.synth.alloff()

class GenOneShot(Gen):
    NAME = "OneShot"

    def __init__(self, parent, state):
        super().__init__(parent, state)
        self.pstart = None
        self.pend = None

    def ctl_active(self, down, vel):
        start, end = 0, 1.0
        if down:
            self.parent.synth.noteon(start, end, vel)
            self.pstart = start
            self.pend = end
        elif self.pstart is not None:
            self.parent.synth.noteoff(self.pstart, self.pend, vel)

    def ctl_key(self, state, start, end, vel):
        if state:
            self.parent.synth.noteon(start, end, vel)
        else:
            self.parent.synth.noteoff(start, end, vel)

class GenKeyRight(GenKey):
    NAME = "Key Right"
    CONFLICTS = ("key", "key_right")

    def ctl_key(self, state, start, end, vel, **kw):
        if kw.get("area", None) == "right":
            super().ctl_key(state, start, end, vel)

class GenKeyLeft(GenKey):
    NAME = "Key Left"
    CONFLICTS = ("key", "key_left")

    def ctl_key(self, state, start, end, vel, **kw):
        if kw.get("area", None) == "left":
            super().ctl_key(state, start, end, vel)

class GenSubdivided(GenPattern):
    @property
    def width(self):
        return max(1, int(self.parent.state["gen"].get("param", 0) / 126 * 32))

    @property
    def statusText(self):
        return "W: %d" % self.width
    
    def clock(self, tick, period):
        loop = int(24 * 4 * 2**self.parent.state["gen"].get("timebase", 0))
        width = self.width
        tick %= loop
        a = width * tick // loop
        b = width * (tick + 1) // loop
        dur = period * loop / width
        for i in range(width):
            lp = i * loop // width
            if lp == tick:
                self.trigger(i, width, dur)


class GenSweepRight(GenSubdivided):
    NAME = "Sweep R"

    def trigger(self, pos, width, dur):
        self.parent.synth.noteon(pos / width, (pos + 1) / width, 127, dur)

class GenSweepLeft(GenSubdivided):
    NAME = "Sweep L"

    def trigger(self, pos, width, dur):
        pos = width - pos - 1
        self.parent.synth.noteon(pos / width, (pos + 1) / width, 127, dur)

class GenRandom(GenPattern):
    NAME = "Random"

    @property
    def width(self):
        return self.parent.state["gen"].get("param", 0) / 127.0

    @property
    def mult(self):
        return max(1, int(self.parent.state["gen"].get("param2", 0) / 126.0 * 16))

    @property
    def statusText(self):
        return "%d%% ×%d" % (100 * self.width, self.mult)
    
    def clock(self, tick, period):
        loop = int(24 * 4 * 2**self.parent.state["gen"].get("timebase", 0))
        dur = period * loop
        w = self.width
        if tick % loop == 0:
            for i in range(self.mult):
                x = random.uniform(0, 1 - w)
                self.parent.synth.noteon(x, x + w, 127, dur)

GENS = OrderedDict(
    key=GenKey,
    key_right=GenKeyRight,
    key_left=GenKeyLeft,
    oneshot=GenOneShot,
    
    sweep_right=GenSweepRight,
    sweep_left=GenSweepLeft,
    random=GenRandom,
)
