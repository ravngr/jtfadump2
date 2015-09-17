import logging
import random
import threading
import time
import util

__author__ = 'chris'


class CaptureException(Exception):
    pass


class Capture(object):
    def __init__(self, label, raw=False):
        self._label = label
        self._raw = raw

        self._log = logging.getLogger(type(self).__name__)
        self._log.debug("Created capture module {} ({})".format(type(self).__name__, self._label))

    def get_data(self, experiment_stack):
        # Check for state variables if raw capture is enabled
        if self._raw and not Capture._has_experiment_state(experiment_stack):
            self._log.warn('Raw capture enabled but experiment stack has no state variables. Raw capture has been'
                           ' disabled!')
            self._raw = False

        # Get state from child class
        data = self._get_data(experiment_stack)

        # Append label to keys in state
        return {self._label + '_' + k: v for k, v in data.items()}

    def _get_data(self, experiment_stack):
        raise NotImplementedError()

    @staticmethod
    def _has_experiment_state(experiment_stack):
        for e in experiment_stack:
            if e.get_primary_key_field():
                return True

        return False

    @staticmethod
    def _get_experiment_state_fields(experiment_stack):
        state = []

        # Get all active state primary variables
        for e in experiment_stack:
            field = e.get_primary_key_field()

            if field:
                state.append(field)

        return tuple(state)

    @staticmethod
    def _get_experiment_state_values(experiment_stack):
        state = []

        # Get all active state primary variables
        for e in experiment_stack:
            field = e.get_primary_key_field()

            if field:
                if type(field) is tuple:
                    state.append(e.get_state()[field[0]][field[1]])
                else:
                    state.append(e.get_state()[field])

        if len(state) is 0:
            raise CaptureException('Experiment stack has no experiment state variables for raw data')

        return tuple(state)


class FrequencyCounterCapture(Capture):
    def __init__(self, label, raw=False):
        super().__init__(label, raw)


class MKSSerialCapture(Capture):
    def __init__(self, label, raw=False):
        super().__init__(label, raw)


class NullCapture(Capture):
    def __init__(self, label, raw=False):
        super().__init__(label, raw)

    def _get_data(self, experiment_stack):
        return {}


class PulseCapture(Capture):
    def __init__(self, label, raw=False, channel=[1]):
        super().__init__(label, raw)

        self._channels = channel

    def _get_data(self, experiment_stack):
        return {
            'signal_time': [],
            'signal_channel': self._channels
        }


class RandomCapture(Capture):
    def __init__(self, label, raw=False, length=1):
        super().__init__(label, raw)

        self._length = length

    def _get_data(self, experiment_stack):
        if self._raw:
            keys = []
            values = []

            for _ in range(0, self._length):
                keys.append(Capture._get_experiment_state_values(experiment_stack))
                values.append(random.random())

            return {
                'raw_key_fields': Capture._get_experiment_state_fields(experiment_stack),
                'raw_key_values': keys,
                'raw_number': values,
                'number': sum(values) / float(len(values))
            }
        else:
            return {
                'number': [random.random() for _ in range(0, self._length)]
            }


class VNACapture(Capture):
    def __init__(self, label, raw=False):
        super().__init__(label, raw)


class ContinuousCaptureWrapper(Capture):
    def __init__(self, label, interval, wrapped_class, *args, **kwargs):
        super().__init__(label)

        self._interval = interval

        # Create child class
        self._wrapped_class = util.class_instance_from_dict(wrapped_class, __name__, *args, **kwargs)

        # Buffer for data from capture
        self._buffer = []
        self._buffer_lock = threading.RLock()

        self._stop = threading.Event()

        self._thread = threading.Thread(target=self._update)
        self._thread.daemon = True
        self._thread.start()

    def __del__(self):
        self._stop.set()
        self._thread.join()

    def _get_data(self, experiment_stack):
        with self._buffer_lock:
            out_buffer = self._buffer

            self._buffer = []

            return out_buffer

    def _update(self):
        while not self._stop.is_set():
            with self._buffer_lock:
                self._capture._get_data()

            time.sleep(self._interval)
