import functools
import inspect
import logging
import os
import random
import requests.exceptions
import string
import subprocess
import sys
import time

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


def class_instance_from_dict(class_name, parent, *args, **kwargs):
    class_type = class_from_str(class_name, parent)

    return class_type(*args, **kwargs)


class ExceptionRetry(object):
    default_retry = 3

    def __init__(self, exception_types, log=None, log_attribute=None, retry=None, retry_attribute=None,
                 reset=None, reset_method=None, reset_args=None, reset_kwargs=None, wait=None, wait_attribute=None):
        self._exception_types = exception_types
        self._log = log
        self._log_attribute = log_attribute
        self._retry = retry
        self._retry_attribute = retry_attribute
        self._reset = reset
        self._reset_method = reset_method
        self._reset_args = reset_args if reset_args else ()
        self._reset_kwargs = reset_kwargs if reset_kwargs else {}
        self._wait = wait
        self._wait_attribute = wait_attribute

    def __call__(self, f):
        @functools.wraps(f)
        def func(*args, **kwargs):
            retry = ExceptionRetry.default_retry

            if self._retry:
                retry = self._retry

            if self._retry_attribute:
                retry = getattr(args[0], self._retry_attribute)

            for attempt in range(retry):
                attempt_remain = (retry - 1) - attempt

                try:
                    return f(*args, **kwargs)
                except Exception as e:
                    # If exception is expected or a sub-class of an expected exception then ignore it as long as there
                    # are remaining attempts
                    if type(e) in self._exception_types or issubclass(type(e), tuple(self._exception_types)):
                        log_dict = {
                            'attempt': attempt,
                            'attempt_remain': attempt_remain,
                            'attempt_plural': 's' if attempt_remain else '',
                            'exception': str(type(e)),
                            'function': str(f)
                        }

                        if attempt_remain is 0:
                            raise
                        else:
                            # Optional delay before retry
                            wait = None

                            if self._wait:
                                wait = self._wait

                            if self._wait_attribute:
                                wait = getattr(args[0], self._wait_attribute)

                            log = None

                            if self._log:
                                log = self._log

                            if self._log_attribute:
                                log = getattr(args[0], self._log_attribute)

                            if log:
                                log.warning("Ignoring exception during call to {function}, "
                                            "{attempt_remain} attempt{attempt_plural} "
                                            "remaining".format(**log_dict), exc_info=True)

                                if wait:
                                    log.warning("Waiting {} second{} "
                                                "before next attempt".format(wait, 's' if wait is not 1 else ''))

                            # After a failed attempt call the optional reset function
                            reset = None

                            if self._reset:
                                reset = self._reset

                            if self._reset_method:
                                reset = getattr(args[0], self._reset_method)

                            if reset:
                                reset(*self._reset_args, **self._reset_kwargs)

                            if wait:
                                time.sleep(wait)
                    else:
                        # Raise any unexpected exceptions
                        raise

        return func


def decorator_factory(decorator, *args, **kwargs):
    decorator_instance = decorator(*args, **kwargs)

    def func(*inner_args, **inner_kwargs):
        return decorator_instance(*inner_args, **inner_kwargs)

    return func


# From http://stackoverflow.com/questions/12826723/possible-to-extract-the-git-repo-revision-hash-via-python-code
def get_git_hash():
    git_process = subprocess.Popen(['git', 'rev-parse', 'HEAD'], stdout=subprocess.PIPE, stderr=None)
    (git_out, _) = git_process.communicate()
    return git_out.strip()


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
