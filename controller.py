import threading
import time

__author__ = 'chris'


class OutputLimit(object):
    def __init__(self, minimum, maximum):
        self._minimum = minimum
        self._maximum = maximum

    def clamp(self, value):
        if value < self._minimum:
            return self._minimum
        elif value > self._maximum:
            return self._maximum
        else:
            return value


class PIDParameter(object):
    def __init__(self, p, i, d):
        self.p = p
        self.i = i
        self.d = d


class PIDRegulator(object):
    def __init__(self, input_function, output_function, pid_parameters, input_function_kwargs=None,
                 output_function_kwargs=None, initial_target=0, invert=False, output_limit=None, period=1):
        self._input_function = input_function
        self._input_function_kwargs = input_function_kwargs

        self._output_function = output_function
        self._output_function_kwargs = output_function_kwargs

        self._output_limit = output_limit if output_limit else OutputLimit()

        self._parameters = pid_parameters
        self._invert = invert
        self._target = initial_target
        self._period = period

        self._integral = 0
        self._in_previous = None
        self._out_last = None

        # Thread management primitives
        self._lock = threading.RLock()
        self._stop = threading.Event()

        # Create and start the thread
        self._thread = threading.Thread(target=self._update)
        self._thread.daemon = True

    def __del__(self):
        self.stop()

    def start(self):
        self._thread.start()

    def stop(self, block=True):
        self._stop.set()

        if block:
            self._thread.join()

    def get_input(self):
        with self._lock:
            return self._input_function(**self._input_function_kwargs)

    def get_output(self):
        return self._out_last

    def set_output(self, value):
        self._out_last = value

        with self._lock:
            return self._output_function(value, **self._output_function_kwargs)

    def get_target(self):
        with self._lock:
            return self._target

    def get_error(self):
        with self._lock:
            return self._target - self.get_input()

    def set_target(self, target):
        with self._lock:
            self._target = target

    def _update(self):
        while not self._stop.is_set():
            # Read input
            with self._lock:
                # Get current input
                in_value = self.get_input()

                # Proportional
                in_error = in_value - self._target

                # Integral
                self._integral = self._output_limit.clamp(self._integral + self._parameters.i * in_error)

                # Differential
                in_differential = self._parameters.d * (in_value - self._in_previous)
                self._in_previous = in_value

                out_value = self._output_limit.clamp(self._parameters.p * in_error + self._integral + in_differential)

                # Write new output
                self.set_output(out_value)

            # Sleep until next update
            time.sleep(self._period)
