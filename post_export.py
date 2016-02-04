import logging
import os
import shutil
import zipfile

__author__ = 'chris'


class PostExporterException(Exception):
    pass


class PostExporter(object):
    def __init__(self, result_directory):
        self._log = logging.getLogger(type(self).__name__)

        self._result_directory = result_directory

    def process(self, exported_files):
        raise NotImplementedError()


class BackupCopy(PostExporter):
    def __init__(self, result_directory, target_directory):
        super().__init__(result_directory)

        self._target_directory = target_directory

    def process(self, exported_files):
        # Copy exported files to target directory
        backup_files = []

        for f in exported_files:
            # Generate new path
            target_path = os.path.join(self._target_directory, os.path.basename(f))

            self._log.debug("Copying file {} to {}".format(f, target_path))

            shutil.copyfile(f, target_path)

            backup_files.append(target_path)

        return tuple(backup_files)


class LatestCopy(BackupCopy):
    def __init__(self, result_directory, target_directory):
        super().__init__(result_directory, target_directory)

        self.target_directory = target_directory

        self.created_files = ()

    def process(self, exported_files):
        # Delete the previous copy in target directory
        if self.created_files:
            for f in self.created_files:
                if os.path.exists(f) and os.path.isfile(f):
                    self._log.debug("Deleting previous copy {}".format(f))

                    try:
                        os.remove(f)
                    except (IOError, OSError, FileNotFoundError):
                        self._log.exception("Exception raised while attempting to delete previous copy {}".format(f),
                                            exc_info=True)
                else:
                    self._log.warn("Previous copy {} not deleted".format(f))

        # Backup files as the parent class would
        backup_files = super(LatestCopy, self).process(exported_files)

        self.created_files = backup_files

        return backup_files


class ZipPostExporter(PostExporter):
    EXTENSION = 'zip'

    def __init__(self, result_directory):
        super().__init__(result_directory)

        self._zip_filename = result_directory + '.' + self.EXTENSION

    def process(self, exported_files):
        with zipfile.ZipFile(self._zip_filename, 'a') as result_zip:
            for f in exported_files:
                result_zip.write(f)

        self._log.info("Updated {}".format(self._zip_filename))

        return self._zip_filename,
