#!/usr/bin/env python2

# RELOAD DURING DEVELOPMENT:
#
#  docker exec compose_archivematica-mcp-client_1 touch /tmp/continue.txt



"""Archivematica Client (Gearman Worker)

This executable does the following.

1. Loads tasks from config. Loads a list of performable tasks (client scripts)
   from a config file (typically that in lib/archivematicaClientModules) and
   creates a mapping from names of those tasks (e.g., 'normalize_v1.0') to the
   full paths of their corresponding (Python or bash) scripts (e.g.,
   '/src/MCPClient/lib/clientScripts/normalize.py').

2. Registers tasks with Gearman. On multiple threads, create a Gearman worker
   and register the loaded tasks with the Gearman server, effectively saying
   "Hey, I can normalize files", etc.

When the MCPServer requests that the MCPClient perform a registered task, the
MCPClient thread calls ``execute_command``, passing it a job object which has a
``task`` attribute containing the name of the client script to run, and a
``data`` attribute whose value is a BLOB that unpickles to a dict containing
arguments to pass to the client script. The following then happens.

1. The client script is run in a subprocess with the provided arguments.

2. The exit code and output streams are pickled and returned.

"""

# This file is part of Archivematica.
#
# Copyright 2010-2017 Artefactual Systems Inc. <http://artefactual.com>
#
# Archivematica is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# Archivematica is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with Archivematica.  If not, see <http://www.gnu.org/licenses/>.

# @package Archivematica
# @subpackage archivematicaClient
# @author Joseph Perry <joseph@artefactual.com>

import ConfigParser
import cPickle
import logging
import os
from socket import gethostname
import threading
import time
import traceback

import django
django.setup()
from django.conf import settings as django_settings
import gearman

from main.models import Task
from databaseFunctions import auto_close_db, getUTCDate
from executeOrRunSubProcess import executeOrRun

from django.db import transaction
import batch_development
import shlex
import importlib
import traceback

logger = logging.getLogger('archivematica.mcp.client')

replacement_dict = {
    '%sharedPath%': django_settings.SHARED_DIRECTORY,
    '%clientScriptsDirectory%': django_settings.CLIENT_SCRIPTS_DIRECTORY,
    '%clientAssetsDirectory%': django_settings.CLIENT_ASSETS_DIRECTORY,
}

# This dict will map the names of the client scripts listed in the config file
# (typically MCPClient/lib/archivematicaClientModules) to the full paths to
# those scripts on disk.
supported_modules = {}


def load_supported_modules_support(client_script, client_script_path):
    """Replace variables in ``client_script_path`` and confirm that said path
    is an existent file.
    """
    for key2, value2 in replacement_dict.items():
        client_script_path = client_script_path.replace(key2, value2)
    if not os.path.isfile(client_script_path):
        logger.error('Warning! Module can\'t find file, or relies on system'
                     ' path: {%s} %s', client_script, client_script_path)
    supported_modules[client_script] = client_script_path + ' '


def load_supported_modules(file):
    """Populate the global `supported_modules` dict by parsing the MCPClient
    modules config file (typically MCPClient/lib/archivematicaClientModules).
    """
    supported_modules_config = ConfigParser.RawConfigParser()
    supported_modules_config.read(file)
    for client_script, client_script_path in supported_modules_config.items(
            'supportedCommands'):
        load_supported_modules_support(client_script, client_script_path)
    if django_settings.LOAD_SUPPORTED_COMMANDS_SPECIAL:
        for client_script, client_script_path in supported_modules_config.items(
                'supportedCommandsSpecial'):
            load_supported_modules_support(client_script, client_script_path)


class ProcessGearmanJobError(Exception):
    pass


def _process_gearman_job(gearman_job, gearman_worker):
    """Process a gearman job/task: return a 3-tuple consisting of a script
    string (a command-line script with arguments), a task UUID string, and a
    boolean indicating whether output streams should be captured. Raise a
    custom exception if the client script is unregistered or if the task has
    already been started.
    """
    # ``client_script`` is a string matching one of the keys (i.e., client
    # scripts) in the global ``supported_modules`` dict.
    client_script = gearman_job.task
    task_uuid = str(gearman_job.unique)
    logger.info('Executing %s (%s)', client_script, task_uuid)
    data = cPickle.loads(gearman_job.data)
    utc_date = getUTCDate()
    arguments = data['arguments']
    if isinstance(arguments, unicode):
        arguments = arguments.encode('utf-8')
    client_id = gearman_worker.worker_client_id
    task = Task.objects.get(taskuuid=task_uuid)
    if task.starttime is not None:
        raise ProcessGearmanJobError({
            'exitCode': -1,
            'stdOut': '',
            'stdError': 'Detected this task has already started!\n'
                        'Unable to determine if it completed successfully.'})
    task.client = client_id
    task.starttime = utc_date
    task.save()
    client_script_full_path = supported_modules.get(client_script)
    if not client_script_full_path:
        raise ProcessGearmanJobError({
            'exitCode': -1,
            'stdOut': 'Error!',
            'stdError': 'Error! - Tried to run an unsupported command.'})
    replacement_dict['%date%'] = utc_date.isoformat()
    replacement_dict['%jobCreatedDate%'] = data['createdDate']
    # Replace replacement strings
    for var, val in replacement_dict.items():
        # TODO: this seems unneeded because the full path to the client
        # script can never contain '%date%' or '%jobCreatedDate%' and the
        # other possible vars have already been replaced.
        client_script_full_path = client_script_full_path.replace(var, val)
        arguments = arguments.replace(var, val)
    arguments = arguments.replace('%taskUUID%', task_uuid)
    script = client_script_full_path + ' ' + arguments
    return script, task_uuid


def _unexpected_error():
    logger.exception('Unexpected error')
    return cPickle.dumps({'exitCode': -1,
                          'stdOut': '',
                          'stdError': traceback.format_exc()})


class Job():
    def __init__(self, name, args):
        self.name = name
        self.args = [name] + args
        self.int_code = 0
        self.status_code = 'success'
        self.output = ""
        self.error = ""

    def dump(self):
        return (("#<TASK %s; EXIT: %d; CODE: %s\n" +
                "STDOUT: %s\n" +
                "STDERR: %s\n" +
                "\n>") % (self.name, self.int_code, self.status_code, self.output, self.error))

    def set_status(self, int_code, status_code='success'):
        if int_code:
            self.int_code = int_code
        self.status_code = status_code

    def write_output(self, s):
        self.output += s

    def write_error(self, s):
        self.error += s

    def get_exit_code(self):
        return self.int_code

    def get_stdout(self):
        return self.output

    def get_stderr(self):
        return self.error


def handle_batch_task(gearman_job, gearman_worker):
    module_name = batch_development.converted_modules.get(gearman_job.task)
    task_uuid = str(gearman_job.unique)

    gearman_data = cPickle.loads(gearman_job.data)
    arguments = gearman_data['arguments']
    if isinstance(arguments, unicode):
        arguments = arguments.encode('utf-8')

    utc_date = getUTCDate()
    replacements = (replacement_dict.items() + 
                    {'%date%': utc_date.isoformat(),
                     '%taskUUID%': task_uuid,
                     '%jobCreatedDate%': gearman_data['createdDate']}.items())

    for var, val in replacements:
        arguments = arguments.replace(var, val)

    job = Job(gearman_job.task, shlex.split(arguments))

    module = importlib.import_module("batchClientScripts." + module_name)
    reload(module)
    module.call([job])

    return job

class DevelopmentRollback(Exception):
    pass

def safe_execute_command(gearman_worker, gearman_job):
    try:
        return execute_command(gearman_worker, gearman_job)
    except Exception as e:
        print "COMPLETELY FAILED: %s" % (str(e))
        traceback.print_exc()
        raise e

def wait_for_next_round():
    loops = 0
    while True:
        loops += 1

        if os.path.isfile("/tmp/continue.txt"):
            os.remove("/tmp/continue.txt")
            break

        if (loops % 50) == 0:
            logger.info("\n\n*** Touch file /tmp/continue.txt to continue")
        time.sleep(0.1)


def execute_command(gearman_worker, gearman_job):
    """Execute the command encoded in ``gearman_job`` and return its exit code,
    standard output and standard error as a pickled dict.
    """
    logger.info("\n\n*** RUNNING TASK: %s" % (gearman_job.task))
    logger.info("\n\n*** CONVERTED MODULES: %s" % (batch_development.converted_modules))

    reload(batch_development)

    if gearman_job.task in batch_development.converted_modules:
        logger.info("\n\n*** Task %s is converted module!", gearman_job.task)
        while batch_development.converted_modules.get(gearman_job.task) in batch_development.modules_under_development:
            logger.info("\n\n*** RUNNING TASK %s in development mode", gearman_job.task)
            try:
                with transaction.atomic():
                    try:
                        job = handle_batch_task(gearman_job, gearman_worker)
                        logger.info("\n\n*** PRODUCED JOB: %s" % (job.dump()))
                        raise DevelopmentRollback()
                    except:
                        traceback.print_exc()
                        raise DevelopmentRollback()
            except DevelopmentRollback:
                wait_for_next_round()
                reload(batch_development)

        # Run the batch version of this task
        job = handle_batch_task(gearman_job, gearman_worker)

        return cPickle.dumps({'exitCode': job.get_exit_code(),
                              'stdOut': job.get_stdout(),
                              'stdError': job.get_stderr()})


    logger.info("\n\n*** TASK: %s has not been converted yet" % (gearman_job.task))
    try:
        script, task_uuid = _process_gearman_job(
            gearman_job, gearman_worker)
    except ProcessGearmanJobError:
        return cPickle.dumps({
            'exitCode': 1,
            'stdOut': 'Archivematica Client Process Gearman Job Error!',
            'stdError': traceback.format_exc()})
    except Exception:
        return _unexpected_error()
    logger.info('<processingCommand>{%s}%s</processingCommand>',
                task_uuid, script)
    try:
        exit_code, std_out, std_error = executeOrRun(
            'command', script, stdIn='',
            printing=django_settings.CAPTURE_CLIENT_SCRIPT_OUTPUT,
            capture_output=django_settings.CAPTURE_CLIENT_SCRIPT_OUTPUT)
    except OSError:
        logger.exception('Execution failed')
        return cPickle.dumps({'exitCode': 1,
                              'stdOut': 'Archivematica Client Error!',
                              'stdError': traceback.format_exc()})
    except Exception:
        return _unexpected_error()
    return cPickle.dumps({'exitCode': exit_code,
                          'stdOut': std_out,
                          'stdError': std_error})


def start_gearman_worker():
    """Setup a gearman client, for the thread."""
    gm_worker = gearman.GearmanWorker([django_settings.GEARMAN_SERVER])
    host_id = '{}_1'.format(gethostname())
    gm_worker.set_client_id(host_id)
    for client_script in supported_modules:
        gm_worker.register_task(client_script, safe_execute_command)
    fail_max_sleep = 30
    fail_sleep = 1
    fail_sleep_incrementor = 2
    while True:
        try:
            gm_worker.work()
        except gearman.errors.ServerUnavailable as inst:
            logger.error('Gearman server is unavailable: %s. Retrying in %d'
                         ' seconds.', inst.args, fail_sleep)
            time.sleep(fail_sleep)
            if fail_sleep < fail_max_sleep:
                fail_sleep += fail_sleep_incrementor

if __name__ == '__main__':
    try:
        load_supported_modules(django_settings.CLIENT_MODULES_FILE)
        start_gearman_worker()
    except (KeyboardInterrupt, SystemExit):
        logger.info('Received keyboard interrupt, quitting.')
