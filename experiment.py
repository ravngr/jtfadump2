# -- coding: utf-8 --

import datetime
import logging
import time

__author__ = 'chris'


class ExperimentConfigurationException(Exception):
    pass


class Experiment(object):
    def __init__(self, config):
        self._config = config

        self._label = config.pop('label')
        self._primary = config.get('primary', True)

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

        if not primary_key:
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
    def __init__(self, config, field):
        super().__init__(config)

        self._field = field

        self._current_step = 0
        self._next_step = 0

    def step(self):
        self._current_step = self._next_step
        self._next_step += 1

        self._log.info("Step {} of {}".format(self._current_step + 1, self._step_maximum()))

    def reset(self):
        self._current_step = 0
        self._next_step = 0

        self._log.info('Step reset')

    def has_next(self):
        return self._next_step < self._step_maximum()

    def get_resume_state(self):
        return self._current_step, self._next_step,

    def set_resume_state(self, state):
        self._current_step, self._next_step = state

    def _get_state(self):
        return {
            self._field + '_step': self._get_step()
        }

    def _primary_key_field(self):
        raise NotImplementedError()

    def _step_maximum(self):
        if type(self._config[self._field]) is list:
            return len(self._config[self._field])
        else:
            return 1

    def _get_step(self):
        return self._current_step


class _IncrementExperiment(_SteppedExperiment):
    def __init__(self, config, field):
        super().__init__(config, field)

    def _get_state(self):
        return {
            self._field + '_increment': self._get_step()
        }

    def _primary_key_field(self):
        raise NotImplementedError()

    def _step_maximum(self):
        return int(self._config.get(self._field, 1))


class FlowExperiment(_SteppedExperiment):
    def __init__(self, config):
        super().__init__(config, 'flow_rate')

        self._flow_rate = config['flow_rate']
        self._channels = len(self._flow_rate[0])

        self._log.info("Setup {} channel mass flow controller".format(self._channels))

    def reset(self):
        super().reset()

    def step(self):
        super().step()

        flow_rate = self._get_flow()

        self._log.info("Flow rate: {} sccm".format(' sccm, '.join([str(x) for x in flow_rate])))

    def stop(self):
        pass

    def set_resume_state(self, state):
        super().set_resume_state(state)

        # TODO Update controllers

    def _get_flow(self):
        return self._flow_rate[self._get_step()]

    def _get_state(self):
        # TODO Get actual values

        state = super()._get_state()
        state.update({
            'target_flow': self._flow_rate[self._get_step()],
            'flow': [0 for _ in range(len(self._get_flow()))]
        })

        return state

    def _primary_key_field(self):
        return 'flow',


class HumidityExperiment(_SteppedExperiment):
    def __init__(self, config):
        super().__init__(config, 'vgen_temperature')

        self._vgen_temperature = config['vgen_temperature']

        self._log.info('Setup VGen humidity controller')

    def reset(self):
        super().reset()

    def step(self):
        super().step()

        temperature = self._get_vgen_temperature_target()

        self._log.info("Saturator: {} °C, Condenser: {} °C".format(temperature[0], temperature[1]))

    def stop(self):
        pass

    def set_resume_state(self, state):
        super().set_resume_state(state)

        # TODO Update controllers

    def _get_vgen_temperature_target(self):
        return self._vgen_temperature[self._get_step()]

    def _get_state(self):
        # TODO Get actual values

        temperature = self._get_vgen_temperature_target()

        state = super()._get_state()
        state.update({
            'relative_humidity': 0,
            'output_temperature': 0,
            'condenser_temperature': 0,
            'condenser_temperature_target': 0,
            'saturator_temperature': 0,
            'saturator_temperature_target': 0,
            'external_temperature': 0
        })

        return state

    def _primary_key_field(self):
        return 'relative_humidity',


class RegulatedTemperatureExperiment(_SteppedExperiment):
    def __init__(self, config):
        super().__init__(config, 'temperature')

        # Hardware setup
        self._regulator_probe_id = config['probe']
        self._regulator_supply_id = config['supply']

        if 'regulator' in config:
            config_regulator = config['regulator']
        else:
            config_regulator = {}

        self._regulator_pid = {
            'p': config_regulator.get('p', 1),
            'i': config_regulator.get('i', 0),
            'd': config_regulator.get('d', 0),
            'period': config_regulator.get('period', 1),
            'limit': (config_regulator.get('out_min', None), config_regulator.get('out_max', None))
        }

        # Experimental parameters
        self._device_temperature = config['temperature']

        self._log.info('Setup temperature regulator')

    def reset(self):
        super().reset()

    def step(self):
        super().step()

        device_temperature = self._get_temperature_target()

        self._log.info("Device temperature: {} °C".format(device_temperature))

    def stop(self):
        # TODO Bring controller down safely
        pass

    def set_resume_state(self, state):
        super().set_resume_state(state)

        # TODO Update controllers

    def _get_temperature_target(self):
        return self._device_temperature[self._get_step()]

    def _get_state(self):
        state = super()._get_state()
        state.update({
            'temperature': 0,
            'temperature_target': self._get_temperature_target(),
            'supply_voltage': 0,
            'supply_current': 0
        })

        return state

    def _primary_key_field(self):
        return 'temperature',


class TimeExperiment(_SteppedExperiment):
    def __init__(self, config):
        super().__init__(config, 'delay')

        self._delay = config['delay']

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
                        print('Select an option:\n\tn: Next step\n\ts: Stop\n\tr: Resume\n')

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
                        else:
                            print('Command not recognised')
        else:
            self._log.warn("Attempted to sleep for zero or negative time ({:.3f} seconds)".format(sleep_time))


class SynchronisedTimeExperiment(TimeExperiment):
    def __init__(self, config):
        super().__init__(config)

        self._sync_on_first = config.get('sync_on_first', False)
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


class ExperimentStateExperiment(Experiment):
    pass
