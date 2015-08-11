import logging
import os
import time

import scipy.io as sio

__author__ = 'chris'


class Exporter():
    _FILE_EXTENSION_SEPARATOR = '.'
    _FILE_DELIMITER = '-'
    _FILE_SPACE = '_'

    _file_date_format = '%Y%m%d%H%M%S'

    def __init__(self, config, type_prefix, type_extension, result_directory, export_prefix=None,
                 file_date_format=None):
        self._config = config
        self._type_prefix = type_prefix
        self._type_extension = type_extension
        self._result_directory = result_directory
        self._export_prefix = export_prefix

        if file_date_format is not None:
            self._file_date_format = file_date_format

        self._log = logging.getLogger(type(self).__name__)
        self._log.debug("Created export module {}".format(type(self).__name__))

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

    def export(self, identifier, data):
        raise NotImplementedError()


class _DelimitedTextExporter(Exporter):
    def __init__(self, config, type_prefix, type_extension, result_directory, text_header, text_delimiter,
                 export_prefix=None, file_date_format=None):
        super().__init__(config, type_prefix, type_extension, result_directory, export_prefix, file_date_format)

        self._text_header = text_header
        self._text_delimiter = text_delimiter

        # Single files is used for all writes, generate the file name at startup
        self._file_name = self._generate_name(None)

        # Check for existing file
        if os.path.isfile(self._file_name):
            raise FileExistsError()

        self._fields = None
        self._header_written = False

    def export(self, identifier, data):
        fields = data.keys()
        values = data.values()

        with open(self._file_name, 'a') as f:
            if self._text_header and not self._header_written:
                f.write(self._text_header + self._text_delimiter.join(fields))

            f.write(self._text_delimiter.join(str(x) for x in values))

        self._log.debug("Appended to {}".format(self._file_name))


class CSVExporter(_DelimitedTextExporter):
    EXTENSION = 'csv'

    def __init__(self, config, result_directory, export_prefix=None):
        super().__init__(config, None, self.EXTENSION, result_directory, '', ', ', export_prefix)


class MatfileExporter(Exporter):
    EXTENSION = 'mat'

    def __init__(self, config, result_directory, export_prefix=None):
        super().__init__(config, None, self.EXTENSION, result_directory, export_prefix)

        self._compress = config.get('compress', True)

    def export(self, identifier, data):
        filename = self._generate_name(identifier)

        sio.savemat(filename, data, do_compression=self._compress)

        self._log.debug("Wrote to {}".format(filename))


class MKSPressureExporter(_DelimitedTextExporter):
    EXTENSION = 'pre'

    def __init__(self, config, result_directory, export_prefix=None):
        super().__init__(config, None, self.EXTENSION, result_directory, None, '\t', export_prefix)


class SummaryTextExporter(Exporter):
    _LINE_FORMAT = "{key}: {value}\n"
    _LINE_MAX_FIELD_SIZE = 8

    EXTENSION = 'txt'

    def __init__(self, config, result_directory, export_prefix=None):
        super().__init__(config, 'summary', self.EXTENSION, result_directory, export_prefix)

    def export(self, identifier, data):
        filename = self._generate_name(identifier)

        with open(filename, 'a') as f:
            for key in sorted(data):
                value = data[key]

                # Skip unsupported or long fields
                if type(value) is dict:
                    continue
                elif type(value) in [list, tuple] and len(value) > self._LINE_MAX_FIELD_SIZE:
                    continue

                f.write(self._LINE_FORMAT.format(key=key, value=str(value)))

        self._log.debug("Wrote to {}".format(filename))
