import logging

import data

__author__ = 'chris'


class PostProcessorException(Exception):
    pass


class PostProcessor(object):
    def __init__(self):
        self._log = logging.getLogger(type(self).__name__)

    def process(self, experiment_data):
        raise NotImplementedError()


class ThresholdPostProcessor(PostProcessor):
    def __init__(self, field, limit, exception=False, level='WARNING'):
        super().__init__()

        self._level = logging.getLevelName(level)
        self._field = data.DataField(**field)
        self._limit = data.DataLimit(**limit)
        self._exception = exception

    def process(self, experiment_data):
        # Check that each field specified is within set limits
        if self._field.name in experiment_data:
            value = self._field.get_value(experiment_data)

            if not self._limit.test(value):
                err_str = "Field {} outside limit".format(self._field.to_str(value))

                if self._exception:
                    raise PostProcessorException(err_str)
                else:
                    self._log.log(self._level, err_str)
        else:
            self._log.warn("Field {} not present in data".format(self._field.name))

        return experiment_data
