import capture_output
import logging
import runpy
import sys
import os

logger = logging.getLogger('archivematica.mcp.client')

# Thrown when a subtask calls sys.exit()
class SubTaskExited(Exception):
    def __init__(self, status):
        self.status = status

# Replacement for sys.exit() that throws our exception
def no_exit(status=None):
    if status == None:
        status = 0

    if not isinstance(status, int):
        sys.stderr.write(str(status) + "\n")
        status = 1

    raise SubTaskExited(status)

# If the subtask exits, throw an exception to force it to abort
sys.exit = no_exit

# THINKME: Need to setup django at this point?  And prevent subcalls?

# FIXME: not doing anything with sInput yet.
def run(command, sInput):
    # Gets filled in by capture_stdout_stderr.  Bit of an akward API...
    output_streams = {}

    if not '/src/MCPClient/lib/clientScripts/' in sys.path:
        sys.path.insert(0, '/src/MCPClient/lib/clientScripts/')

    if sInput != "":
        log.info("***** DEBUG WARNING: ****** command %s using stdin str: %s" % (command, sInput))

    status = 0
    orig_argv = sys.argv
    sys.argv = command

    try:
        with capture_output.capture_stdout_stderr(output_streams):
            try:
                runpy.run_path(command[0], run_name='__main__')
            except SubTaskExited as e:
                status = e.status
    finally:
        sys.argv = orig_argv

    stdout = ""
    stderr = ""

    if output_streams['stdout']:
        stdout = output_streams['stdout'].read()
        output_streams['stdout'].close()

    if output_streams['stderr']:
        stderr = output_streams['stderr'].read()
        output_streams['stderr'].close()

    return (status, stdout, stderr)
