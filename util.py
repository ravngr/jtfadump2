import functools
import inspect
import logging
import os
import random
import requests.exceptions
import string
import subprocess
import sys

import pushover
import yaml

try:
    import colorama
except ImportError:
    colorama = None

__author__ = 'chris'


def rand_hex_str(length=8):
    return ''.join(random.choice(string.hexdigits[:16]) for _ in range(length))


# From http://stackoverflow.com/questions/1176136/convert-string-to-python-class-object
def class_from_str(class_name, parent):
    return functools.reduce(getattr, class_name.split('.'), sys.modules[parent])


def class_from_dict(config, parent):
    class_type = class_from_str(config.pop('class'), parent)

    return class_type(**config)


# From http://stackoverflow.com/questions/12826723/possible-to-extract-the-git-repo-revision-hash-via-python-code
def get_git_hash():
    proc = subprocess.Popen(['git', 'rev-parse', 'HEAD'], stdout=subprocess.PIPE, stderr=None)
    (proc_out, _) = proc.communicate()
    return proc_out.strip()


def get_module_subclasses(module, parent):
    subclass_list = []

    for m in dir(module):
        m = class_from_str(m, module.__name__)

        if m is not parent and inspect.isclass(m) and issubclass(m, parent) and m.__name__[0] is not '_':
            subclass_list.append(str(m.__name__).split('.', 1)[-1])

    return subclass_list


def unique_list(l):
    seen = set()
    seen_add = seen.add

    return [x for x in l if not (x in seen or seen_add(x))]


# From http://stackoverflow.com/questions/528281/how-can-i-include-an-yaml-file-inside-another
class RecursiveLoader(yaml.Loader):
    def __init__(self, stream):
        self._root = os.path.split(stream.name)[0]

        super(RecursiveLoader, self).__init__(stream)

    def include(self, node):
        filename = os.path.join(self._root, self.construct_scalar(node))

        with open(filename, 'r') as f:
            return yaml.load(f, RecursiveLoader)

RecursiveLoader.add_constructor('!include', RecursiveLoader.include)


class PushoverHandler(logging.Handler):
    priority_map = {
        logging.DEBUG: -1,
        logging.INFO: -1,
        logging.WARNING: -1,
        logging.ERROR: 0,
        logging.CRITICAL: 1
    }

    def __init__(self, title, api_token=None, user_key=None, device=None, priority_map=None):
        super().__init__()

        if priority_map:
            self.priority_map = priority_map

        self._title = title
        self._pushover = pushover.Client(api_token=api_token, user_key=user_key, device=device)

    def emit(self, record):
        msg = self.format(record)
        priority = self.priority_map[record.levelno] if record.levelno in self.priority_map else 0

        try:
            self._pushover.send_message(msg, priority=priority, title=self._title)
        except requests.exceptions.ConnectionError:
            print('Connection error when connecting to Pushover', file=sys.stderr)


if colorama:
    # From https://gist.github.com/ravngr/26b84b73a1457d69185e
    class ColorizingStreamHandler(logging.StreamHandler):
        color_map = {
            logging.DEBUG: colorama.Style.BRIGHT + colorama.Fore.BLACK,
            logging.WARNING: colorama.Style.BRIGHT + colorama.Fore.YELLOW,
            logging.ERROR: colorama.Style.BRIGHT + colorama.Fore.RED,
            logging.CRITICAL: colorama.Back.RED + colorama.Fore.WHITE
        }

        def __init__(self, stream, color_map=None):
            super().__init__(colorama.AnsiToWin32(stream).stream)
            if color_map is not None:
                self.color_map = color_map

        @property
        def is_tty(self):
            isatty = getattr(self.stream, 'isatty', None)
            return isatty and isatty()

        def format(self, record):
            message = super().format(record)
            if self.is_tty:
                # Don't colorize a traceback
                parts = message.split('\n', 1)
                parts[0] = self.colorize(parts[0], record)
                message = '\n'.join(parts)
            return message

        def colorize(self, message, record):
            try:
                return self.color_map[record.levelno] + message + colorama.Style.RESET_ALL

            except KeyError:
                return message
else:
    # Define dummy handler if colorama is not installed
    class ColorizingStreamHandler(logging.StreamHandler):
        def __init__(self, stream, color_map=None):
            logging.StreamHandler.__init__(self, stream)
