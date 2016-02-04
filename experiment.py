# -- coding: utf-8 --

import code
import datetime
import logging
import time

__author__ = 'chris'


class ExperimentException(Exception):
    pass


class ExperimentConfigurationException(Exception):
    pass


class Experiment(object):
    def __init__(self, label, primary=True):
        self._label = label
        self._primary = primary

        self._log = logging.getLogger(type(self).__name__)
        self._log.debug("Created Experiment module {} ({} primary key)".format(self._label,
                                                                               '✓' if self._primary else '✗'))

    def step(self):
        raise NotImplementedError()

    def reset(self):
        raise NotImplementedError()

    def stop(self):
        pass

    def has_next(self):
        raise NotImplementedError()

    def get_resume_state(self):
        raise NotImplementedError()

    def set_resume_state(self, state):
        raise NotImplementedError()

    def get_state(self):
        # Get state from child class
        state = self._get_state()

        # Append label to keys in state
        return {self._label + '_' + k: v for k, v in state.items()}

    def _get_state(self):
        raise NotImplementedError()

    def get_primary_key_field(self):
        primary_key = self._primary_key_field()

        if primary_key is None:
            return None

        if type(primary_key) is tuple:
            if len(primary_key) is 1:
                primary_key = primary_key[0]
            elif len(primary_key) is 2:
                primary_key = "{}[{}]".format(str(primary_key[0]), str(primary_key[1]))
            else:
                raise ExperimentConfigurationException('Experiment primary key tuple must be 1 or 2 elements long')

        if type(primary_key) in [tuple, list]:
            if len(primary_key) > 1:
                return self._label + '_' + primary_key if self._primary else None
            else:
                primary_key = primary_key[0]

        return self._label + '_' + primary_key if self._primary else None

    def _primary_key_field(self):
        raise NotImplementedError()


class _SteppedExperiment(Experiment):
    def __init__(self, label, step_values, primary=True):
        super().__init__(label, primary)

        self._step_values = step_values

        self._current_step = 0
        self._next_step = 0

    def step(self):
        if self._next_step > self._step_maximum():
            raise ExperimentException()

        self._current_step = self._next_step
        self._next_step += 1

        self._log.info("Step {} of {}".format(self._current_step + 1, self._step_maximum()))

    def reset(self):
        self._current_step = 0
        self._next_step = 0

        self._log.info('Steps reset')

    def has_next(self):
        return self._next_step < self._step_maximum()

    def get_resume_state(self):
        return self._current_step, self._next_step,

    def set_resume_state(self, state):
        self._current_step, self._next_step = state

    def _get_state(self):
        return {
            'step': self._get_step()
        }

    def _primary_key_field(self):
        raise NotImplementedError()

    def _step_maximum(self):
        if type(self._step_values) is list:
            return len(self._step_values)
        else:
            return 1

    def _get_step(self):
        return self._current_step

    def _get_step_value(self):
        return self._step_values[self._current_step]


class RepeatExperiment(Experiment):
    def __init__(self, label, maximum, primary=True):
        super().__init__(label, primary)

        self._count = 0
        self._maximum = maximum

    def step(self):
        self._count += 1

    def reset(self):
        self._count = 0

    def has_next(self):
        return self._count < self._maximum

    def get_resume_state(self):
        return self._count, self._maximum

    def set_resume_state(self, state):
        self._count, self._maximum = state


class FlowExperiment(_SteppedExperiment):
    def __init__(self, label, mfc_connector, mfc_flow_rate, primary=True):
        super().__init__(label, mfc_flow_rate, primary)

        self._channels = len(mfc_flow_rate[0])

        self._log.info("Setup {} channel mass flow controller".format(self._channels))

    def reset(self):
        super().reset()

    def step(self):
        super().step()

        flow_rate = self._get_step_value()

        self._log.info("Flow rate: {} sccm".format(' sccm, '.join([str(x) for x in flow_rate])))

    def stop(self):
        # TODO Shutdown
        pass

    def set_resume_state(self, state):
        super().set_resume_state(state)

        # TODO Update controllers

    def _get_state(self):
        # TODO Get actual values

        state = super()._get_state()
        state.update({
            'target_flow': self._get_step_value(),
            'flow': [0 for _ in range(len(self._get_step_value()))]
        })

        return state

    def _primary_key_field(self):
        return 'flow',


class HumidityExperiment(_SteppedExperiment):
    def __init__(self, label, vgen_connector, vgen_temperature, vgen_rtd_incline=None, vgen_rtd_intercept=None, primary=True):
        super().__init__(label, vgen_temperature, primary)

        self._log.info('Setup VGen humidity controller')

    def reset(self):
        super().reset()

    def step(self):
        super().step()

        temperature = self._get_step_value()

        self._log.info("Saturator: {} °C, Condenser: {} °C".format(temperature[0], temperature[1]))

    def stop(self):
        pass

    def set_resume_state(self, state):
        super().set_resume_state(state)

        # TODO Update controllers

    def _get_state(self):
        # TODO Get actual values

        temperature = self._get_step_value()

        state = super()._get_state()
        state.update({
            'relative_humidity': 0,
            'output_temperature': 0,
            'condenser_temperature': 0,
            'condenser_temperature_target': temperature[1],
            'saturator_temperature': 0,
            'saturator_temperature_target': temperature[0],
            'external_temperature': 0
        })

        return state

    def _primary_key_field(self):
        return 'relative_humidity',


class RegulatedTemperatureExperiment(_SteppedExperiment):
    def __init__(self, label, probe_connector, supply_connector, temperature, regulator=None, primary=True):
        super().__init__(label, temperature, primary)

        # Hardware setup
        self._regulator_probe_id = probe_connector
        self._regulator_supply_id = supply_connector

        # TODO create PID loop
        self._regulator = regulator

        self._log.info('Setup temperature regulator')

    def reset(self):
        super().reset()

    def step(self):
        super().step()

        device_temperature = self._get_step_value()

        self._log.info("Device temperature: {} °C".format(device_temperature))

    def stop(self):
        # TODO Bring controller down safely
        pass

    def set_resume_state(self, state):
        super().set_resume_state(state)

        # TODO Update controllers

    def _get_state(self):
        state = super()._get_state()
        state.update({
            'temperature': 0,
            'temperature_target': self._get_step_value(),
            'supply_voltage': 0,
            'supply_current': 0
        })

        return state

    def _primary_key_field(self):
        return 'temperature',


class TimeExperiment(_SteppedExperiment):
    def __init__(self, label, delay, primary=True):
        super().__init__(label, primary)

        self._delay = delay

        self._timer = time.time()

    def reset(self):
        super().reset()

    def step(self):
        super().step()

        self._timer = time.time()
        self._interruptable_sleep(time.time() + self._get_delay())

    def get_resume_state(self):
        return (self._timer,) + super().get_resume_state()

    def set_resume_state(self, state):
        self._timer = state[:1]

        super().set_resume_state(state[1:])

    def _get_state(self):
        state = super()._get_state()
        state.update({
            'iteration': self._get_step(),
            'step_start': self._timer,
            'step_time': time.time() - self._timer,
            'delay': self._get_delay()
        })

        return state

    def _primary_key_field(self):
        return None

    def _get_delay(self):
        if type(self._delay) is list:
            return self._delay[self._get_step()]
        else:
            return self._delay

    def _interruptable_sleep(self, wake_time):
        start_time = time.time()
        sleep_time = wake_time - start_time

        wake_datetime = datetime.datetime.now() + datetime.timedelta(seconds=sleep_time)

        if sleep_time > 0:
            while sleep_time > 0:
                try:
                    self._log.info("Sleeping until {:%H:%M:%S}".format(wake_datetime))
                    time.sleep(sleep_time)
                    break
                except KeyboardInterrupt:
                    self._log.error("Sleep interrupted by user")

                    while True:
                        print('Select an option:\n\tn: Next step\n\ts: Stop\n\tr: Resume\n\rd: Debug\n')

                        cmd = input('Command: ')

                        if cmd in ['n', 'next']:
                            # Return from sleep
                            self._log.warn('Skipping sleep')
                            return
                        elif cmd in ['s', 'stop']:
                            # Raise exception to halt program
                            self._log.warn('Requested stop')
                            raise
                        elif cmd in ['r', 'resume']:
                            # Calculate new sleep time
                            start_time = time.time()
                            sleep_time = wake_time - start_time

                            if sleep_time > 0:
                                self._log.info('User resumed sleep')
                            else:
                                self._log.error('User resumed sleep but timer has expired')

                            break
                        elif cmd in ['d', 'debug']:
                            self._log.warn('Dropping to interactive shell')
                            code.interact(local=locals())
                        else:
                            print('Command not recognised')
        else:
            self._log.warn("Attempted to sleep for zero or negative time ({:.3f} seconds)".format(sleep_time))


class SynchronisedTimeExperiment(TimeExperiment):
    def __init__(self, label, delay, sync_on_first=False, primary=True):
        super().__init__(label, delay, primary)

        self._sync_on_first = sync_on_first
        self._first = False

    def reset(self):
        super(TimeExperiment, self).reset()

    def step(self):
        super(TimeExperiment, self).step()

        if self._sync_on_first and not self._first:
            self._log.info("Synchronised on first step")
            self._timer = time.time()

        wake_time = self._timer + self._get_delay()

        if wake_time > time.time():
            self._interruptable_sleep(wake_time)
        else:
            self._log.warn("Skipping sleep, missed synchronisation by {:.3f} seconds".format(
                time.time() - wake_time))

        # Update time
        self._timer += self._get_delay()

        self._first = True

    def get_resume_state(self):
        return (self._first,) + super().get_resume_state()

    def set_resume_state(self, state):
        self._first = state[:1]

        super().set_resume_state(state[1:])

    def _get_state(self):
        return {
            'sync_lag': time.time() - self._timer
        }.update(super()._get_state())

    def _primary_key_field(self):
        return None


class StateWaitExperiment(Experiment):
    pass
