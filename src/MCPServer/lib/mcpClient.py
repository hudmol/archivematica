#!/usr/bin/env python2

# This file is part of Archivematica.
#
# Copyright 2010-2013 Artefactual Systems Inc. <http://artefactual.com>
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
# @subpackage MCPServer

# Interface for sending jobs to the MCP Client (via gearman)

# FIXME: Very prototypey right now.  Better design to follow!

import threading
import gearman
import cPickle
import logging
import time
import traceback
import os

from multiprocessing.pool import ThreadPool

import databaseFunctions
from django.conf import settings as django_settings
from django.utils import timezone
from django.db import transaction
from fileOperations import writeToFile

LOGGER = logging.getLogger('archivematica.mcp.server')

class TaskRunner():
    pending_jobs = []
    running_jobs = []
    tasks_by_uuid = {}
    task_groups_by_subtask_uuid = {}
    completion_count_by_task_group = {}
    finish_callback_by_task_group = {}

    # Used to run completed callbacks off the main thread
    pool = ThreadPool(20)

    last_finished_jobs_flush = 0
    finished_job_write_frequency_seconds = 0.0

    pending_jobs_lock = threading.Lock()

    @staticmethod
    def finish_task_group(finishedTaskGroup):
        try:
            callback = TaskRunner.finish_callback_by_task_group.pop(finishedTaskGroup.UUID)
            callback(finishedTaskGroup)
        except Exception as e:
            print "ERROR CALLING FINISH TASK: " + str(e)
            traceback.print_exc()
            raise e

    @staticmethod
    def submit(task, finishedCallback):
        print "submit: Waiting for jobs lock..."
        with TaskRunner.pending_jobs_lock:
            print "submit: Got it!"
            # FIXME: hack using tuples here.  Just to get things going
            TaskRunner.pending_jobs.append((task, finishedCallback))

    @staticmethod
    def check_jobs(gm_client, loopcount):
        pending_jobs = []

        with TaskRunner.pending_jobs_lock:
            pending_jobs = list(TaskRunner.pending_jobs)
            TaskRunner.pending_jobs = []

        # Run any jobs that are ready to go
        for (runnableTaskGroup, finishedCallback) in pending_jobs:
            print "Got a new job to run"

            TaskRunner.completion_count_by_task_group[runnableTaskGroup.UUID] = 0
            TaskRunner.finish_callback_by_task_group[runnableTaskGroup.UUID] = finishedCallback

            print "Subtask count: %d" % (len(runnableTaskGroup.subtasks()))

            for subtask in runnableTaskGroup.subtasks():
                print "Subtask: %s" % (subtask)
                data = {"createdDate": timezone.now().isoformat(' ')}
                data["arguments"] = subtask.arguments

                job_request = None

                while job_request == None:
                    try:
                        job_request = gm_client.submit_job(
                            task=runnableTaskGroup.execute.lower(),
                            data=cPickle.dumps(data),
                            unique=subtask.UUID,
                            wait_until_complete=False,
                            background=False,
                            max_retries=10)
                    except Exception as e:
                        print "Retrying submit for job %s...: %s: %s" % (task.UUID, str(e), str(type(e)))
                        time.sleep(0.05)

                print "Registering subtask: %s for job: %s" % (subtask.UUID, runnableTaskGroup.execute.lower())
                TaskRunner.tasks_by_uuid[subtask.UUID] = subtask
                TaskRunner.task_groups_by_subtask_uuid[subtask.UUID] = runnableTaskGroup
                TaskRunner.running_jobs.append(job_request)

        # Check in on our existing jobs
        statuses = []
        for job in TaskRunner.running_jobs:
            try:
                status = gm_client.get_job_status(job)
                statuses.append(status)
            except KeyError:
                print "Oops!  Got a weird KeyError"
                # There seems to be a race condition here... if the
                # COMPLETED message comes in before RES_STATUS, KeyError is
                # thrown.
                statuses.append(job)

        finished_jobs = [job for job in statuses if job.complete]
        still_running_jobs = [job for job in statuses if not job.complete]

        # Log all task outputs
        with transaction.atomic():
            for finished_job in finished_jobs:
                subtask = TaskRunner.tasks_by_uuid[finished_job.gearman_job.unique]
                TaskRunner.log_task_output(subtask, finished_job)

        # FIXME: we'll move this code into MCP Client anyway.
        for finished_job in finished_jobs:
            print "REMOVING subtask: %s" % (finished_job.gearman_job.unique)
            subtask = TaskRunner.tasks_by_uuid.pop(finished_job.gearman_job.unique)
            thisTaskGroup = TaskRunner.task_groups_by_subtask_uuid.pop(subtask.UUID)

            TaskRunner.completion_count_by_task_group[thisTaskGroup.UUID] += 1

            if TaskRunner.completion_count_by_task_group[thisTaskGroup.UUID] == len(thisTaskGroup.subtasks()):
                del TaskRunner.completion_count_by_task_group[thisTaskGroup.UUID]

                # The entire group is finished
                TaskRunner.pool.apply_async(TaskRunner.finish_task_group, [thisTaskGroup])

        if loopcount % 50 == 0:
            print "Running tasks: %s" % (still_running_jobs)

        TaskRunner.running_jobs = still_running_jobs

    # FIXME: Temporary... will end up elsewhere.
    @staticmethod
    def log_task_output(subtask, job_request):
        if job_request.complete:
            subtask.results = cPickle.loads(job_request.result)
            LOGGER.debug('Task %s finished! Result %s - %s', job_request.job.unique, job_request.state, subtask.results)
            TaskRunner.writeOutputs(subtask)
        elif job_request.timed_out:
            LOGGER.error('Task %s timed out!', job_request.unique)
            subtask.results['exitCode'] = -1
            subtask.results["stdError"] = "Task %s timed out!" % job_request.unique
        elif job_request.state == gearman.client.JOB_UNKNOWN:
            LOGGER.error('Task %s connection failed!', job_request.unique)
            subtask.results["stdError"] = "Task %s connection failed!" % job_request.unique
            subtask.results['exitCode'] = -1
        else:
            LOGGER.error('Task %s failed!', job_request.unique)
            subtask.results["stdError"] = "Task %s failed!" % job_request.unique
            subtask.results['exitCode'] = -1

    # FIXME: Temporary... will end up elsewhere.
    @staticmethod
    def outputFileIsWritable(fileName):
        """
        Validates whether a given file is writeable or, if the file does not exist, whether its parent directory is writeable.
        """
        if os.path.exists(fileName):
            target = fileName
        else:
            target = os.path.dirname(fileName)
        return os.access(target, os.W_OK)

    # FIXME: Temporary... will end up elsewhere.
    @staticmethod
    def validateOutputFile(fileName):
        """
        Returns True if the given file is writeable.
        If the passed file is not None and isn't writeable, logs the filename.
        """
        if fileName is None:
            return False

        if not TaskRunner.outputFileIsWritable(fileName):
            LOGGER.warning('Unable to write to file %s', fileName)
            return False

        return True

    # FIXME: Temporary... will end up elsewhere.
    # Used to write the output of the commands to the specified files
    @staticmethod
    def writeOutputs(subtask):
        """Used to write the output of the commands to the specified files"""

        if subtask.outputLock is not None:
            subtask.outputLock.acquire()

        if TaskRunner.validateOutputFile(subtask.standardOutputFile):
            stdoutStatus = writeToFile(subtask.results["stdOut"], subtask.standardOutputFile)
        else:
            stdoutStatus = -1
        if TaskRunner.validateOutputFile(subtask.standardErrorFile):
            stderrStatus = writeToFile(subtask.results["stdError"], subtask.standardErrorFile)
        else:
            stderrStatus = -1

        if subtask.outputLock is not None:
            subtask.outputLock.release()

        if stdoutStatus and subtask.standardOutputFile is not None:
            if isinstance(subtask.standardOutputFile, unicode):
                stdout = subtask.standardOutputFile.encode('utf-8')
            else:
                stdout = subtask.standardOutputFile
            subtask.stdError = "Failed to write to file{" + stdout + "}\r\n" + subtask.results["stdOut"]
        if stderrStatus and subtask.standardErrorFile is not None:
            if isinstance(subtask.standardErrorFile, unicode):
                stderr = subtask.standardErrorFile.encode('utf-8')
            else:
                stderr = subtask.standardErrorFile
            subtask.stdError = "Failed to write to file{" + stderr + "}\r\n" + subtask.results["stdError"]
        if subtask.results['exitCode']:
            return subtask.results['exitCode']
        return stdoutStatus + stderrStatus

    @staticmethod
    def poll_jobs():
        gm_client = gearman.GearmanClient([django_settings.GEARMAN_SERVER])
        loopcount = 0

        while True:
            loopcount += 1
            try:
                time.sleep(0.2)
                TaskRunner.check_jobs(gm_client, loopcount)
            except Exception as e:
                print "Error in poll_jobs: " + str(e) + ": " + str(type(e))
                traceback.print_exc()

t = threading.Thread(target=TaskRunner.poll_jobs)
t.start()

def runTaskGroup(runnableTaskGroup, finishedCallback):
    TaskRunner.submit(runnableTaskGroup, finishedCallback)

