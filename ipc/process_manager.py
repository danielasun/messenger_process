import logging
import multiprocessing
import collections
from ipc.signals import MP_TRANSPORT

"""
ProcessReference:
    named tuple
        name: string
        proc: Process reference
        link_to_child: parent connection

"""
ProcessReference = collections.namedtuple('ProcessReference',
                                          'name \
                                           link_to_child\
                                           proc')

log = logging.getLogger(__name__)

class ProcessManager:
    """
    A process metaclass that lets you create new processes, automatically
    destroy them and monitor a parent connection. The ProcessManager can be
    context-managed using the with keyword. When going out of scope, the Process
    Manager will automatically send the MP_TRANSPORT.STOP enum to its children.

    Functions intended to be used as child processes should be set up so that
    one of their arguments is titled 'link_to_parent'. This is a
    multiprocessing Pipe that has the ability to send messages back to the
    parent process.

    Looping child processes should monitor ext_link for the enum
    MP_TRANSPORT.STOP. If received, make sure that your process terminates.
    Child procs have the responsibility to make sure that they terminate
    correctly!


    """
    def __init__(self, name, link_to_parent=None):
        """
        :param name: name of process, as string
        :param link_to_parent: if None, then this process is the master process
        otherwise, this connection can be polled for stop messages.
        """
        self.name = name
        self.ext_proc = {} # dictionary with process references, indexed by name.
        self.link_to_parent = link_to_parent
        self.msg = None

    def __enter__(self):
        return self

    def __exit__(self, type, value, traceback):
        self.close_all_processes()

    def add_process(self, name, f, daemon=False, *args, **kwargs):
        """
        Add managed process by name that executes function f. Set daemon to True
        to run process as a daemon (separate from Unix daemon) which means that
        it will not be able to create child processes.
        :param name: name of the external process (string)
        :param f: name of function to run
        :param daemon: True or False
        :param args: ordered arguments to pass to the function
        :param kwargs: keyword arguments to pass to the function
        :return:
        """
        link_to_child, link_to_parent = multiprocessing.Pipe()
        kwargs['link_to_parent']=link_to_parent
        proc = multiprocessing.Process(target=f,
                                       args=args,
                                       kwargs=kwargs,
                                       daemon=daemon)
        # create external process and pass it the pipe with keyword
        # "link_to_parent" along with other kwargs
        proc.start()

        if name in self.ext_proc:
            raise RuntimeError('Attempted to add multiples of the same '
                               'process: {}'.format(name))
        self.ext_proc[name] = ProcessReference(name=name,
                                               link_to_child=link_to_child,
                                               proc=proc)

    def close_process(self, name):
        """
        Close process by name and join them.
        :param name: name of process to close
        :return:
        """
        log.info('Closing process {}'.format(name))
        STOP_SIGNAL = MP_TRANSPORT.STOP
        proc_ref = self.ext_proc[name]
        proc = proc_ref.proc
        link_to_child = proc_ref.link_to_child
        link_to_child.send(STOP_SIGNAL)
        proc.join(1)
        log.info('proc {} exited with code {}'.format(
            name, proc.exitcode))
        try:
            del self.ext_proc[name]
        except KeyError:
            print('Key {} not found'.format(name))

    def close_all_processes(self):
        """
        Closes all processes using self.close_process()
        :return:
        """
        log.debug('Closing all processes in {}'.format(self.name))

        for k in self.ext_proc.copy(): # making copy to avoid runtime error
            log.info('Closing {}'.format(k))
            self.close_process(k)

    def poll(self, proc_name=None, timeout=0):
        """
        Non-blocking check link to parent or external process for messages.
        :return:
        """
        if proc_name is None:
            connection = self.link_to_parent
        else:
            connection = self.ext_proc[proc_name].link_to_child

        if connection.poll(timeout):
            return True
        else:
            return False

    def recv(self, proc_name=None):
        """
        Should only be called if ProcessManager.poll() returned True.
        Returns an object msg
        :return: msg
        """
        if proc_name is None:
            return self.link_to_parent.recv()
        else:
            return self.ext_proc[proc_name].link_to_child.recv()

    def send(self, proc_name=None, msg=None):
        """
        Send message to process. Defaults to parent process if proc_name is
        None, otherwise sends to child external process.
        :param proc_name:
        :return:
        """
        if msg is None:
            raise ValueError("Must send a message")

        if proc_name is None:
            if self.link_to_parent is None:
                raise ValueError("send() defaults to sending up to parent.")
            self.link_to_parent.send(msg)
        else:
            self.ext_proc[proc_name].link_to_child.send(msg)

    def _check_exit_condition(self):
        """
        Returns True if exit flag is given, otherwise returns False.
        Non-blocking call to poll. Saves last message to self.msg
        :return: True/False
        """

        if self.link_to_parent is None:
            raise ValueError("Can't check exit condition as master process")

        if self.poll():
            msg = self.recv()
            if self.msg_is_stop_signal(msg):
                log.debug('exiting proc {}'.format(self.name))
                return True
            else:
                log.debug(msg)
                self.msg = msg
        return False

    def process_should_continue(self):
        """
        Determine whether to continue a loop by reading from the parent process.
        :return: True to continue, False to exit
        """
        return not self._check_exit_condition()

    @staticmethod
    def msg_is_stop_signal(msg):
        """
        Check if received message indicates to terminate the current process.
        :param msg: needs to be of type MP_TRANSPORT
        :return:
        """
        if type(msg) == MP_TRANSPORT and msg == MP_TRANSPORT.STOP:
            return True
        else:
            return False

class ChildManager(ProcessManager):
    """
    Convenient wrapper for child processes that requires a link to the parent.
    """
    def __init__(self, name, link_to_parent):
        super().__init__(name=name, link_to_parent=link_to_parent)