__author__ = 'chris'


class DataField():
    def __init__(self, name, index=None, friendly_name=None, unit=None):
        self.name = name
        self.index = index
        self.friendly_name = friendly_name
        self.unit = unit

    def field_to_str(self, value, value_format, format=None):
        return ().format(

        )

        return (format if format is not None else "{name}: {value}{unit}")

        return "{}: {}{}".format(self.friendly_name if self.friendly_name else self.name, str(value))  ': ' + str(value) + (' ' + self.unit if self.unit else '')


def generate_data_field_list(field_dict_list):
    return [DataField(**f) for f in field_dict_list]
