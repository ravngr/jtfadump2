#!/usr/bin/env python
# -- coding: utf-8 --

import argparse
import logging
import logging.config
import os
import sys
import time

import serial
import pyvisa
import yaml

import capture
import experiment
import exporter
import post_process
import util

__author__ = 'Christopher Harrison'
__license__ = 'MIT'
__version__ = '0.1.0'
__maintainer__ = 'Christopher Harrison'
__email__ = 'dev@ravngr.com'
__status__ = 'Development'


class ExperimentNode:
    def __init__(self, exp, children=None):
        self.experiment = exp

        if children:
            self.children = children
            self.size = 1 + sum([x.size for x in children])
        else:
            self.children = None
            self.size = 1


def _generate_module_args(global_config, parent, *args, **kwargs):
    class_name = kwargs.pop('class')

    # If module has global configuration options then load those first
    if class_name in global_config:
        instance_config = global_config[class_name]

        # Overwrite global options with parameters for this instance
        instance_config.update(kwargs)
    else:
        instance_config = kwargs

    return util.class_instance_from_dict(class_name, parent, *args, **instance_config)


def _generate_experiment_tree(module_config, global_module_config):
    # Generate new node using global config with overrides
    config = global_module_config.get(module_config['class'], {})
    config.update(module_config)

    c = util.class_from_str(config.pop('class'), experiment.__name__)
    child_nodes = []

    if 'child' in config:
        config_child = config.pop('child')

        for child in config_child:
            child_nodes.append(_generate_experiment_tree(child, global_module_config))

    return ExperimentNode(c(config), child_nodes)


def main():
    # Get start time
    start_time = time.gmtime()
    start_time_str = time.strftime('%Y%m%d_%H%M%S', start_time)

    # Generate list of available modules
    module_list = 'Experiment Modules:\n\t'
    module_list += '\n\t'.join(util.get_module_subclasses(experiment, experiment.Experiment))

    module_list += '\n\nCapture Modules:\n\t'
    module_list += '\n\t'.join(util.get_module_subclasses(capture, capture.Capture))

    module_list += '\n\nPost-Process Modules:\n\t'
    module_list += '\n\t'.join(util.get_module_subclasses(post_process, post_process.PostProcessor))

    module_list += '\n\nExporter Modules:\n\t'
    module_list += '\n\t'.join(util.get_module_subclasses(exporter, exporter.Exporter))

    # Parse command line arguments
    parse = argparse.ArgumentParser(description='jtfadump2 Experiment System',
                                    formatter_class=argparse.RawDescriptionHelpFormatter, epilog=module_list)

    parse.add_argument('name', help='Prefix for results folder')
    parse.add_argument('config', help='YAML configuration file(s)', nargs='+')

    parse.add_argument('-v', '--verbose', help='Verbose output', dest='display_verbose', action='store_true')
    parse.set_defaults(display_verbose=False)
    parse.add_argument('--visa', help='Display VISA traffic in console', dest='display_visa', action='store_true')
    parse.set_defaults(display_visa=False)
    parse.add_argument('-q', '--quiet', help='Suppress info logging output', dest='display_quiet', action='store_true')
    parse.set_defaults(display_visa=False)

    args = parse.parse_args()

    # Get experiment prefix
    experiment_name = args.name.strip().replace(' ', '_')

    # Load configuration file(s)
    config = {}

    for f in args.config:
        with open(f, 'r') as h:
            config.update(yaml.load(h))

    # Setup directories
    result_path = os.path.realpath(config['result']['path'])

    if not os.path.exists(result_path) or not os.path.isdir(result_path):
        print("Result directory {} either doesn't exist or is not a writable directory".format(result_path),
              file=sys.stderr)
        return

    result_path = os.path.join(result_path, "{}-{}".format(experiment_name, start_time_str))

    # Create result directory
    os.makedirs(result_path, exist_ok=False)

    log_path = os.path.realpath(config['logging'].get('path', result_path))

    # Setup logging
    logging_config_dict = config.pop('logging')['config']

    # Generate log filename
    log_filename = os.path.join(log_path, "log-{}-{}.log".format(experiment_name, start_time_str))

    # If a filename is None then set the generated name as the target
    if logging_config_dict['handlers']:
        for (key, value) in logging_config_dict['handlers'].items():
            if 'filename' in value and not value['filename']:
                logging_config_dict['handlers'][key]['filename'] = log_filename

    # Apply logging configuration
    logging.config.dictConfig(logging_config_dict)

    root_logger = logging.getLogger(__name__)

    try:
        git_hash = util.get_git_hash()
    except OSError:
        git_hash = 'not found'

    root_logger.info("jtfadump2 | git hash: {}".format(git_hash))
    root_logger.info("python {}".format(sys.version))

    for m in [('pyserial', serial.VERSION), (pyvisa.__name__, pyvisa.__version__), ('pyyaml', yaml.__version__)]:
        root_logger.info("{} {}".format(m[0], m[1]))

    root_logger.info("Started: {}".format(time.strftime('%a, %d %b %Y %H:%M:%S +0000', start_time)))
    root_logger.info("Launch command: {}".format(' '.join(sys.argv)))
    root_logger.info("Result directory: {}".format(result_path))

    # Dump configuration to log
    root_logger.debug('--- BEGIN CONFIGURATION ---')

    for line in yaml.dump(config).split('\n'):
        root_logger.debug(line)

    root_logger.debug('--- END CONFIGURATION ---')

    # Setup modules
    if 'experiment' not in config or not config['experiment']:
        root_logger.error('Configuration must specify at least one experiment module!', file=sys.stderr)
        return

    if 'experiment' not in config or not config['capture']:
        root_logger.error('Configuration must specify at least one capture module!', file=sys.stderr)
        return

    if 'export' not in config or not config['export']:
        root_logger.error('Configuration must specify at least one export module!', file=sys.stderr)
        return

    # Get global module configuration
    global_module_config = config.pop('modules')

    # Create modules
    capture_modules = []
    post_process_modules = []
    export_modules = []

    for module_config in config.pop('capture'):
        capture_modules.append(_generate_module_args(global_module_config, capture.__name__, **module_config))

    for module_config in config.pop('export'):
        export_modules.append(_generate_module_args(global_module_config, exporter.__name__,
                                                    result_directory=result_path, **module_config))

    if 'post' in config and config['post']:
        for module_config in config.pop('post'):
            post_process_modules.append(_generate_module_args(global_module_config, post_process.__name__,
                                                              **module_config))

    capture_module_count = len(capture_modules)
    post_process_module_count = len(post_process_modules)
    export_module_count = len(export_modules)

    # Connect to all hardware

    # Setup experiment stack
    experiment_nodes = []
    experiment_module_count = 0

    for node_config in config.pop('experiment'):
        node = _generate_experiment_tree(node_config, global_module_config)

        experiment_module_count += node.size

        experiment_nodes.append(node)

    # Note loaded modules
    root_logger.info("Loaded {} experiment module{}".format(experiment_module_count,
                                                            's' if experiment_module_count is not 1 else ''))
    root_logger.info("Loaded {} capture module{}".format(capture_module_count,
                                                         's' if capture_module_count is not 1 else ''))
    root_logger.info("Loaded {} post-process module{}".format(post_process_module_count,
                                                              's' if post_process_module_count is not 1 else ''))
    root_logger.info("Loaded {} export module{}".format(export_module_count,
                                                        's' if export_module_count is not 1 else ''))

    # Track running experiments in order to stop them properly
    running_experiments = []

    # Catch all exceptions for logging
    try:
        # Step experiment stack
        active_experiments = []

        while experiment_nodes:
            current_node = experiment_nodes[0]
            current_experiment = current_node.experiment

            if current_experiment.has_next():
                # Add experiment to active list
                if current_experiment not in active_experiments:
                    active_experiments.append(current_experiment)

                if current_experiment not in running_experiments:
                    running_experiments.append(current_experiment)

                # Step the active experiment
                current_experiment.step()

                if current_node.children:
                    # Append children to node stack
                    experiment_nodes[:0] = current_node.children
                else:
                    # Save data from this experiment
                    # Generate a unique identifier for the capture
                    capture_id = util.rand_hex_str(64)
                    capture_id_short = capture_id[-8::]

                    # Timestamp data and attach unique id
                    data = {
                        'cap_id': capture_id,
                        'cap_time': time.strftime('%a, %d %b %Y %H:%M:%S +0000'),
                        'cap_timestamp': time.time()
                    }

                    # Get current state of experiment
                    for e in active_experiments:
                        data.update(e.get_state())

                    # Capture data from all sources
                    for c in capture_modules:
                        data.update(c.get_data(active_experiments))

                    # Apply optional post-processors to data
                    if post_process_modules:
                        for p in post_process_modules:
                            d = p.process(data)

                            # Don't let badly written post-processors wipe out data
                            if d is not None:
                                data = d
                            else:
                                root_logger.warn("PostProcessor {} returning no data".format(p.__name__))

                    # Export data
                    for e in export_modules:
                        e.export(capture_id_short, data)
            else:
                # Remove experiment both from the stack and from the active list
                experiment_nodes.pop(0)
                active_experiments.remove(current_experiment)

                # Reset experiment state in case it is re-used
                current_experiment.reset()

        root_logger.info('Experiment finished normally')
    except:
        root_logger.exception('Caught exception in main loop', exc_info=True)
        raise
    finally:
        # Stop all running experiments
        for e in running_experiments:
            e.stop()

    root_logger.info('Exiting')


if __name__ == "__main__":
    main()
