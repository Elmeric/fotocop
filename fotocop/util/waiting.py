"""A class providing a threaded spin cursor on the console.

From http://code.activestate.com/recipes/534142-spin-cursor/
"""
import threading
import sys
import time


class SpinCursor(threading.Thread):
    """A console spin cursor class.

    Example Usage:
        This will spin 5 times even if the data arrives early:
            spin = SpinCursor(minspin=5, msg="Waiting for data...")
            spin.start()
            if data_arrived():
                spin.join()

        This will spin only during the waiting time:
            spin = SpinCursor(msg="Waiting for data...")
            spin.start()
            if data_arrived():
                spin.stop()

        This will spin really fast:
            spin = SpinCursor(msg="I am really busy...", speed=50)
            spin.start()
    """

    def __init__(self, msg='', maxspin=0, minspin=10, speed=5):
        # Count of a spin
        self.count = 0
        self.out = sys.stdout
        self.flag = False
        self.max = maxspin
        self.min = minspin
        # Any message to print first ?
        self.msg = msg
        # Complete printed string
        self.string = ''
        # Speed is given as number of spins a second
        # Use it to calculate spin wait time
        self.waittime = 1.0 / float(speed * 4)
        self.spinchars = (u'-', u'\\ ', u'| ', u'/ ')
        threading.Thread.__init__(self, None, None, "Spin Thread")

    def spin(self):
        """ Perform a single spin """

        for x in self.spinchars:
            self.string = self.msg + "...\t" + x + "\r"
            self.out.write(self.string)
            self.out.flush()
            time.sleep(self.waittime)

    def run(self):

        while (not self.flag) and ((self.count < self.min) or (self.count < self.max)):
            self.spin()
            self.count += 1

        # Clean up display...
        self.out.write(" " * (len(self.string) + 1))

    def stop(self):
        self.flag = True


if __name__ == "__main__":
    spin = SpinCursor(msg="Spinning...", minspin=5, speed=5)
    spin.start()
