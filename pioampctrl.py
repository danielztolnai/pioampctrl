#!/usr/bin/env python
import socket
import select
import threading
import os
from gi.repository import Gtk
from gi.repository import Gdk
from gi.repository import AppIndicator3 as appindicator

TCP_IP = '192.168.213.192'
TCP_PORTS = (23, 8102, 49152, 49153, 49154)


class avrConnection:
    def __init__(self, host, ports):
        self.host = host
        self.ports = ports
        self.avr = None
        self.worker = None
        self.buffer = bytes()
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.connect()

    def connect(self):
        connected = False
        for port in self.ports:
            try:
                self.socket.connect((self.host, port))
            except socket.error:
                continue
            connected = True
            break

        if connected is False:
            raise socket.error('Could not connect to the device')

    def checkConnection(self):
        err = self.socket.getsockopt(socket.SOL_SOCKET, socket.SO_ERROR)
        if err != 0:
            raise socket.error(err, os.strerror(err))

    def close(self):
        self.running = False
        self.worker.join()
        self.socket.close()

    def loop(self):
        self.running = True
        rsl = (self.socket,)
        while self.running:
            if self.writable():
                wsl = rsl
            else:
                wsl = ()

            r, w, e = select.select(rsl, wsl, rsl, 0.5)

            if r != []:
                self.read()
            if w != []:
                self.write()

    def runInThread(self):
        self.worker = threading.Thread(target=self.loop)
        self.worker.start()

    def setController(self, avrControllerInstance):
        self.avr = avrControllerInstance

    def writable(self):
        return (len(self.buffer) > 0)

    def read(self):
        self.checkConnection()
        line = self.socket.recv(1024).decode(encoding='UTF-8').strip()
        lines = line.split('\n')
        for line in lines:
            self.avr.parseMessage(line.strip())

    def write(self):
        self.checkConnection()
        sent = self.socket.send(self.buffer)
        self.buffer = self.buffer[sent:]

    def sendCommand(self, message):
        self.buffer += message.encode('UTF-8')


class avrController:
    def __init__(self):
        self.volumeLimits = {'min': -80, 'max': 12, 'step': 0.5}
        self.speakerConfigs = {0: 'Off', 1: 'A', 2: 'B', 3: 'AB'}
        self.dispatch = {'VOL': self.parseVolume,
                         'PWR': self.parsePower,
                         'RGB': self.parseInputName,
                         'FN':  self.parseActiveInput,
                         'SPK': self.parseSpeakerConfig,
                         'FL':  self.parseDisplayText}
        self.inputs = {25: '25',  4:  '4',  6:  '6', 15: '15',
                       19: '19', 20: '20', 21: '21', 22: '22',
                       23: '23', 38: '38', 44: '44', 45: '45',
                       17: '17',  5:  '5',  1:  '1',  2:  '2',
                       33: '33'}
        self.connection = None
        self.menu = None
        # Device parameters
        self.power = 0
        self.volume = -50.0
        self.input = 4
        self.speaker = 1
        self.lcd = 'Off'

    # Get initial values
    def initialize(self):
        self.getPower()
        self.getVolume()
        self.getActiveInput()
        self.getSpeakerConfig()
        self.getInputNames()

    # Menu
    def setMenu(self, menu):
        self.menu = menu

    def refreshMenu(self, message):
        if self.menu is None:
            return False
        self.menu.refresh(message)

    # Connection
    def setConnection(self, connector):
        self.connection = connector

    def sendCommand(self, message):
        if self.connection is None:
            return False
        message = '\r\n' + message + '\r\n'
        self.connection.sendCommand(message)

    # Line dispatcher
    def parseMessage(self, line):
        for cmd, func in self.dispatch.items():
            if line.startswith(cmd):
                func(line)
                self.refreshMenu(cmd)

    # Volume
    def parseVolume(self, line):
        volume = int(line[3:6])
        self.volume = float(-80.5 + 0.5 * volume)
        print('Volume is ' + str(self.volume) + ' dB')
        return self.volume

    def getVolume(self):
        self.sendCommand("?V")

    def setVolume(self, dB):
        if self.power != 1:
            return False
        if dB == self.volume:
            return True
        volume = int((dB + 80.5) / 0.5)
        volume = min(max(volume, 1), 185)
        volume = str(volume).zfill(3)
        self.sendCommand(volume + "VL")

    def increaseVolume(self):
        if self.power != 1:
            return False
        self.sendCommand("VU")

    def decreaseVolume(self):
        if self.power != 1:
            return False
        self.sendCommand("VD")

    # Power
    def parsePower(self, line):
        self.power = 1 - int(line[3])
        print('Power is ' + str(self.power))
        return self.power

    def getPower(self):
        self.sendCommand("?P")

    def setPower(self, power=2):
        if int(power) == self.power:
            return True
        else:
            self.sendCommand("PZ")

    # Input name
    def parseInputName(self, line):
        inputChannel = int(line[3:5])
        inputName = str(line[6:])
        self.inputs[inputChannel] = inputName
        print('Name of channel ' + str(inputChannel) + ' is ' + str(inputName))
        return self.inputs[inputChannel]

    def getInputName(self, ch):
        self.sendCommand("?RGB" + str(ch).zfill(2))

    def getInputNames(self):
        chList = self.inputs.items()
        for ch, _ in chList:
            self.getInputName(ch)

    def setInputName(self, ch, name):
        if self.power != 1:
            return False
        self.sendCommand(str(name)[:14] + "1RGB" + str(ch).zfill(2))

    # Input channel
    def parseActiveInput(self, line):
        self.input = int(line[2:4])
        print('Active input is '
              + self.inputs[self.input]
              + ' (' + str(self.input)
              + ')')
        return self.input

    def getActiveInput(self):
        self.sendCommand("?F")

    def setActiveInput(self, ch):
        if self.power != 1:
            return False
        if ch == self.input:
            return True
        self.sendCommand(str(ch).zfill(2) + "FN")

    # Speaker configuration
    def parseSpeakerConfig(self, line):
        self.speaker = int(line[3])
        print('Speaker configuration is ' + str(self.speaker))
        return self.speaker

    def getSpeakerConfig(self):
        self.sendCommand("?SPK")

    def setSpeakerConfig(self, sp):
        if self.power != 1:
            return False
        if sp == self.speaker:
            return True
        self.sendCommand(str(sp) + "SPK")

    # LCD information
    def parseDisplayText(self, line):
        line = line[4:]
        text = ""
        for i in range(14):
            num_hex = line[i*2:(i+1)*2]
            text += chr(int(num_hex, base=16))
        self.lcd = text.strip()
        print('LCD message: ' + str(self.lcd))
        return self.lcd

    def getDisplayText(self):
        self.sendCommand("?FL")


class avrIndicator:
    class ChannelMenuItem(Gtk.RadioMenuItem):
        def set_channel(self, ch):
            self.ch = ch

        def get_channel(self):
            return self.ch

    def __init__(self, avrControllerInstance):
        self.avr = avrControllerInstance
        path = os.path.dirname(os.path.realpath(__file__))
        self.indicator = appindicator.Indicator.new(
                            'avrcontroller',
                            os.path.join(path, 'amp.svg'),
                            appindicator.IndicatorCategory.HARDWARE
                        )
        self.indicator.set_status(appindicator.IndicatorStatus.ACTIVE)
        self.indicator.set_menu(self.buildMenu())
        self.indicator.connect('scroll-event', self.volumeScroll)

    def run(self):
        Gtk.main()

    # Menu item creators
    def createPowerButton(self):
        item = Gtk.CheckMenuItem('Power')
        item.connect('button-press-event', self.itemCmd, self.avr.setPower)
        return item

    def createVolumeButton(self):
        item = Gtk.MenuItem('Volume')
        item.connect('button-press-event', self.itemCmd, self.volumeCmd)
        item.set_sensitive(self.avr.power)
        return item

    def createSelectorMenu(self, label, options, func, value):
        submenu = Gtk.Menu()
        item = None
        for ch, name in options.items():
            item = self.ChannelMenuItem(group=item, label=name)
            item.set_channel(ch)
            if ch == value:
                item.set_active(True)
            item.connect('button-press-event', self.itemCmd, func, ch)
            submenu.append(item)
        item = Gtk.MenuItem(label)
        item.set_submenu(submenu)
        item.set_sensitive(self.avr.power)
        return item

    def createQuitButton(self):
        item = Gtk.MenuItem('Quit')
        item.connect('button-press-event', self.itemCmd, Gtk.main_quit)
        return item

    # Menu builder
    def buildMenu(self):
        self.menu = Gtk.Menu()

        self.menu.append(self.createPowerButton())
        self.menu.append(self.createVolumeButton())
        self.menu.append(self.createSelectorMenu('Input channel',
                                                 self.avr.inputs,
                                                 self.avr.setActiveInput,
                                                 self.avr.input))
        self.menu.append(self.createSelectorMenu('Speaker setup',
                                                 self.avr.speakerConfigs,
                                                 self.avr.setSpeakerConfig,
                                                 self.avr.speaker))
        self.menu.append(self.createQuitButton())

        self.menu.show_all()
        return self.menu

    # Refresh functions
    def refresh(self, cmd):
        dispatch = {'VOL': ('Volume',        self.refreshVolume),
                    'PWR': ('Power',         self.refreshPower),
                    'RGB': ('Input channel', self.refreshInputName),
                    'FN':  ('Input channel', self.refreshActiveInput),
                    'SPK': ('Speaker setup', self.refreshSpeakerConfig),
                    'FL':  ('None',          None)}
        for i in self.menu.get_children():
            if i.get_label().startswith(dispatch[cmd][0]):
                dispatch[cmd][1](i)

    def refreshVolume(self, menu_item):
        menu_item.set_label('Volume: ' + str(self.avr.volume) + ' dB')

    def refreshPower(self, menu_item):
        menu_item.set_active(self.avr.power)
        for i in self.menu.get_children():
            if i == menu_item:
                continue
            if i.get_label() == 'Quit':
                continue
            i.set_sensitive(self.avr.power)

    def refreshInputName(self, menu_item):
        for ch in menu_item.get_submenu().get_children():
            ch.set_label(self.avr.inputs[ch.get_channel()])

    def refreshActiveInput(self, menu_item):
        for ch in menu_item.get_submenu().get_children():
            if ch.get_channel() == self.avr.input:
                ch.set_active(True)

    def refreshSpeakerConfig(self, menu_item):
        for ch in menu_item.get_submenu().get_children():
            if ch.get_channel() == self.avr.speaker:
                ch.set_active(True)

    # Command helpers
    def itemCmd(self, menu_item, button_event, command, *args):
        command(*args)

    def volumeCmd(self):
        v = self.getSlider("Volume (dB)",
                           self.avr.volumeLimits['min'],
                           self.avr.volumeLimits['max'],
                           -self.avr.volumeLimits['step'],
                           self.avr.volume)
        self.avr.setVolume(v)

    def getSlider(self, text, smin, smax, sstep, svalue):
        dialog = Gtk.MessageDialog(
            None, 0,
            Gtk.MessageType.QUESTION,
            Gtk.ButtonsType.OK_CANCEL,
            text)
        scale = Gtk.Scale().new_with_range(0, smin, smax, sstep)
        scale.set_digits(1)
        scale.set_value(svalue)
        hbox = Gtk.Box()
        hbox.pack_end(scale, True, True, 0)
        dialog.vbox.pack_end(hbox, True, True, 0)
        dialog.show_all()
        dialog.run()
        newValue = scale.get_value()
        dialog.destroy()
        return newValue

    def volumeScroll(self, indicator_item, value, direction):
        if direction == Gdk.ScrollDirection.DOWN:
            self.avr.decreaseVolume()
        elif direction == Gdk.ScrollDirection.UP:
            self.avr.increaseVolume()


def main():
    controller = avrController()
    connection = avrConnection(TCP_IP, TCP_PORTS)
    menu = avrIndicator(controller)

    connection.setController(controller)
    controller.setConnection(connection)
    controller.setMenu(menu)
    controller.initialize()

    connection.runInThread()
    menu.run()
    connection.close()
    print('Bye!')


if __name__ == "__main__":
    main()
