#!/usr/bin/python3
# -!- coding: utf-8 -!-
import sys, os, subprocess, time, atexit, urllib, base64, json, copy
from pprint import pprint
from collections import OrderedDict
from functools import partial

from PyQt5 import QtWidgets, uic
from PyQt5.QtCore import Qt, QSettings, QCoreApplication, QAbstractListModel, QModelIndex, QItemSelectionModel
from PyQt5.QtGui import QPalette, QColor
from PyQt5.QtWidgets import (QApplication, QMainWindow,
        QWidget, QToolButton, QGroupBox, QGridLayout, QTabWidget,
        QVBoxLayout, QHBoxLayout, QSizePolicy, QLabel, QSpacerItem,
        QComboBox, QFrame, QFileDialog, QListWidgetItem, QAbstractItemView)

from generators import GENS
from voices import BasicSynth, VOICES
from controller import LaunchKeyController

from util import ADSR
from colors import PALETTE
from laser import Renderer
from bpm import BPMThread
from util import gamma

DEFAULT_STATE = {
    "active": False,
    "sticky": False,
    "fader": 127,
    "gen": {
        "type": "key",
        "timebase": 0,
        "param": 0,
        "param2": 0,
    },
    "voice": {
        "type": "bar",
        "env": {
            "a": 0,
            "d": 0,
            "s": 127,
            "r": 0,
        },
        "mult": 1,
    },
    "map": "span",
    "color": 0,
}

OUTPUT_MODES = [
    "span",
    "clone",
    "mirror",
    "left",
    "right",
]

class Channel(QFrame):
    def __init__(self, parent, chid):
        self._parent = parent
        self.chid = chid
        super().__init__(parent)
        uic.loadUi('channel.ui', self)
        self.setFocus(False)
        self.pb_active.setText(str(chid + 1))
        self.cb_gen.clear()
        for k, v in GENS.items():
            self.cb_gen.addItem(v.NAME, k)
        self.cb_gen.currentIndexChanged[int].connect(self.genChanged)

        self.cb_voice.clear()
        for k, v in VOICES.items():
            self.cb_voice.addItem(v.NAME, k)
        self.cb_voice.currentIndexChanged[int].connect(self.voiceChanged)

        self.pb_active.clicked.connect(self.activeChanged)
        self.ck_sticky.clicked.connect(self.stickyChanged)
        
        for i, c in enumerate(PALETTE):
            self.cb_color.addItem("")
            self.cb_color.setItemData(i, QColor(c), Qt.BackgroundRole)
            self.cb_color.setItemData(i, QColor(c), Qt.ForegroundRole)

        self.cb_color.currentIndexChanged[int].connect(self.colorChanged)

        self.state = copy.deepcopy(DEFAULT_STATE)
        self.load(self.state)

        for i in "adsr":
            slider = getattr(self, "env_%s"%i)
            slider.valueChanged.connect(partial(self.sliderMoved, "voice.env.%s" % i))
        
        self.fader.valueChanged.connect(partial(self.sliderMoved, "fader"))
        self.timebase.valueChanged.connect(partial(self.sliderMoved, "gen.timebase"))
        self.gen_p.valueChanged.connect(partial(self.sliderMoved, "gen.param"))
        self.gen_p2.valueChanged.connect(partial(self.sliderMoved, "gen.param2"))
        self.mult.valueChanged.connect(partial(self.sliderMoved, "voice.mult"))
        
        self.cb_map.currentIndexChanged[int].connect(self.mapChanged)

    def updateStatus(self):
        tb = self.state["gen"].get("timebase", 0)
        if tb < 0:
            s = "1/%d" % (2**(-tb))
        else:
            s = "%d/1" % (2**tb)

        self.gen_status.setText("%s | %s" % (s, self.gen.statusText))

    def genChanged(self, index):
        self.state["gen"]["type"] = list(GENS.keys())[index]
        self.gen = GENS[self.state["gen"]["type"]](self, self.state["gen"])
        self.updateStatus()
        self.synth.alloff()
        self.stateChanged()

    def voiceChanged(self, index):
        self.state["voice"]["type"], klass = list(VOICES.items())[index]
        self.synth.voice = klass
        self.stateChanged()

    def mapChanged(self, index):
        self.state["map"] = OUTPUT_MODES[index]
        self.stateChanged()

    def colorChanged(self, index):
        self.state["color"] = index
        self.cb_color.setStyleSheet("* {background-color: #%06x !important;}" % PALETTE[index]);
        self.cb_color.clearFocus()
        self.synth.color = gamma(PALETTE[self.state["color"]])
        self.stateChanged()
        self._parent._parent.controller.update_leds()

    def sliderMoved(self, param, value):
        s = self.state
        p = param
        while "." in p:
            left, p = p.split(".", 1)
            s = s[left]
        s[p] = value
        self.stateChanged()
        if param.startswith("voice.env."):
            self.synth.adsr = ADSR(self.state["voice"]["env"])
        if param.startswith("gen."):
            self.updateStatus()

    def mousePressEvent(self, ev):
        self._parent.focusChannel(self.chid)

    def setFocus(self, focus):
        self.focus = focus
        if self.focus:
            self.setStyleSheet("Channel {border: 1px solid #0f0}");
        else:
            self.setStyleSheet("Channel {border: 1px solid #f00}");

    def setActive(self, active):
        self.pb_active.setChecked(active)
        self.state["active"] = active
        if not active:
            self.synth.alloff()
        #self.stateChanged()
        self._parent._parent.controller.update_leds()

    def activeChanged(self):
        active = self.state["active"] = self.pb_active.isChecked()
        if not active:
            self.synth.alloff()
        #self.stateChanged()
        self._parent._parent.controller.update_leds()

    def stickyChanged(self):
        self.state["sticky"] = self.ck_sticky.isChecked()

    def loadChildren(self):
        self.gen = GENS[self.state["gen"]["type"]](self, self.state["gen"])
        voice = VOICES[self.state["voice"].get("type", "bar")]
        adsr = ADSR(self.state["voice"]["env"])
        self.synth = BasicSynth(self, voice, adsr)
        self.updateStatus()
        for i in "adsr":
            slider = getattr(self, "env_%s"%i)
            slider.setValue(self.state["voice"]["env"][i])
        self.timebase.setValue(self.state["gen"].get("timebase", 0))
        self.gen_p.setValue(self.state["gen"].get("param", 0))
        self.gen_p2.setValue(self.state["gen"].get("param2", 0))
        self.fader.setValue(self.state.get("fader", 127))
        self.mult.setValue(self.state["voice"].get("mult", 127))

    def stateChanged(self):
        print("== %d ==" % self.chid)
        pprint(self.state)

    def load(self, state):
        print("LOAD", state)
        self.state = copy.deepcopy(DEFAULT_STATE)
        self.state.update(copy.deepcopy(state))
        self.stateChanged()
        self.loadChildren()
        self.setActive(False)
        self.cb_gen.setCurrentIndex(list(GENS.keys()).index(self.state["gen"]["type"]))
        self.cb_voice.setCurrentIndex(list(VOICES.keys()).index(self.state["voice"].get("type", "bar")))
        self._parent.activeChannels &= ~(1<<self.chid)
        self.cb_color.setCurrentIndex(self.state["color"])
        self.colorChanged(self.state["color"])
        self.ck_sticky.setChecked(self.state["sticky"])
        self.cb_map.setCurrentIndex(OUTPUT_MODES.index(self.state["map"]))

    def ctl_active(self, down=True, vel=127):
        if self.state["color"] == 0:
            return
        if down:
            self._parent.focusChannel(self.chid)
        self.gen.ctl_active(down, vel)
        self._parent.focusChannel(self.chid)

    def ctl_adsr(self, param, val):
        slider = getattr(self, "env_%s" % param)
        slider.setValue(val)

    def ctl_key(self, state, start, end, velocity, **kw):
        self.gen.ctl_key(state, start, end, velocity, **kw)

    def ctl_color(self, color):
        self.cb_color.setCurrentIndex(color)

    def ctl_param(self, param, val):
        if param == 0:
            self.gen_p.setValue(val)
        elif param == 1:
            self.gen_p2.setValue(val)

    def ctl_fader(self, val):
        self.fader.setValue(val)

    def ctl_timebase(self, val):
        cmin = self.timebase.minimum()
        cmax = self.timebase.maximum()
        val = min(cmax,max(cmin, val / 127.0 * (cmax - cmin + 1) + cmin))
        self.timebase.setValue(val)

class Scene(QWidget):
    def __init__(self, parent, name=None, data=None):
        self.activeChannels = 0
        self._parent = parent
        self.name = name
        super().__init__(parent)
        self.hide()
        parent.channelContainer.layout().addWidget(self)
        self.loadChannels()
        if data is not None:
            self.setState(data)
        self.focusChannel(0)

    def focusChannel(self, chid):
        for i, ch in enumerate(self.channels):
            ch.setFocus(i == chid)

        self.focused = chid

    @property
    def cur_channel(self):
        return self.channels[self.focused]

    def loadChannels(self):
        self.channels = []
        l = QGridLayout(self)
        l.setContentsMargins(0, 0, 0, 0)
        for i in range(7):
            ch = Channel(self, i)
            l.addWidget(ch, 0, i)
            self.channels.append(ch)
        for i in range(7):
            ch = Channel(self, 7+i)
            l.addWidget(ch, 1, i)
            self.channels.append(ch)

    @property
    def state(self):
        return {
            "name": self.name,
            "channels": [i.state for i in self.channels],
        }

    def setState(self, state):
        self.name = state["name"]
        for i, j in enumerate(self.channels):
            j.load(state["channels"][i])
    
    def ctl_key(self, state, start, end, velocity, **kw):
        for i in self.channels:
            if i.state["active"]:
                i.ctl_key(state, start, end, velocity, **kw)

    def select(self):
        pass
        
    def deselect(self):
        for i in self.channels:
            i.gen.deselect()

    def clock(self, tick, period):
        for i in self.channels:
            if i.state["active"]:
                i.gen.clock(tick, period)

class SceneListModel(QAbstractListModel):
    def __init__(self, listobj, parent=None, *args):
        self._parent = parent
        QAbstractListModel.__init__(self, parent, *args)
        self.l = listobj

    def rowCount(self, parent=QModelIndex()):
        return len(self.l)

    def data(self, index, role):
        if index.isValid() and role in (Qt.DisplayRole, Qt.EditRole):
            return (self.l[index.row()].name)
        else:
            return None

    def flags(self, idx):
        if idx.isValid():
            return (Qt.ItemIsDragEnabled |
                    Qt.ItemIsSelectable | Qt.ItemIsEnabled | Qt.ItemIsEditable)
        else:
            return (Qt.ItemIsDropEnabled |
                    Qt.ItemIsSelectable | Qt.ItemIsEnabled | Qt.ItemIsEditable)

    def supportedDropActions(self):
        return Qt.MoveAction

    def setData(self, index, data, role=Qt.DisplayRole):
        print("setData", index, data, role)
        if role == Qt.EditRole:
            if not data.strip():
                return False
            for i in self.l:
                if i.name.strip() == data.strip():
                    return False
            self.l[index.row()].name = data
            return True
        elif role == Qt.DisplayRole:
            # ugh hax
            for i, j in enumerate(self.l):
                if i != index.row() and j.name.strip() == data.strip():
                    self.l[i], self.l[index.row()] = self.l[index.row()], self.l[i]
                    return True
        else:
            return False

    def insertRows(self, row, count, parent):
        print("insertRows", row, count)
        self.beginInsertRows(parent, row, (row + (count - 1)))
        new = []
        for i in range(count):
            name = "New scene"
            ctr = 1
            while True:
                for j in (self.l + new):
                    if j.name == name:
                        break
                else:
                    break
                ctr += 1
                name = "New scene (%d)" % ctr
            new.append(Scene(self._parent, name))
        self.l[row:row] = new
        self.endInsertRows()
        return True

    def removeRows(self, row, count, parent):
        if self.rowCount() < 2:
            return False
        print("removeRows", row, count)
        try:
            self.beginRemoveRows(parent, row, row + count - 1)
            for i in self.l[row:row+count]:
                i.deleteLater()
            del self.l[row:row+count]
            self.endRemoveRows()
            return True
        except IndexError:
            self.endRemoveRows()
            return False

    def moveRows(self, parent, sourceRow, count, destParent, destChild):
        print("moveRows", sourceRow, conut, descChild)
        return False

    def replaceList(self, scenes):
        self.beginResetModel()
        for i in self.l:
            i.deleteLater()
        self.l[:] = scenes
        self.endResetModel()

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        uic.loadUi('mainwindow.ui', self)

        self.controller = LaunchKeyController(self)
        self.cur_scene = None

        self.scenes = [
            Scene(self, "Default"),
        ]

        self.cur_scene_idx = 0
        self.cur_scene = self.scenes[self.cur_scene_idx]
        self.sceneList.setModel(SceneListModel(self.scenes, parent=self))
        self.sceneList.setDragDropMode(QAbstractItemView.DragDrop)
        self.sceneList.setDragEnabled(True)
        self.sceneList.setAcceptDrops(True)

        self.cur_scene.show()

        self.sceneList.selectionModel().selectionChanged.connect(self.sceneSelectionChanged)

        self.actionSave.triggered.connect(self.save)
        self.actionLoad.triggered.connect(self.load)

        self.b_sceneAdd.clicked.connect(self.sceneAdd)
        self.b_sceneDel.clicked.connect(self.sceneDel)
        
        self.laser = Renderer(self)
        self.controller.update_leds()
        
        self.bpm = BPMThread(self)
        self.bpm.start()

    def clock(self, tick, period):
        self.controller.clock(tick)
        self.cur_scene.clock(tick, period)

    def sceneSelectionChanged(self, current, previous):
        current = current.indexes()
        if not current:
            return

        self.setCurrentScene(current[0].row())

    def setCurrentScene(self, i):
        self.cur_scene.deselect()
        self.cur_scene.hide()
        self.cur_scene_idx = i
        self.cur_scene = self.scenes[self.cur_scene_idx]
        self.cur_scene.show()
        self.cur_scene.select()

    def sceneAdd(self):
        model = self.sceneList.model()
        model.insertRows(model.rowCount(), 1, QModelIndex())
        self.setCurrentScene(self.sceneList.selectionModel().currentIndex().row())

    def sceneDel(self):
        model = self.sceneList.model()
        model.removeRows(self.cur_scene, 1, QModelIndex())
        self.setCurrentScene(self.sceneList.selectionModel().currentIndex().row())

    def save(self):
        config = {
            "scenes": [i.state for i in self.scenes],
            "cur_scene_idx": self.cur_scene_idx,
        }
        name, _ = QFileDialog.getSaveFileName(self, 'Save Setlist')
        if not name:
            return

        with open(name,'w') as fd:
            json.dump(config, fd)

    def load(self):
        name, _ = QFileDialog.getOpenFileName(self, 'Load Setlist')
        if not name:
            return
        try:
            with open(name,'r') as fd:
                config = json.load(fd)
        except:
            return
        self.loadConfig(config)

    def loadConfig(self, config):
        self.cur_scene.hide()
        scenes = [Scene(self, data=s) for s in config["scenes"]]
        self.sceneList.model().replaceList(scenes)
        self.cur_scene_idx = config.get("cur_scene_idx", 0)
        idx = self.sceneList.model().createIndex(self.cur_scene_idx, 0)
        self.sceneList.selectionModel().setCurrentIndex(idx, QItemSelectionModel.SelectCurrent)
        self.cur_scene = self.scenes[self.cur_scene_idx]
        self.cur_scene.show()
        self.controller.update_leds()

if __name__ == '__main__':
    QCoreApplication.setOrganizationName("marcan")
    QCoreApplication.setOrganizationDomain("marcan")
    QCoreApplication.setApplicationName("LVJ")
    app = QApplication(sys.argv)
    window = MainWindow()
    window.laser.start()
    window.show()
    if len(sys.argv) > 1:
        try:
            with open(sys.argv[1],'r') as fd:
                config = json.load(fd)
                window.loadConfig(config)
        except IOError:
            pass

    rc = app.exec_()
    window.laser.active = False
    window.bpm.active = False
    window.laser.join()
    window.bpm.join()
    sys.exit(rc)
