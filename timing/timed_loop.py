import time
import logging

import ipc.enums
# from pebl.robots.pebl import memory as mem # NOTE disabled because this relies on a closed source library

log = logging.getLogger(__name__)

class TimedLoop(object):
    """
    Decorator class to run a function repeatedly with some specified period.

    Use:
    - write a function which is meant to be called on a loop.
    - decorate the function with this class, specifying dt
    - call the function in a while or for loop

    Example:
    # This program will print 'loop_func ran' every .75 seconds

    @TimedLoop(dt=.75)
    def loop_func():
        print('loop_func ran')

    while True:
        loop_func()

    This decorator uses an internal counter in order to properly maintain the
    timing, i.e. slow down if ahead and try to catch up if behind. In order to
    maintain a proper counter while running multiple looping functions, the
    same TimedLoop object must be applied to all functions.

    Example:
    # This program will print 'funcA ran', 'funcB ran', 'funcC ran' with .75
    # second intervals in between.

    TL = TimedLoop(dt=.75)
    @TL2
    def funcA():
        print("funcA ran")
    @TL
    def funcB():
        print("funcB ran")
    @TL
    def funcC():
        print("funcC ran")
    while True:
        funcA()
        funcB()
        funcC()
    """

    def __init__(self, dt):
        self.i = 0
        self.dt = dt
        self.init_time = None

    def __call__(self, loop_func, *args, **kwargs):

        def wrapper(*args, **kwargs):

            # increment call count
            self.i += 1

            try:
                # calculate start time and desired end time
                des_end_time = self.i * self.dt + self.init_time
            except TypeError:  # raised if init_time has not been initialized
                self.init_time = time.perf_counter()
                des_end_time = self.i * self.dt + self.init_time

            # call function
            res = loop_func(*args, **kwargs)

            # sleep until desired end time or just continue
            current_time = time.perf_counter()
            # if des_end_time < current_time:
                # log.warning(f'Exceeded alloted loop iteration time: {des_end_time - current_time}')
            time.sleep(max(des_end_time - current_time, 0))

            # return result
            return res

        return wrapper

    def change_dt(self, new_dt):
        """
        Change dt for Timed Loop to hit between each sucessive call to its
        wrapped function
        :param new_dt:
        :return:
        """
        self.i = 0
        self.dt = new_dt
        self.init_time = None

    def reset_start_time(self):
        """
        reset start time
        :return:
        """
        self.i = 0
        self.init_time = None


class SynchronizedTimedLoop(TimedLoop):
    def __init__(self, dt, iterations_per_update, timestep_lookup_fn):
        """
        Extends the TimedLoop functionality to let you also dynamically change the
        dt of the TimedLoop based on an external 'real-time factor'.

        :param dt: timestep
        :param iterations_per_update: number of iterations before checking
        update function
        :param timestep_lookup_fn: a function to call to lookup the real-time
        factor
        :param lookup_args: if additional arguments are needed for using the lookup function
        """
        super().__init__(dt)
        self.iterations_per_update = iterations_per_update
        self.timestep_lookup_fn = timestep_lookup_fn

    def __call__(self, loop_func, *args, **kwargs):

        def wrapper(*args, **kwargs):

            # increment call count
            self.i += 1

            try:
                # calculate start time and desired end time
                des_end_time = self.i * self.dt + self.init_time
            except TypeError:  # raised if init_time has not been initialized
                self.init_time = time.perf_counter()
                des_end_time = self.i * self.dt + self.init_time

            # call function
            res = loop_func(*args, **kwargs)

            # sleep until desired end time or just continue
            current_time = time.perf_counter()
            # if current_time > des_end_time:
                # print(f'Exceeded alloted loop iteration time: {des_end_time - current_time}')
            try:
                time.sleep(max(des_end_time - current_time, 0))
            except OverflowError:
                print("OVERFLOW: {}".format(max(des_end_time - current_time,
                                                0)))
                print(des_end_time, current_time)

            if self.i >= self.iterations_per_update:
                self.synchronize()

            # return result
            return res

        return wrapper

    def synchronize(self):
        """
        Use given lookup function to synchronize
        :return:
        """
        desired_dt = self.timestep_lookup_fn()
        self.change_dt(desired_dt)


def get_timestep_lookup_function_by_player(control_loop_period, player):
    """
    Create customized timestep lookup function for a Synchronized TimedLoop
    based on the player provided.
    :param control_loop_period: duration of cycle of the timed loop. [s]
    :param player: either settings.PLAYER.VREP or settings.PLAYER.DXL
    :return: a customized function that takes no arguments and returns a
    desired_dt based on the scaling from the real_time_factor
    """
    if player == ipc.enums.PLAYER.DXL or ipc.enums.PLAYER.BULLET:
        memoryloc = mem.DATA_CLOCK
    elif player == ipc.enums.PLAYER.VREP:
        memoryloc = mem.DATA_VREP
    else:
        raise ValueError(
            "Non-recognized player enum specified for player device. "
            "It should be either settings.PLAYER.DXL or settings.PLAYER.VREP.")
    timestep_fn = _get_timestep_lookup_function(control_loop_period,
                                                memoryloc,
                                                rtf_key='real_time_factor')
    return timestep_fn



def get_synchronized_timed_loop(control_loop_period,
                                player,
                                iterations_per_update=100,):
    """
    Creates an instance of SynchronizedTimedLoop. Returns the timed loop
    instance and an empty sleep function that can be used to make execution
    halt until the next time interval.

    :param control_loop_period: duration of cycle of the timed loop. [s]
    :param player: either settings.PLAYER.VREP or settings.PLAYER.DXL
    :param iterations_per_update: number of iterations before syncing
    :return: sleep_fn, SynchronizedTimedLoop instance
    """

    lookup_fn = get_timestep_lookup_function_by_player(
        control_loop_period=control_loop_period,
        player=player
    )

    stl = SynchronizedTimedLoop(control_loop_period,
                                iterations_per_update=iterations_per_update,
                                timestep_lookup_fn=lookup_fn
                                )
    @stl
    def sleep_fn():
        pass

    return sleep_fn, stl

def get_timed_loop(control_loop_period,
                   synchronize,
                   player=None,
                   iterations_per_update=100):
    """
    Function to create timed loop functions and have the option to synchronize
    with an external clock.
    :param control_loop_period:  duration of cycle of the timed loop. [s]
    :param synchronize: whether to slow down the timed loop to match the
    speed of the player (usually used for simulations)
    :param player: either settings.PLAYER.VREP or settings.PLAYER.DXL
    :param iterations_per_update: number of iterations before syncing
    :return:
    """
    if synchronize:
        return get_synchronized_timed_loop(
            control_loop_period=control_loop_period,
            player=player,
            iterations_per_update=iterations_per_update
        )
    else:
        logging.debug('un-timed loop')
        tl = TimedLoop(dt=control_loop_period)
        @tl
        def sleep_fn():
            pass
        return sleep_fn, tl


def _get_timestep_lookup_function(control_loop_period, memory_loc, rtf_key):
    """
    Creates a customized timestep lookup function for a SynchronizedTimedLoop
    :param control_loop_period: duration in [s] of each timed loop
    :param memory_loc: location in shared memory to get() data from
    :param rtf_key: key for dictionary to plug into memory location
    :return: a customized function that takes no arguments and returns a
    desired_dt based on the scaling from the real_time_factor
    """
    def timestep_lookup_function():
        data = memory_loc.get()
        real_time_factor = data[rtf_key][0]
        desired_dt = control_loop_period / real_time_factor
        return desired_dt
    return timestep_lookup_function