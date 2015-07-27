#!/usr/bin/env python

import sys
import time
import serial
from threading import Thread

class RawInput:
    """Gets a single character from standard input.  Does not echo to the screen."""
    def __init__(self):
        try:
            self.impl = RawInputWindows()
        except ImportError:
            self.impl = RawInputUnix()

    def __call__(self): return self.impl()


class RawInputUnix:
    def __init__(self):
        import tty, sys

    def __call__(self):
        import sys, tty, termios
        fd = sys.stdin.fileno()
        old_settings = termios.tcgetattr(fd)
        try:
            tty.setraw(sys.stdin.fileno())
            ch = sys.stdin.read(1)
        finally:
            termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
        return ch


class RawInputWindows:
    def __init__(self):
        import msvcrt

    def __call__(self):
        import msvcrt
        return msvcrt.getch()

class Baudrate:

    VERSION = '1.0'
    READ_TIMEOUT = 5
    BAUDRATES = [
#            "1200",
#            "1800",
#            "2400",
#            "4800",
            "9600",
            "38400",
            "19200",
            "57600",
            "115200",
    ]

    UPKEYS = ['u', 'U', 'A']
    DOWNKEYS = ['d', 'D', 'B']

    MIN_CHAR_COUNT = 25
    WHITESPACE = [' ', '\t', '\r', '\n']
    PUNCTUATION = ['.', ',', ':', ';', '?', '!']
    VOWELS = ['a', 'A', 'e', 'E', 'i', 'I', 'o', 'O', 'u', 'U']

    def __init__(self, port=None, threshold=MIN_CHAR_COUNT, timeout=READ_TIMEOUT, name=None, auto=True, verbose=False):
        self.port = port
        self.threshold = threshold
        self.timeout = timeout
        self.name = name
        self.auto_detect = auto
        self.verbose = verbose
        self.index = len(self.BAUDRATES) - 1
        self.valid_characters = []
        self.ctlc = False
        self.thread = None

        self._gen_char_list()

    def _gen_char_list(self):
        c = ' '

        while c <= '~':
            self.valid_characters.append(c)
            c = chr(ord(c) + 1)

        for c in self.WHITESPACE:
            if c not in self.valid_characters:
                self.valid_characters.append(c)

    def _print(self, data):
        if self.verbose:
            sys.stderr.write(data)

    def Open(self):
        self.serial = serial.Serial(self.port, timeout=self.timeout)
        self.NextBaudrate(0)

    def NextBaudrate(self, updn):

        self.index += updn

        if self.index >= len(self.BAUDRATES):
            self.index = 0
        elif self.index < 0:
            self.index = len(self.BAUDRATES) - 1

        sys.stderr.write('\n\n@@@@@@@@@@@@@@@@@@@@@ Baudrate: %s @@@@@@@@@@@@@@@@@@@@@\n\n' % self.BAUDRATES[self.index])

        self.serial.flush()
        self.serial.baudrate = self.BAUDRATES[self.index]
        self.serial.flush()

    def Detect(self):
        count = 0
        whitespace = 0
        punctuation = 0
        vowels = 0
        start_time = 0
        timed_out = False
        clear_counters = False

        if not self.auto_detect:
            self.thread = Thread(None, self.HandleKeypress, None, (self, 1))
            self.thread.start()

        while True:
            if start_time == 0:
                start_time = time.time()

            byte = self.serial.read(1)

            if byte:
                if self.auto_detect and byte in self.valid_characters:
                    if byte in self.WHITESPACE:
                        whitespace += 1
                    elif byte in self.PUNCTUATION:
                        punctuation += 1
                    elif byte in self.VOWELS:
                        vowels += 1

                    count += 1
                else:
                    clear_counters = True

                self._print(byte)

                if count >= self.threshold and whitespace > 0 and punctuation > 0 and vowels > 0:
                    break
                elif (time.time() - start_time) >= self.timeout:
                    timed_out = True
            else:
                timed_out = True

            if timed_out and self.auto_detect:
                start_time = 0
                self.NextBaudrate(-1)
                clear_counters = True
                timed_out = False

            if clear_counters:
                whitespace = 0
                punctuation = 0
                vowels = 0
                count = 0
                clear_counters = False

            if self.ctlc:
                break

        self._print("\n")
        return self.BAUDRATES[self.index]

    def HandleKeypress(self, *args):
        userinput = RawInput()

        while not self.ctlc:
            c = userinput()
            if c in self.UPKEYS:
                self.NextBaudrate(1)
            elif c in self.DOWNKEYS:
                self.NextBaudrate(-1)
            elif c == '\x03':
                self.ctlc = True

    def MinicomConfig(self, name=None):
        success = True

        if name is None:
            name = self.name

        config =  "########################################################################\n"
        config += "# Minicom configuration file - use \"minicom -s\" to change parameters.\n"
        config += "pu port             %s\n" % self.port
        config += "pu baudrate         %s\n" % self.BAUDRATES[self.index]
        config += "pu bits             8\n"
        config += "pu parity           N\n"
        config += "pu stopbits         1\n"
        config += "pu rtscts           No\n"
        config += "########################################################################\n"

        if name is not None and name:
            try:
                open("/etc/minicom/minirc.%s" % name, "w").write(config)
            except Exception, e:
                print "Error saving minicom config file:", str(e)
                success = False

        return (success, config)

    def Close(self):
        self.ctlc = True
        self.serial.close()



if __name__ == '__main__':

    import subprocess
    from getopt import getopt as GetOpt, GetoptError

    def usage():
        baud = Baudrate()

        print ""
        print "Baudrate v%s" % baud.VERSION
        print "Craig Heffner, http://www.devttys0.com"
        print ""
        print "Usage: %s [OPTIONS]" % sys.argv[0]
        print ""
        print "\t-p <serial port>       Specify the serial port to use [/dev/ttyUSB0]"
        print "\t-t <seconds>           Set the timeout period used when switching baudrates in auto detect mode [%d]" % baud.READ_TIMEOUT
        print "\t-c <num>               Set the minimum ASCII character threshold used during auto detect mode [%d]" % baud.MIN_CHAR_COUNT
        print "\t-n <name>              Save the resulting serial configuration as <name> and automatically invoke minicom (implies -a)"
        print "\t-a                     Enable auto detect mode"
        print "\t-b                     Display supported baud rates and exit"
        print "\t-q                     Do not display data read from the serial port"
        print "\t-h                     Display help"
        print ""
        sys.exit(1)

    def main():
        display = False
        verbose = True
        auto = False
        run = False
        threshold = 25
        timeout = 5
        name = None
        port = '/dev/ttyUSB0'

        try:
            (opts, args) = GetOpt(sys.argv[1:], 'p:t:c:n:abqh')
        except GetoptError, e:
            print e
            usage()

        for opt, arg in opts:
            if opt == '-t':
                timeout = int(arg)
            elif opt == '-c':
                threshold = int(arg)
            elif opt == '-p':
                port = arg
            elif opt == '-n':
                name = arg
                auto = True
                run = True
            elif opt == '-a':
                auto = True
            elif opt == '-b':
                display = True
            elif opt == '-q':
                verbose = False
            else:
                usage()

        baud = Baudrate(port, threshold=threshold, timeout=timeout, name=name, verbose=verbose, auto=auto)

        if display:
            print ""
            for rate in baud.BAUDRATES:
                print "\t%s" % rate
            print ""
        else:
            print ""
            print "Starting baudrate detection on %s, turn on your serial device now." % port
            print "Press Ctl+C to quit."
            print ""

            baud.Open()

            try:
                rate = baud.Detect()
                print "\nDetected baudrate: %s" % rate

                if name is None:
                    print "\nSave minicom configuration as: ",
                    name = sys.stdin.readline().strip()
                    print ""

                (ok, config) = baud.MinicomConfig(name)
                if name and name is not None:
                    if ok:
                        if not run:
                            print "Configuration saved. Run minicom now [n/Y]? ",
                            yn = sys.stdin.readline().strip()
                            print ""
                            if yn == "" or yn.lower().startswith('y'):
                                run = True

                        if run:
                            subprocess.call(["minicom", name])
                    else:
                        print config
                else:
                    print config
            except KeyboardInterrupt:
                pass

            baud.Close()

    main()
