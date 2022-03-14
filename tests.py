import logging
import os
import time
import unittest

import matplotlib.pyplot as plt
import numpy as np

import ipc.message as message
import ipc.messenger_process as mp
import ipc.signals as sig
import ipc.signals as signals
from ipc.process_manager import ProcessManager, ChildManager
from ipc.signals import MP_TRANSPORT
from timing.timed_loop import TimedLoop, SynchronizedTimedLoop, get_timed_loop

log = logging.getLogger(__name__)
logging.basicConfig(level=logging.DEBUG)


def my_proc(link_to_parent, proc_name=''):
    logging.debug('entering {}'.format(proc_name))
    while True:
        link_to_parent.poll()  # not using process manager at lowest level
        if link_to_parent.poll():
            msg = link_to_parent.recv()
            if msg == MP_TRANSPORT.STOP:
                logging.debug(
                    'closing worker_proc {}'.format(os.getpid()))
                break
        logging.debug('.')
        time.sleep(0.005)


def worker_proc(link_to_parent, proc_name=''):
    # using process manager at worker level
    logging.debug('entering {}'.format(proc_name))
    with ProcessManager(proc_name, link_to_parent) as pm:
        while True:
            if pm.poll():
                msg = pm.recv()
                if pm.msg_is_stop_signal(msg):
                    logging.debug(
                        'closing worker_proc {}'.format(os.getpid()))
                    break
            logging.debug('.')
            time.sleep(0.005)


def mid_level_proc(link_to_parent, proc_name=''):
    logging.debug('entering {}'.format(proc_name))
    with ChildManager(proc_name, link_to_parent=link_to_parent) as cm:
        # child manager will automatically close external processes
        # when it goes out of scope
        cm.add_process("worker_proc1", worker_proc,
                       proc_name='worker_proc1', daemon=True)
        cm.add_process("worker_proc2", worker_proc,
                       proc_name='worker_proc2', daemon=True)
        while True:
            msg = None
            if cm.poll():
                msg = cm.recv()
                if cm.msg_is_stop_signal(msg):
                    logging.debug(
                        'closing worker_proc {}'.format(os.getpid()))
                    break
            logging.debug('.')
            time.sleep(0.005)


def boss_proc(link_to_parent, proc_name=''):
    logging.debug('entering {}'.format(proc_name))
    with ChildManager(proc_name, link_to_parent=link_to_parent) as cm:
        cm.add_process("mid_level_proc1/", mid_level_proc,
                       proc_name=proc_name + 'mid_level_proc1/')
        cm.add_process("mid_level_proc2/", mid_level_proc,
                       proc_name=proc_name + 'mid_level_proc2/')
        while True:
            if cm.poll():
                msg = cm.recv()
                if cm.msg_is_stop_signal(msg):
                    logging.debug(
                        'closing boss_proc {}'.format(
                            os.getpid()))
                    break
            logging.debug('.')
            time.sleep(0.005)


def msg_proc(link_to_parent, proc_name=''):
    logging.debug('entering {}'.format(proc_name))
    with ChildManager(proc_name, link_to_parent=link_to_parent) as cm:
        while cm.process_should_continue():
            if cm.msg is not None:
                cm.send(msg='gday mate')
                cm.msg = None
            time.sleep(0.005)


def heartbeat_proc(link_to_parent, proc_name=''):
    """
    Responds to heartbeat signal (MP_TRANSPORT.HEARTBEAT) with its own
    heartbeat signal.
    :param link_to_parent:
    :param proc_name:
    :return:
    """

    logging.debug('entering {}'.format(proc_name))
    with ChildManager(proc_name, link_to_parent=link_to_parent) as cm:
        while True:
            msg = None
            if cm.poll():
                msg = cm.recv()
                if cm.msg_is_stop_signal(msg):
                    break
                else:
                    logging.debug("{} : {}".format(proc_name, msg))
                if msg == MP_TRANSPORT.HEARTBEAT:
                    cm.send(msg=MP_TRANSPORT.HEARTBEAT)
            time.sleep(0.005)


def check_msg_proc(link_to_parent, proc_name=''):
    logging.debug('entering {}'.format(proc_name))
    with ChildManager(proc_name, link_to_parent=link_to_parent) as cm:
        while cm.process_should_continue():
            logging.debug('continuing child proc')
            time.sleep(0.005)


def long_proc(link_to_parent, proc_name=''):
    logging.debug('entering {}'.format(proc_name))
    with ChildManager(proc_name, link_to_parent=link_to_parent) as cm:
        time.sleep(1)
        cm.send(msg='timeout')


def process_fn(link_to_parent):
    """
    Minimal loop fn
    :param link_to_parent:
    :return:
    """
    m = mp.MessengerProcess('child', link_to_parent)

    def fn(val, **kwargs):
        return val

    signal = sig.MESSENGER_SIGNAL.A
    m.add_signal(signal, fn)
    while not m.should_stop_loop():
        m.handle_messages()


class TestMessage(unittest.TestCase):
    def test_create_message(self):
        msg = message.create_message(signals.MESSENGER_SIGNAL.A, sys=5)
        self.assertTrue(msg.type == signals.MESSENGER_SIGNAL.A)
        self.assertTrue(msg['sys'] == 5)


class TestProcessManager(unittest.TestCase):
    def test_single_level(self):  # single level of tests, not using Process
        with ProcessManager('p_man') as p:
            p.add_process("my_proc1", my_proc, proc_name='my_proc1')
            p.add_process("my_proc2", my_proc, proc_name='my_proc2')
            time.sleep(.1)

    def test_multi_level(self):  # test multiple levels of child processes
        with ProcessManager('p_man') as p:
            p.add_process('mid_level_proc', mid_level_proc,
                          proc_name='mid_level_proc')
            time.sleep(.1)

    def test_three_level(self):  # three levels of processes
        with ProcessManager('p_man') as p:
            p.add_process('boss_proc', boss_proc, proc_name='boss_proc/')
            time.sleep(.1)

    def test_message_queue(self):  # testing message sending protocol
        # send 4 messages, check that child process returns them.
        with ProcessManager('p_man') as p:
            p.add_process("msg_proc1", msg_proc, proc_name='msg_proc1')
            time.sleep(0.1)
            for i in range(4):
                p.ext_proc['msg_proc1'].link_to_child.send('hi it\'s your boss')
            for i in range(4):
                if p.poll('msg_proc1'):
                    reply = p.recv('msg_proc1')
                    self.assertTrue(reply == 'gday mate')
                time.sleep(.1)

    def test_message_queue_speed1(self):  # testing message sending protocol
        import numpy as np
        def my_proc(link_to_parent, proc_name=''):
            logging.debug('entering {}'.format(proc_name))
            with ChildManager(proc_name, link_to_parent=link_to_parent) as cm:
                i = 0
                while True:
                    i += 1
                    msg = None
                    if cm.poll():
                        msg = cm.recv()
                        if cm.msg_is_stop_signal(msg):
                            break
                        else:
                            if i % 100 == 0:
                                print()
                                print("{}:".format(i), end='')
                            print('.', end='')

        with ProcessManager('p_man') as p:
            p.add_process("my_proc1", my_proc, proc_name='my_proc1')
            a = np.random.random((100, 100))
            time.sleep(.5)
            start_time = time.time()
            nmessages = 10000
            for i in range(nmessages):
                p.send('my_proc1', a)
        elapsed_time = time.time() - start_time
        logging.info("Elapsed time: {} for {} messages. ({}s per "
                     "message)".format(
            elapsed_time, nmessages, elapsed_time / nmessages))

    def test_message_queue_speed2(self):
        # testing message sending protocol with timing of 1 ms
        import numpy as np
        def my_proc(link_to_parent, proc_name=''):
            @TimedLoop(dt=0.001)
            def worker_loop_fn():
                pass

            logging.debug('entering {}'.format(proc_name))
            with ChildManager(proc_name, link_to_parent=link_to_parent) as cm:
                i = 0
                while True:
                    i += 1
                    msg = None
                    if cm.poll():
                        msg = cm.recv()
                        if cm.msg_is_stop_signal(msg):
                            break
                        else:
                            if i % 100 == 0:
                                print()
                                print("{}:".format(i), end='')
                            print('.', end='')
                    worker_loop_fn()

        @TimedLoop(dt=0.001)
        def boss_loop_fn():
            pass

        with ProcessManager('p_man') as p:
            p.add_process("my_proc1", my_proc, proc_name='my_proc1')
            a = np.random.random((100, 100))
            time.sleep(.01)
            start_time = time.time()
            nmessages = 500
            for i in range(nmessages):
                p.send('my_proc1', a)
                boss_loop_fn()
        elapsed_time = time.time() - start_time
        print("Elapsed time: {} for {} messages. ({}s per message)".format(
            elapsed_time, nmessages, elapsed_time / nmessages))

    def test_daemon_auto_destroy(self):
        def faulty_mid_level_proc(link_to_parent, proc_name=''):
            logging.debug('entering {}'.format(proc_name))
            cm = ChildManager(name=proc_name, link_to_parent=link_to_parent)
            # child manager will automatically close external processes
            # when it goes out of scope
            cm.add_process("worker_proc1", worker_proc,
                           proc_name='worker_proc1', daemon=True)
            cm.add_process("worker_proc2", worker_proc,
                           proc_name='worker_proc2', daemon=True)

        p = ProcessManager('p_man')
        proc_name = 'mid_level_proc'
        p.add_process(proc_name, faulty_mid_level_proc,
                      proc_name='mid_level_proc', daemon=False)
        time.sleep(.3)

    def test_arg_keyword(self):
        """
        Test sending arbitrary number of arguments and keyword arguments.
        Increase variable "sleep_amt" to see the order that things get
        printed out.

        :return:
        """

        def arg_func(arg1, arg2, kwarg1='hey', kwarg2='there',
                     link_to_parent=None,
                     name='arg_func',
                     **kwargs):
            with ChildManager(link_to_parent=link_to_parent, name=name) as cm:
                print(arg1, arg2, kwarg1, kwarg2)
                while True:
                    if cm.poll():
                        msg = cm.recv()
                        print(msg)
                        if cm.msg_is_stop_signal(msg):
                            break

            print(arg1, arg2, kwarg1, kwarg2)

        sleep_amt = 0.01  # increase this to see in real time
        with ProcessManager('p_man') as p:
            proc_name = 'proc'
            p.add_process(proc_name, arg_func, False, 1, 2,
                          kwarg1='whats', kwarg2='up')
            time.sleep(sleep_amt)
            for i in range(5):
                p.send(proc_name, 'awake?')
                time.sleep(sleep_amt)

            proc_name = 'proc2'
            p.add_process(proc_name, arg_func, False, 3, 4)
            time.sleep(sleep_amt)
            for i in range(5):
                p.send(proc_name, 'awake?')
                time.sleep(sleep_amt)

    def test_poll_by_name(self):
        """
        Parent polls processes by name, children respond with heartbeat signal.
        :return:
        """

        sleep_amt = 0.01

        with ProcessManager('p_man') as p:
            for i in range(3):
                proc_name = 'proc' + str(i)
                p.add_process(proc_name, heartbeat_proc, proc_name=proc_name)
            time.sleep(0.1)
            for _ in range(10):

                for k in p.ext_proc:
                    proc_name = p.ext_proc[k].name
                    p.send(proc_name, MP_TRANSPORT.HEARTBEAT)

                for i in range(3):
                    proc_name = 'proc' + str(i)
                    if p.poll(proc_name):
                        msg = p.recv(proc_name)
                        print("{}: {}".format(proc_name, msg))

                time.sleep(sleep_amt)

    def test_process_should_continue(self):
        """
        Check that external process exits
        :return:
        """
        with ProcessManager('master') as pm:
            pm.add_process('child_proc', check_msg_proc)

            self.assertRaises(ValueError, pm._check_exit_condition)
            for i in range(10):
                time.sleep(.01)

    def test_timeout(self):
        with ProcessManager('master') as pm:
            pm.add_process('child', long_proc)

            # immediate timeout
            start_time = time.time()
            if pm.poll(proc_name='child'):
                print(pm.recv('child'))
            final_time = time.time() - start_time
            print(final_time)
            self.assertTrue(final_time < .05)

            # .25 s timeout
            start_time = time.time()
            if pm.poll(proc_name='child', timeout=.25):
                print(pm.recv('child'))
            final_time = time.time() - start_time
            print(final_time)
            self.assertTrue(final_time > .25)

            # infinite timeout
            start_time = time.time()
            if pm.poll(proc_name='child', timeout=None):
                print(pm.recv('child'))
            final_time = time.time() - start_time
            print(final_time)
            self.assertTrue(final_time > .75)

            pm.close_process('child')

    def test_exc_when_adding_duplicate_process_names(self):
        """
        Can't add multiples of the same process name
        Can't add multiples of the same process name
        :return:
        """
        with self.assertRaises(RuntimeError):
            with ProcessManager('master') as pm:
                pm.add_process('child', long_proc)
                pm.add_process('child', long_proc)


class TestMessengerProcess(unittest.TestCase):
    def test_map_signal_to_function(self):
        m = mp.MessengerProcess('master')

        def fn(val, **kwargs):
            return val

        signal = sig.MESSENGER_SIGNAL.A
        m.add_signal(signal, fn)
        msg = {'type': sig.MESSENGER_SIGNAL.A,
               'val': 5}
        out = m.process_message(msg)
        self.assertTrue(out == 5)

    def test_handle_messages(self):
        """
        Handle messages and program should terminate after 1 second
        :return:
        """
        m = mp.MessengerProcess('father')
        m.add_process('child', process_fn)

        with m:
            for i in range(10):
                time.sleep(.1)

    def test_create_process_fn(self):
        m = mp.MessengerProcess('father')
        process_fn = mp.create_process_fn(mp.MessengerProcess, 'kid',
                                          control_loop_period=0.005)

        m.add_process('child', process_fn)

        with m:
            for i in range(10):
                msg = {'type': sig.MP_TRANSPORT.HEARTBEAT}
                m.send('child', msg)

    def test_send_message(self):
        m = mp.MessengerProcess('father')
        process_fn = mp.create_process_fn(mp.MessengerProcess, 'kid',
                                          control_loop_period=0.005)
        m.add_process('child', process_fn)

        with m:
            for i in range(10):
                msg = message.create_message(type=sig.MP_TRANSPORT.HEARTBEAT)
                m.send('child', msg)


""" test_timed_loop.py
Tests for the TimedLoop class in pebl.decorator
"""

TL = TimedLoop(dt=.02)

start_time = time.time()


@TL
def funcA():
    print("funcA ran: ", end='')


@TL
def funcB():
    print("funcB ran: ", end='')
    time.sleep(.03)


@TL
def funcC():
    print("funcC ran: ", end='')


@TL
def empty_loop():
    pass


class TestTimedLoop(unittest.TestCase):
    def test_catch_up(self):
        print("# === test_catch_up === #")
        print(
            """
            # expected output:
            funcA ran: .02
            funcB ran: .03
            funcC ran: .01
            """)

        print("# actual output:")
        start_time = time.time()
        funcA()
        time_diff = time.time() - start_time
        print("{:.2f}".format(time_diff))
        self.assertAlmostEqual(time_diff, .02, 2)

        start_time = time.time()
        funcB()
        time_diff = time.time() - start_time
        print("{:.2f}".format(time_diff))
        self.assertAlmostEqual(time_diff, .03, 2)

        start_time = time.time()
        funcC()
        time_diff = time.time() - start_time
        print("{:.2f}".format(time_diff))
        self.assertAlmostEqual(time_diff, .01, 2)

    def test_change_dt(self):
        print("# === test_change_dt === #")
        print("""# expected output:
    funcA ran: .025
    funcB ran: .030
    funcC ran: .020\n""")

        TL.change_dt(.025)

        print("# actual output:")
        start_time = time.time()
        funcA()
        time_diff = time.time() - start_time
        print("{:.3f}".format(time_diff))
        self.assertAlmostEqual(time_diff, .025, 2)

        start_time = time.time()
        funcB()
        time_diff = time.time() - start_time
        print("{:.3f}".format(time_diff))
        self.assertAlmostEqual(time_diff, .03, 2)

        start_time = time.time()
        funcC()
        time_diff = time.time() - start_time
        print("{:.3f}".format(time_diff))
        self.assertAlmostEqual(time_diff, .02, 2)

        TL.change_dt(.02)

    def test_reset_start_time(self):
        print("# === test_reset_start_time === #")
        print("""# expected output:
    funcA ran: .020
    funcB ran: .030
    funcC ran: .010\n""")

        TL.reset_start_time()

        print("# actual output:")
        start_time = time.time()
        funcA()
        time_diff = time.time() - start_time
        print("{:.3f}".format(time_diff))
        self.assertAlmostEqual(time_diff, .02, 2)

        start_time = time.time()
        funcB()
        time_diff = time.time() - start_time
        print("{:.3f}".format(time_diff))
        self.assertAlmostEqual(time_diff, .03, 2)

        start_time = time.time()
        funcC()
        time_diff = time.time() - start_time
        print("{:.3f}".format(time_diff))
        self.assertAlmostEqual(time_diff, .01, 2)

    def test_empty_loop(self):
        print("# === test_empty_loop === #")
        print("""
# expected output:
.020
.040
.060
            """)

        print("# actual output:")
        empty_loop()
        start_time = time.time()
        time.sleep(.01)
        empty_loop()
        time_diff = time.time() - start_time
        print("{:.3f}".format(time_diff))
        self.assertAlmostEqual(time_diff, .02, 2)

        time.sleep(.01)
        empty_loop()
        time_diff = time.time() - start_time
        print("{:.3f}".format(time_diff))
        self.assertAlmostEqual(time_diff, .04, 2)

        time.sleep(.01)
        empty_loop()
        time_diff = time.time() - start_time
        print("{:.3f}".format(time_diff))
        self.assertAlmostEqual(time_diff, .06, 2)

    def test_jitter(self):

        import gc

        gc.disable()
        sleep_fn, tl = get_timed_loop(control_loop_period=0.005,
                                      synchronize=False)

        ntimes = 1000
        dt_list = []
        for i in range(ntimes):
            print('i')
            dt_list.append(time.perf_counter())
            sleep_fn()

        dt_arr = np.diff(np.array(dt_list))

        plt.plot(dt_arr)
        plt.xlabel('iteration')
        plt.ylabel('t [s]')
        plt.title('Loop period jitter, N = {}'.format(ntimes))
        plt.show()

        print(np.std(dt_arr))

    def test_jitter_busy_loop(self):
        import numpy as np
        import matplotlib.pyplot as plt

        ntimes = 1000
        dt = 0.005

        dt_list = []
        start_time = time.time()
        for i in range(ntimes):
            while time.time() - start_time < i * dt:
                # print('pass' + str(time.time()))
                continue
            dt_list.append(time.time())
        dt_arr = np.diff(np.array(dt_list))

        plt.plot(dt_arr)
        plt.xlabel('iteration')
        plt.ylabel('t [s]')
        plt.title('Loop period jitter, N = {}'.format(ntimes))
        plt.show()

        print(np.std(dt_arr))

    def test_jitter_uncompensated(self):
        import numpy as np
        import matplotlib.pyplot as plt

        ntimes = 1000
        dt = 0.005

        dt_list = []
        prev_time = time.time()
        for i in range(ntimes):
            while time.time() - prev_time < dt:
                print('pass' + str(time.time()))
                continue
            curr_time = time.time()
            prev_time = curr_time
            dt_list.append(curr_time)
        dt_arr = np.diff(np.array(dt_list))

        plt.plot(dt_arr)
        plt.xlabel('iteration')
        plt.ylabel('t [s]')
        plt.title('Loop period jitter, N = {}'.format(ntimes))
        plt.show()

        print(np.std(dt_arr))


class TestTimedLoopMutable(unittest.TestCase):
    def test_change_dt(self):
        # print out the time that each loop takes, show that each one is the
        # desired rate more or less
        # is the desired

        start_time = time.time()

        def lookup_fn():
            if time.time() - start_time <= 2:
                desired_dt = .05
            elif time.time() - start_time <= 4:
                desired_dt = .1
            elif time.time() - start_time <= 6:
                desired_dt = .2
            else:
                desired_dt = .3
            return desired_dt

        # create a timed loop function
        TL = SynchronizedTimedLoop(dt=0.05, iterations_per_update=10, timestep_lookup_fn=lookup_fn)
        # have it slowly increase its dt by looking up values in a for loop
        TL.synchronize()

        @TL
        def loop_fn():
            pass

        # iterate 10 and check
        prev_time = start_time
        for i in range(10):
            loop_fn()
            time_diff = time.time() - prev_time
            prev_time = time.time()
            print("time: = {} | dt = {}".format(time.time(), time_diff))
        self.assertAlmostEqual(time_diff, lookup_fn(), 2)

        # iterate 40 more and check again, the desired timestep should have changed
        prev_time = start_time
        for i in range(40):
            loop_fn()
            time_diff = time.time() - prev_time
            prev_time = time.time()
            print("time: = {} | dt = {}".format(time.time(), time_diff))
        self.assertAlmostEqual(time_diff, lookup_fn(), 2)


if __name__ == '__main__':
    unittest.main()