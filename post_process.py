import logging

__author__ = 'chris'


class PostProcessorException(Exception):
    pass


class PostProcessor():
    def __init__(self, config):
        self._config = config

        self._log = logging.getLogger(type(self).__name__)

    def process(self, data):
        raise NotImplementedError()


class ThresholdPostProcessor(PostProcessor):
    def __init__(self, config):
        super().__init__(config)

        self._limit = []

        for threshold in config['threshold']:
            level = logging.getLevelName(threshold.get('action', 'WARNING'))

            self._limit.append({
                'field': threshold.get('field'),
                'level': level,
                'exception': threshold.get('exception', False),
                'min': threshold.get('min', None),
                'max': threshold.get('max', None)
            })

    def process(self, data):
        for limit in self._limit:
            if limit['field'] in data.keys():
                field_data = data[limit['field']]

                limit_min = limit['min'] and field_data < limit['min']
                limit_max = limit['max'] and field_data > limit['max']

                if limit_min:
                    logging.log(limit['level'], "Field {} = {} is under threshold {}".format(limit['field'], field_data,
                                                                                             limit['min']))

                if limit_max:
                    logging.log(limit['level'], "Field {} = {} is over threshold {}".format(limit['field'], field_data,
                                                                                            limit['max']))

                if (limit_min or limit_max) and limit['exception']:
                    raise PostProcessorException('Data field outside threshold range')

        return data
