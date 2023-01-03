from collections import OrderedDict
from util import *

import pylase as ol

class BaseVoice(object):
    def __init__(self, l, r, duration=None):
        self.l = l
        self.r = r
        self.st = ctime()
        self.kt = None
        if duration is not None:
            self.kt = self.st + duration

    def off(self):
        if self.kt is None or self.kt > ctime():
            self.kt = ctime()

    def render(self, adsr, color, mult):
        ct = ctime() - self.st
        v = adsr.evaluate(ct, self.kt - self.st if self.kt is not None else None)
        if v is None:
            return True
        v = v ** 2
        ol.pushColor()
        ol.multColor(color)
        self._render(ct, v, adsr, mult)
        ol.popColor()
        return False

class BarVoice(BaseVoice):
    NAME = "Bar"
    def _render(self, dt, v, adsr, mult):
        for i in range(mult):
            ol.line((self.l, 0), (self.r, 0), ol.C_GREY(int(255 * v)))

class BeamVoice(BaseVoice):
    NAME = "Beam"
    def _render(self, dt, v, adsr, mult):
        x = (self.l + self.r) / 2
        ol.dot((x, 0), mult, ol.C_GREY(int(255 * v)))

class MultiBeamVoice(BaseVoice):
    NAME = "MultiBeam"
    def _render(self, dt, v, adsr, mult):
        x = (self.l + self.r) / 2
        for i in range(10):
            px = (i + 0.5) / 10
            if self.l <= px <= self.r:
                ol.dot((px, 0), mult, ol.C_GREY(int(255 * v)))

class DropVoice(BaseVoice):
    NAME = "Drop"
    def render(self, adsr, color, mult):
        ct = ctime() - self.st
        x = (self.l + self.r) / 2
        dv = max(0.1, adsr.a + adsr.d + adsr.r)
        w = abs(self.l - self.r) / 2
        v = clamp1(1. - ct / dv)
        if v <= 0:
            return True
        w *= (ss(1 - v) + (1 - v)) / 2
        v = 1 - (v ** 3)
        r, g, b = torgb(color)
        cmax = max(r, g, b)
        
        for i in range(mult):
            ol.line((x-w, 0), (x+w, 0), rgb(r - cmax * v, g - cmax * v, b - cmax * v))
        return False

class BasicSynth(object):
    def __init__(self, parent, voice, adsr):
        self.parent = parent
        self.adsr = adsr
        self.voice = voice
        self.voices = {}
        self.color = 0xffffff

    def noteon(self, l, r, vel, duration=None):
        key = (l, r)
        if (l, r) in self.voices:
            del self.voices[(l, r)]
        self.voices[(l, r)] = self.voice(l, r, duration)

    def noteoff(self, l, r, vel):
        print("NOFF", (l, r), self.voices)
        if (l, r) in self.voices:
            self.voices[(l, r)].off()
    
    def alloff(self):
        for k, v in self.voices.items():
            v.off()

    def panic(self):
        self.voices = {}
    
    def render(self):
        if not self.voices:
            return 0
        #print(self.voices.keys())
        voices = 0
        power = int(self.parent.state.get("fader", 127) / 127.0 * 255.0)
        mult = self.parent.state["voice"].get("mult", 1)
        ol.pushColor()
        ol.multColor(ol.C_GREY(power))
        for k, v in sorted(list(self.voices.items())):
            voices += 1
            if v.render(self.adsr, self.color, mult):
                del self.voices[k]
        ol.popColor()
        return voices
        
        
VOICES = OrderedDict(
    bar=BarVoice,
    beam=BeamVoice,
    multi_beam=MultiBeamVoice,
    drop=DropVoice,
)
