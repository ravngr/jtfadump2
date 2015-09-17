import logging

__author__ = 'chris'


class PostProcessorException(Exception):
    pass


class PostProcessor(object):
    def __init__(self):
        self._log = logging.getLogger(type(self).__name__)

    def process(self, data):
        raise NotImplementedError()


class ThresholdPostProcessor(PostProcessor):
    def __init__(self, field, unit=None, level='WARNING', limit_min=None, limit_max=None, exception=False):
        super().__init__()

        self._field = field
        self._unit = unit
        self._level = logging.getLevelName(level)
        self._exception = exception
        self._min = limit_min
        self._max = limit_max

    def process(self, data):
        if self._field in data.keys():
            value = data[self._field]

            limit_min = self._min and value < self._min
            limit_max = self._max and value > self._max

            log_dict = {
                'field': self._field,
                'value': value,
                'unit': ' ' + self._unit if self._unit else '',
                'min': self._min,
                'max': self._max
            }

            if limit_min:
                self._log.log(self._level, "Data field {field} is under threshold {value}{unit} < {min}{unit}".format(
                    **log_dict))

            if limit_max:
                self._log.log(self._level, "Data field {field} is over threshold {value}{unit} > {max}{unit}".format(
                    **log_dict))

            if (limit_min or limit_max) and self._exception:
                raise PostProcessorException('Data field outside threshold range')
        else:
            self._log.warn("Data field {} not present in capture".format(self._field))

        return data
