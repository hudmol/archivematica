import logging

from contextlib import contextmanager
import ctypes
import io
import os, sys
import tempfile

libc = ctypes.CDLL(None)
c_stdout = ctypes.c_void_p.in_dll(libc, 'stdout')


@contextmanager
def capture_stdout_stderr(output):
    original_stdout_fd = sys.stdout.fileno()
    original_stderr_fd = sys.stderr.fileno()

    # Save a copy of the original streams to be restored in a moment.
    saved_stdout = sys.stdout
    saved_stdout_fd = os.dup(original_stdout_fd)
    saved_stderr = sys.stderr
    saved_stderr_fd = os.dup(original_stderr_fd)

    # Create temporary files that will hold redirected output
    stdout_tempfile = tempfile.TemporaryFile(mode='w+b')
    stderr_tempfile = tempfile.TemporaryFile(mode='w+b')

    # Close stdout and redirect it to our tempfile.  Since stdout is usually
    # buffered, flush it before closing.
    libc.fflush(c_stdout)
    libc.close(original_stdout_fd)
    ### sys.stdout.close()
    os.dup2(stdout_tempfile.fileno(), original_stdout_fd)
    sys.stdout = os.fdopen(original_stdout_fd, 'wb')

    # Close stderr and redirect it to our tempfile.
    libc.close(original_stderr_fd)
    ### sys.stderr.close()
    os.dup2(stderr_tempfile.fileno(), original_stderr_fd)
    sys.stderr = os.fdopen(original_stderr_fd, 'wb')

    try:
        yield
    finally:
        # Restore stdout to its original setting.
        libc.fflush(c_stdout)
        sys.stdout.close()
        os.dup2(saved_stdout_fd, original_stdout_fd)
        ## sys.stdout = os.fdopen(original_stdout_fd, 'wb')
        sys.stdout = saved_stdout

        # Restore stderr to its original setting.
        sys.stderr.close()
        os.dup2(saved_stderr_fd, original_stderr_fd)
        ## sys.stderr = os.fdopen(original_stderr_fd, 'wb')
        sys.stderr = saved_stderr

        # Rewind our tempfiles and make their output available
        stdout_tempfile.flush()
        stdout_tempfile.seek(0, io.SEEK_SET)

        stderr_tempfile.flush()
        stderr_tempfile.seek(0, io.SEEK_SET)

        output['stdout'] = stdout_tempfile
        output['stderr'] = stderr_tempfile
