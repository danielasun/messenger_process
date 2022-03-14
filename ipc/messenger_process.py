import logging
import os

from ipc import signals
from ipc.process_manager import ProcessManager
from timing.timed_loop import get_timed_loop

log = logging.getLogger(__name__)

def create_process_fn(msg_proc_class,
                      proc_name=None,
                      control_loop_period=None,
                      synchronize=False,
                      player=None):
    """
    Create process fn, optionally synchronized with a timed loop
    :param msg_proc_class:
    :param proc_name:
    :param control_loop_period:
    :param synchronize:
    :return:

    NOTE: the synchronize functionality is disabled because the shared memory library is closed source.
    """

    if proc_name is None:
        proc_name = msg_proc_class.__name__ + 'daemon'

    if control_loop_period is not None:
        sleep_fn, _ = get_timed_loop(control_loop_period=control_loop_period,
                                     synchronize=synchronize,
                                     player=player)
    else:
        sleep_fn = pass_fn

    def process_fn(link_to_parent, **kwargs):
        log.debug(proc_name)
        log.debug(msg_proc_class)
        m = msg_proc_class(name=proc_name,
                           link_to_parent=link_to_parent,
                           **kwargs)
        proc_loop(m, sleep_fn)

    return process_fn


def proc_loop(m, sleep_fn=None):
    """
    Loop function that exits when m.should_stop == True
    :param m: instance of MessengerProcess
    :param sleep_fn: function to call to sleep at regular intervals
    :return:
    """
    with m:
        m.setup()
        while True:
            m.handle_messages()
            if m.should_stop_loop():
                break
            else:
                m.loop_routine()
            if sleep_fn is not None:
                sleep_fn()
        m.teardown()
    log.debug('{} is exiting'.format(m.name))


def pass_fn(*args, **kwargs):
    """
    Does nothing
    :param args:
    :param kwargs:
    :return:
    """
    pass


class MessengerProcess(ProcessManager):
    """
    Handle system signals transmitted using a process manager. As long as the
    function is capable of handling arbitrary arguments, they will be
    automatically splatted into the function.

    The ability to add arbitrary callbacks linked to receiving a particular
    signal is what differentiates MessengerProcesses from ProcessManagers.

    To add a signal, use the add_signal method of MessengerProcess. by
    default, all MessengerProcesses will respond to the heartbeat signal
    TODO: add ping signal as well

    TODO: update the other loop functions to use MessengerProcess
    """

    def __init__(self, name, link_to_parent=None):
        super().__init__(name, link_to_parent=link_to_parent)
        # dictionary mapping signals to
        # functions
        self.recognized_signals = {}
        self.add_signal(signals.MP_TRANSPORT.HEARTBEAT, self.heartbeat)
        self.should_stop = False

    def handle_messages(self, proc_name=None) -> bool:
        """
        Repeatedly read and respond to messages unless receiving the stop
        signal.
        :param proc_name: name of process to respond to. If left blank, default
        is to check for messages from the parent process.
        :return: whether a message was received
        """
        if self.there_is_a_new_message(proc_name=proc_name):
            msg = self.recv(proc_name=proc_name)
            if self.msg_is_stop_signal(msg):
                self.should_stop = True
            else:
                self.process_message(msg)
            return True
        return False

    def process_message(self, msg):
        """
        Processes message. Every messenger_process has a number of
        recognized signals. The keys of the incoming msg are splatted out into
        keyword arguments.
        :param msg:
        :return:
        """
        if msg['type'] in self.recognized_signals:
            # print(msg['type'])
            # print(msg)
            fn = self.recognized_signals[msg['type']]
            return fn(**msg)
        else:
            log.info('received msg {}'.format(msg))
            raise (AttributeError(
                '{} is an unrecognized signal'.format(msg['type']))
            )

    def add_signal(self, signal, fn):
        self.recognized_signals[signal] = fn

    # TODO: there needs to be the ability to remove a signal

    def there_is_a_new_message(self, proc_name=None, timeout=0):
        """
        poll, optionally with a timeout. If timeout not specified, the poll
        is not blocking and returns immediately. Setting timeout to None will
        make the timeout infinite.
        :param timeout:
        :return: True/False
        """

        res = self.poll(proc_name, timeout=timeout)

        return res

    def heartbeat(self, *args, **kwargs):
        log.info("HEARTBEAT: {} {}".format(self.name, os.getpid()))

    def setup(self, **kwargs):
        """
        called once at the beginning of the proc fn. Meant to be overwritten by
        subclasses.
        :return:
        """
        pass

    def loop_routine(self):
        """
        Loop routine is automatically called on MessengerProcess during its
        loop function. Implement loop_routine in a subclass to use your own
        custom code that will run every iteration of the loop.
        :return:
        """
        pass

    def teardown(self, **kwargs):
        """
        called once when the proc fn is ending. Meant to be overwritten by
        subclasses.
        :param kwargs:
        :return:
        """
        pass

    def should_stop_loop(self):
        """
        Check if loop should stop
        :return:
        """
        # log.debug('checking should stop loop: {}'.format(self.should_stop))
        return self.should_stop

    def get_messages(self, proc_name=None):
        if self.there_is_a_new_message(proc_name=proc_name):
            msg = self.recv(proc_name=proc_name)
        else:
            msg = None
        return msg

