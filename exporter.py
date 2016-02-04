import collections
import data
import logging
import os
import time

import scipy.io as sio

__author__ = 'chris'


class Exporter(object):
    _FILE_EXTENSION_SEPARATOR = '.'
    _FILE_DELIMITER = '-'
    _FILE_SPACE = '_'

    _file_date_format = '%Y%m%d%H%M%S'

    def __init__(self, type_prefix, type_extension, result_directory, export_prefix=None,
                 file_date_format=None):
        self._type_prefix = type_prefix
        self._type_extension = type_extension
        self._result_directory = result_directory
        self._export_prefix = export_prefix

        if file_date_format is not None:
            self._file_date_format = file_date_format

        self._log = logging.getLogger(type(self).__name__)
        self._log.debug('Created Exporter module')

    def _format_name(self, s):
        return s.strip().replace(' ', self._FILE_SPACE)

    def _generate_name(self, identifier):
        name_fields = []

        # File type and export prefixes
        if self._type_prefix is not None:
            name_fields.append(self._format_name(self._type_prefix))

        if self._export_prefix is not None:
            name_fields.append(self._format_name(self._export_prefix))

        # File creation time
        name_fields.append(time.strftime(self._file_date_format))

        if identifier is not None:
            name_fields.append(self._format_name(identifier))

        filename = self._FILE_DELIMITER.join(str(x) for x in name_fields if len(str(x)) > 0) \
            + (self._FILE_EXTENSION_SEPARATOR + self._type_extension) if self._type_extension is not None else ''

        return os.path.join(self._result_directory, filename)

    def export(self, identifier, export_data):
        raise NotImplementedError()


class _DelimitedTextExporter(Exporter):
    def __init__(self, type_prefix, type_extension, result_directory, text_header, text_delimiter,
                 line_separator=None, **kwargs):
        super().__init__(type_prefix, type_extension, result_directory, **kwargs)

        self._text_header = text_header
        self._text_delimiter = text_delimiter
        self._line_separator = line_separator if line_separator else '\n'

        # Single files is used for all writes, generate the file name at startup
        self._file_name = self._generate_name(None)

        # Check for existing file
        if os.path.isfile(self._file_name):
            raise FileExistsError()

        self._fields = None
        self._header_written = False

    def export(self, identifier, export_data):
        fields = export_data.keys()
        values = export_data.values()

        with open(self._file_name, 'a') as f:
            if self._text_header is not None and not self._header_written:
                f.write(self._text_header + self._text_delimiter.join(fields) + self._line_separator)

                self._header_written = True

            f.write(self._text_delimiter.join(str(x) for x in values) + self._line_separator)

        self._log.debug("Appended to {}".format(self._file_name))

        return self._file_name,


class CSVExporter(_DelimitedTextExporter):
    EXTENSION = 'csv'

    def __init__(self, result_directory, **kwargs):
        super().__init__('csv', self.EXTENSION, result_directory, '', ', ', **kwargs)


class MatfileExporter(Exporter):
    EXTENSION = 'mat'

    def __init__(self, result_directory, compress=True, **kwargs):
        super().__init__('matfile', self.EXTENSION, result_directory, **kwargs)

        self._compress = compress

    def export(self, identifier, export_data):
        filename = self._generate_name(identifier)

        sio.savemat(filename, export_data, do_compression=self._compress)

        self._log.debug("Wrote to {}".format(filename))

        return filename,


class MKSPressureExporter(_DelimitedTextExporter):
    EXTENSION = 'pre'

    def __init__(self, result_directory, field=None, **kwargs):
        super().__init__('mks', self.EXTENSION, result_directory, None, '\t', **kwargs)

        self._field_filter = data.generate_data_field_list(field)

    def export(self, identifier, export_data):
        # Filter data fields
        export_data_filtered = collections.OrderedDict()

        if self._field_filter:
            for field in self._field_filter:
                if field.in_dict(export_data):
                    export_data_filtered[field.name] = field.get_value(export_data)
                else:
                    export_data_filtered[field.name] = ''

            return super(MKSPressureExporter, self).export(identifier, export_data_filtered)
        else:
            return super(MKSPressureExporter, self).export(identifier, export_data)


class SummaryLogExporter(Exporter):
    def __init__(self, level, field, **kwargs):
        super().__init__(None, None, **kwargs)

        self._level = logging.getLevelName(level)
        self._field_filter = data.generate_data_field_list(field)

    def export(self, identifier, export_data):
        for field in self._field_filter:
            if field.in_dict(export_data):
                self._log.log(self._level, field.to_str(field.get_value(export_data)))

        return None


class SummaryTextExporter(Exporter):
    _LINE_FORMAT = "{key}: {value}\n"
    _LINE_MAX_FIELD_SIZE = 8

    EXTENSION = 'txt'

    def __init__(self, result_directory, line_format=None, **kwargs):
        super().__init__('summary', self.EXTENSION, result_directory, **kwargs)

        self._line_format = line_format if line_format else self._LINE_FORMAT

    def export(self, identifier, export_data):
        filename = self._generate_name(identifier)

        with open(filename, 'a') as f:
            for key in sorted(export_data):
                value = export_data[key]

                # Skip unsupported or long fields
                if type(value) is dict:
                    continue
                elif type(value) in [list, tuple] and len(value) > self._LINE_MAX_FIELD_SIZE:
                    continue

                f.write(self._line_format.format(key=key, value=str(value)))

        self._log.debug("Wrote to {}".format(filename))

        return filename,
