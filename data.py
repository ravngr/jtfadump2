__author__ = 'chris'


class DataException(Exception):
    pass


class DataField(object):
    DEFAULT_FORMAT = "{name}{index}: {value}{unit}"

    def __init__(self, name, index=None, friendly_name=None, unit=None, default_value=None):
        self.name = name
        self.index = index
        self.friendly_name = friendly_name
        self.unit = unit
        self.default_value = default_value

    def get_value(self, data_dict):
        if self.index is not None:
            return data_dict[self.name][self.index]
        else:
            return data_dict[self.name]

    def in_dict(self, result_dict):
        if self.name not in result_dict:
            return False

        if self.index is not None:
            return type(result_dict[self.name]) in (tuple, list) and len(result_dict[self.name]) > self.index
        else:
            return True

    def to_str(self, value=None, str_format=None):
        if value is None:
            if self.default_value is None:
                raise DataException('No value or default_value to print')

            value = self.default_value

        name = self.friendly_name if self.friendly_name else self.name
        index = "[{}]".format(self.index) if self.index is not None and not self.friendly_name else ''
        unit = " {}".format(self.unit) if self.unit is not None else ''

        return (str_format or self.DEFAULT_FORMAT).format(
            name=name, index=index, value=value, unit=unit
        )


class DataLimit(object):
    def __init__(self, minimum=None, maximum=None):
        self.minimum = minimum
        self.maximum = maximum

    def test(self, value):
        flag = True

        if self.maximum is not None:
            flag &= value < self.maximum

        if self.minimum is not None:
            flag &= value > self.minimum

        return flag


def generate_data_field_list(field_dict_list):
    if field_dict_list is None:
        return None

    return [DataField(**f) for f in field_dict_list]
