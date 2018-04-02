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

import threading
import databaseFunctions
import uuid

from django.db import transaction

class taskGroup():
    """A group of tasks to hand to gearman"""

    def __init__(self, linkTaskManager, execute):
        self.linkTaskManager = linkTaskManager
        self.execute = execute.encode("utf-8")
        self.UUID = str(uuid.uuid4())

        self.tasks = []
        self.tasksLock = threading.Lock()


    def addTask(self,
                arguments, standardOutputFile, standardErrorFile,
                outputLock=None,
                UUID=None,
                commandReplacementDic={}):
        with self.tasksLock:
            self.tasks.append(self.taskGroupTask(arguments,
                                                 standardOutputFile, standardErrorFile,
                                                 outputLock,
                                                 commandReplacementDic))

    def count(self):
        with self.tasksLock:
            return len(self.tasks)

    def subtasks(self):
        return self.tasks

    def logTaskCreatedSQL(self):
        with self.tasksLock:
            with transaction.atomic():
                for task in self.tasks:
                    databaseFunctions.logTaskCreatedSQL(self.linkTaskManager,
                                                        task.commandReplacementDic,
                                                        task.UUID,
                                                        task.arguments)


    def logTaskCompletedSQL(self):
        with self.tasksLock:
            with transaction.atomic():
                for task in self.tasks:
                    databaseFunctions.logTaskCompletedSQL(task)

    def calculateExitCode(self):
        result = 0

        for task in self.tasks:
            if task.results['exitCode'] > result:
                result = task.results['exitCode']

        return result

    class taskGroupTask():
        def __init__(self,
                     arguments,
                     standardOutputFile, standardErrorFile,
                     outputLock,
                     commandReplacementDic):
            self.arguments = arguments
            self.standardOutputFile, = standardOutputFile,
            self.standardErrorFile = standardErrorFile
            self.outputLock = outputLock
            self.UUID = str(uuid.uuid4())
            self.commandReplacementDic = commandReplacementDic

            # NOTE: Preserve compatibility with databaseFunctions.logTaskCompletedSQL (for now)
            self.results = {'exitCode': 0,
                            'stdOut': '',
                            'stdError': ''}
