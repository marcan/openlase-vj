import threading, os, traceback, math, time

import pylase as ol

class Renderer(threading.Thread):
    def __init__(self, parent):
        self.parent = parent
        super().__init__()
        self.active = True
        self.bright = 255
        self.busy_scenes = {}

    def main(self):
        params = ol.RenderParams()
        params.render_flags = ol.RENDER_NOREORDER
        params.on_speed = 2/100.0
        params.off_speed = 2/70.0
        params.flatness = 0.000002
        params.corner_dwell = 2
        params.start_dwell = 2
        params.end_dwell = 2
        params.curve_dwell = 0
        params.curve_angle = math.cos(30.0 * (math.pi / 180.0))
        params.snap = 0.0001
        ol.init(2, num_outputs=2)
        ol.setRenderParams(params)
        ol.setScissor((-0.951, -0.951), (0.951, 0.951))
        while self.active:
            ol.loadIdentity()
            ol.scale((0.95, 0.95))
            ol.translate((-1, 0))
            ol.scale((2, 1))
            ol.resetColor()
            ol.multColor(self.bright * 0x010101)
            self.render()
            #ol.line((0,0.8), (1,0.8), ol.C_WHITE)
            ol.renderFrame(100)

        ol.shutdown()

    def run(self):
        try:
            self.main()
        except:
            traceback.print_exc()
            os.abort()

    def render(self):
        cursc = self.parent.cur_scene
        voices = self.render_scene(cursc)
        if voices > 0:
            self.busy_scenes[cursc] = time.time()
        for sc, t in list(self.busy_scenes.items()):
            if sc is not cursc:
                voices = self.render_scene(sc)
                if voices > 0:
                    self.busy_scenes[sc] = time.time()
                elif time.time() > (1 + t):
                    del self.busy_scenes[sc]

    def render_scene(self, scene):
        total_voices = 0
        for ch in scene.channels:
            mode = ch.state["map"]
            if mode == "span":
                ol.setOutput(0)
                ol.pushMatrix()
                ol.scale((2, 1))
                voices = ch.synth.render()
                ol.popMatrix()

                ol.setOutput(1)
                ol.pushMatrix()
                ol.translate((-1, 0))
                ol.scale((2, 1))
                ch.synth.render()
                ol.popMatrix()
            if mode == "clone":
                ol.setOutput(0)
                voices = ch.synth.render()
                ol.setOutput(1)
                ch.synth.render()
            elif mode == "mirror":
                ol.setOutput(0)
                voices = ch.synth.render()
                ol.setOutput(1)
                ol.pushMatrix()
                ol.translate((1, 0))
                ol.scale((-1, 1))
                ch.synth.render()
                ol.popMatrix()
            if mode == "left":
                ol.setOutput(0)
                voices = ch.synth.render()
            if mode == "right":
                ol.setOutput(1)
                voices = ch.synth.render()
            total_voices += voices
        return total_voices
