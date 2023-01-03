import time

def ctime():
    return time.time()

def clamp(x, y, z):
    if x < y:
        return y
    if x > z:
        return z
    return x

def clamp1(x):
    return clamp(x, 0.0, 1.0)

def unmapf(x, f, t):
    return (x - f) / float(t - f)

def mapf(x, f, t):
    return x * (t - f) + f

def shuf(t):
    return math.sin(t**1.1 * 31337)

def ss(x):
    return x * x * (3 - 2 * x)

def ssout(x):
    return ss(x * 0.5) * 2

def ssin(x):
    return ss(0.5 + x * 0.5) * 2 - 1

inf = float("inf")

def gamma(color):
    r, g, b = torgb(color)
    r = ((r / 255.0) ** 2.0) * 255.0
    g = ((g / 255.0) ** 2.0) * 255.0
    b = ((b / 255.0) ** 2.0) * 255.0
    return rgb(r, g, b)

def torgb(color):
    return color>>16, (color>>8) & 0xff, color & 0xff

def rgb(r, g, b):
    r, g, b = min(255, max(0, r)), min(255, max(0, g)), min(255, max(0, b))
    return (int(r) << 16) | (int(g) << 8) | int(b)


class ADSR(object):
    def __init__(self, state):
        self.a = (state["a"] / 127.0) ** 2.0
        self.d = (state["d"] / 127.0) ** 2.0
        self.s = state["s"] / 127.0
        self.r = ((state["r"] / 127.0) ** 2.0) * 4.0
    
    def evaluate(self, t, kt):
        ct = clamp(t, 0, inf)
        if ct < self.a:
            v = unmapf(t, 0, self.a)
        elif ct < (self.d + self.a):
            v = mapf(unmapf(t, self.a, self.d + self.a), 1.0, self.s)
        else:
            v = self.s
            if self.s == 0:
                return None
        if kt is None or ct < kt:
            return v
        if ct > (kt + self.r):
            return None
        if self.r == 0:
            return 0
        return v * mapf(unmapf(ct, kt, kt + self.r), 1.0, 0.0)        
