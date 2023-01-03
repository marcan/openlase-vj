import select, time

from pyalsa.alsaseq import *
from PyQt5.QtCore import QSocketNotifier

class MIDIController(object):
    def __init__(self, parent, in_ports, out_ports):
        self.parent = parent

        self.seq = seq = Sequencer(name = 'default',
                                   clientname = "lvj",
                                   streams = SEQ_OPEN_DUPLEX,
                                   mode = SEQ_NONBLOCK)

        caps = SEQ_PORT_CAP_WRITE | SEQ_PORT_CAP_SUBS_WRITE
        for n in in_ports:
            port = seq.create_simple_port(name = n,
                                        type = SEQ_PORT_TYPE_MIDI_GENERIC
                                            | SEQ_PORT_TYPE_APPLICATION,
                                        caps = caps)
            setattr(self, n, port)

        caps = SEQ_PORT_CAP_READ | SEQ_PORT_CAP_SUBS_READ
        for n in out_ports:
            port = seq.create_simple_port(name = n,
                                        type = SEQ_PORT_TYPE_MIDI_GENERIC
                                            | SEQ_PORT_TYPE_APPLICATION,
                                        caps = caps)
            setattr(self, n, port)

        self.notifiers = []
        
        class RegisterNotifier(object):
            def register(fd, events):
                if events & select.POLLIN:
                    sn = QSocketNotifier(fd, QSocketNotifier.Read)
                    sn.activated.connect(self.poll)
                    self.notifiers.append(sn)
                elif events == select.POLLOUT:
                    sn = QSocketNotifier(fd, QSocketNotifier.Write)
                    sn.activated.connect(self.poll)
                    self.notifiers.append(sn)
                elif events == select.POLLERR:
                    sn = QSocketNotifier(fd, QSocketNotifier.Exception)
                    sn.activated.connect(self.poll)
                    self.notifiers.append(sn)
        
        self.seq.register_poll(RegisterNotifier)
    
    def poll(self):
        for ev in self.seq.receive_events(0,100):
            data = ev.get_data()
            port = int(ev.dest[1])
            if ev.type in (SEQ_EVENT_NOTEON, SEQ_EVENT_NOTEOFF):
                print("NOTE", port, data["note.channel"],
                                "-+"[ev.type == SEQ_EVENT_NOTEON], data["note.note"],
                                data["note.velocity"])
                self.note_event(ev.dest[1], data["note.channel"],
                                ev.type == SEQ_EVENT_NOTEON, data["note.note"],
                                data["note.velocity"])
            elif ev.type == SEQ_EVENT_CONTROLLER:
                print("CTL", port, data["control.channel"],
                                data["control.param"], data["control.value"])
                self.ctl_event(ev.dest[1], data["control.channel"],
                                data["control.param"], data["control.value"])
            elif ev.type == SEQ_EVENT_PITCHBEND:
                print("PB", port, data["control.channel"],
                                data["control.value"])
                self.pb_event(ev.dest[1], data["control.channel"],
                                data["control.value"])
            #print(ev.get_data())

    def send_note(self, port, ch, state, note, vel):
        event = SeqEvent(type=(SEQ_EVENT_NOTEOFF if not state else SEQ_EVENT_NOTEON))
        event.set_data({'note.channel': ch, 'note.note': note, 'note.velocity': vel})
        event.source = (self.seq.client_id, port)
        self.seq.output_event(event)
        self.seq.drain_output()
    
    def note_event(self, port, ch, state, note, v):
        pass

    def ctl_event(self, port, ch, ctl, v):
        pass

    def pb_event(self, port, ch, v):
        pass

ST_OFF = 0
ST_HOLD = 1
ST_ACTIVE = 2
ST_REL = 3

class LaunchKeyController(MIDIController):
    
    def __init__(self, parent):
        super().__init__(parent, ["key", "ctl"], ["fb"])
        time.sleep(0.2)
        self.send_note(self.fb, 15, True, 12, 127)
        self.send_note(self.fb, 15, True, 13, 0)
        self.send_note(self.fb, 15, True, 15, 127)
        self.cpick_state = 0
        self.bpm_color = 63
        self.bpm_color2 = 63
        self.alt = False
        self.edit = False
        self.selector = False

    def colormap(self, c, bright):
        if c == 0:
            return 0
        elif c == 1:
            if bright == 0:
                return 71
            else:
                return bright
        else:
            return c * 4 + 3 - bright - 4

    def trigger_note(self, state, start, end, vel, **kw):
        self.parent.cur_scene.ctl_key(state, start, end, vel, **kw)

    def note_event(self, port, ch, state, note, v):
        cursc = self.parent.cur_scene
        curch = cursc.cur_channel

        if port == self.ctl:
            if ch == 15:
                if note == 13 and v == 0:
                    #self.send_note(self.fb, 15, True, 13, 127)
                    self.update_leds()
                    return

                if note == 15 and v == 0:
                    self.send_note(self.fb, 15, True, 15, 127)
                    self.send_note(self.fb, 15, True, 16, 127)
                    self.update_leds()
                    return

                if note == 120:
                    if state:
                        if self.cpick_state in (ST_REL, ST_OFF):
                            self.cpick_state = ST_HOLD
                        elif self.cpick_state in (ST_HOLD, ST_ACTIVE):
                            self.cpick_state = ST_OFF
                    else:
                        if self.cpick_state == ST_HOLD:
                            self.cpick_state = ST_ACTIVE
                        elif self.cpick_state == ST_REL:
                            self.cpick_state = ST_OFF
                    self.update_leds()
                    return

                if note == 104:
                    self.selector = state
                    self.update_leds()

                if note == 16:
                    self.alt = v > 0
                    return
                
                if self.cpick_state == ST_REL and not state and (96 <= note <= 103 or 112 <= note <= 119):
                    self.cpick_state = ST_OFF
                    return

                if self.cpick_state == ST_OFF:
                    if 96 <= note <= 102:
                        if self.alt or self.selector:
                            cursc.focusChannel(note - 96)
                            self.update_leds()
                        else:
                            cursc.channels[note - 96].ctl_active(state, v)
                    elif 112 <= note <= 118:
                        if self.alt or self.selector:
                            cursc.focusChannel(note - 112 + 7)
                            self.update_leds()
                        else:
                            cursc.channels[note - 112 + 7].ctl_active(state, v)
                    if state and note == 103:
                        self.parent.bpm.reset()
                    if state and note == 119:
                        self.parent.bpm.kick()
                    return

                elif self.cpick_state in (ST_HOLD, ST_ACTIVE) and state:
                    if 96 <= note <= 103 or 112 <= note <= 119:
                        color = note - 96 if note <= 103 else note - 112 + 8
                        if self.cpick_state == ST_HOLD:
                            self.cpick_state = ST_REL

                        curch.ctl_color(color)
                        self.update_leds()
                    return

        if port == self.key:
                if note == 48:   self.trigger_note(state, 0/10, 1/10, v, area="left")
                elif note == 50: self.trigger_note(state, 1/10, 2/10, v, area="left")
                elif note == 52: self.trigger_note(state, 2/10, 3/10, v, area="left")
                elif note == 53: self.trigger_note(state, 3/10, 4/10, v, area="left")
                elif note == 55: self.trigger_note(state, 4/10, 5/10, v, area="left")

                elif note == 49: self.trigger_note(state, 0/10, 2.5/10, v, area="left")
                elif note == 51: self.trigger_note(state, 2.5/10, 5/10, v, area="left")

                elif note == 57: self.trigger_note(state, 5/10, 6/10, v, area="left")
                elif note == 59: self.trigger_note(state, 6/10, 7/10, v, area="left")
                elif note == 60: self.trigger_note(state, 7/10, 8/10, v, area="left")
                elif note == 62: self.trigger_note(state, 8/10, 9/10, v, area="left")
                elif note == 64: self.trigger_note(state, 9/10, 10/10, v, area="left")

                elif note == 61: self.trigger_note(state, 5/10, 7.5/10, v, area="left")
                elif note == 63: self.trigger_note(state, 7.5/10, 10/10, v, area="left")

                elif note == 54: self.trigger_note(state, 0/10, 5/10, v, area="left")
                elif note == 56: self.trigger_note(state, 0/10, 10/10, v, area="left")
                elif note == 58: self.trigger_note(state, 5/10, 10/10, v, area="left")

                elif note == 65:
                    self.trigger_note(state, 4/10, 5/10, v, area="right")
                    self.trigger_note(state, 5/10, 6/10, v, area="right")
                elif note == 67:
                    self.trigger_note(state, 3/10, 4/10, v, area="right")
                    self.trigger_note(state, 6/10, 7/10, v, area="right")
                elif note == 69:
                    self.trigger_note(state, 2/10, 3/10, v, area="right")
                    self.trigger_note(state, 7/10, 8/10, v, area="right")
                elif note == 71:
                    self.trigger_note(state, 1/10, 2/10, v, area="right")
                    self.trigger_note(state, 8/10, 9/10, v, area="right")
                elif note == 72:
                    self.trigger_note(state, 0/10, 1/10, v, area="right")
                    self.trigger_note(state, 9/10, 10/10, v, area="right")

                elif note == 66:
                    self.trigger_note(state, 2.5/10, 5/10, v, area="right")
                    self.trigger_note(state, 5/10, 7.5/10, v, area="right")
                elif note == 68:
                    self.trigger_note(state, 0/10, 10/10, v, area="right")
                elif note == 70:
                    self.trigger_note(state, 0/10, 2.5/10, v, area="right")
                    self.trigger_note(state, 7.5/10, 10/10, v, area="right")

    def ctl_event(self, port, ch, ctl, v):
        cursc = self.parent.cur_scene
        curch = cursc.cur_channel

        if port == self.ctl:
            if ch == 15:
                if ctl == 21:
                    curch.ctl_fader(v)
                if ctl == 22:
                    curch.ctl_timebase(v)
                elif ctl == 23:
                    curch.ctl_param(0, v)
                elif ctl == 24:
                    curch.ctl_param(1, v)
                elif ctl == 25:
                    curch.ctl_adsr("a", v)
                elif ctl == 26:
                    curch.ctl_adsr("d", v)
                elif ctl == 27:
                    curch.ctl_adsr("s", v)
                elif ctl == 28:
                    curch.ctl_adsr("r", v)
            if ctl == 7:
                self.parent.laser.bright = int(v / 127 * 255)
        elif port == self.key:
            if ctl == 21:
                curch.ctl_fader(v)
            
    def pb_event(self, port, ch, v):
        pass

    def clock(self, tick):
        tick -= 2
        beat = tick // 24
        self.bpm_color = 71
        self.bpm_color2 = 71
        if (tick % 24) < 4:
            if beat % 4 == 0:
                self.bpm_color = 60
            self.bpm_color2 = 17
        if self.cpick_state in (ST_HOLD, ST_ACTIVE):
            return
        self.send_note(self.fb, 15, True, 103, self.bpm_color)
        self.send_note(self.fb, 15, True, 119, self.bpm_color2)

    def update_leds(self):
        if self.cpick_state in (ST_HOLD, ST_ACTIVE):
            for i in range(16):
                key = 96 + i if i < 8 else 112 + i - 8
                active = i == self.parent.cur_scene.cur_channel.state["color"]
                self.send_note(self.fb, 15, True, key, self.colormap(i, 2 if active else 0))
            self.send_note(self.fb, 15, True, 120, 60)
            return

        self.send_note(self.fb, 15, True, 104, 60 if self.selector else 63)
        self.send_note(self.fb, 15, True, 120, 63)

        cursc = self.parent.cur_scene
        if cursc is None:
            return
        for i, ch in enumerate(cursc.channels):
            key = 96 + i if i < 7 else 112 + i - 7
            hue = ch.state["color"]
            bright = 0
            if ch.state["active"]:
                bright = 2
            if self.selector and ch.focus:
                bright = 3
                if hue == 0:
                    hue = 1
                    bright = 1
            self.send_note(self.fb, 15, True, key, self.colormap(hue, bright))

        self.send_note(self.fb, 15, True, 103, self.bpm_color)
        self.send_note(self.fb, 15, True, 119, self.bpm_color2)
