# -*- coding: utf8 -*-
"""Tests for the archivematicaClamscan.py client script."""

from __future__ import print_function

import os
import subprocess
import sys

import pytest

THIS_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.append(os.path.abspath(os.path.join(THIS_DIR, '../lib/clientScripts')))

import archivematicaClamscan

# ClamScanner tests

@pytest.mark.parametrize("version, want", [
    (
        "ClamAV 0.99.2/23992/Fri Oct 27 05:04:12 2017",
        ("ClamAV 0.99.2", "23992/Fri Oct 27 05:04:12 2017")
    ),
    (
        "ClamAV 0.99.2",
        ("ClamAV 0.99.2", None)
    ),
    (
        "Unexpected value",
        (None, None)
    ),
])
def test_clamav_version_parts(version, want):
    got = archivematicaClamscan.clamav_version_parts(version)
    assert got == want

def setup_clamscanner():
    return archivematicaClamscan.ClamScanner()


def test_clamscanner_version_props(mocker):
    scanner = setup_clamscanner()
    mocker.patch.object(
        scanner, 'version_attrs',
        return_value=("ClamAV 0.99.2", "23992/Fri Oct 27 05:04:12 2017"))

    assert scanner.program() == "ClamAV (clamscan)"
    assert scanner.version() == "ClamAV 0.99.2"
    assert scanner.virus_definitions() == "23992/Fri Oct 27 05:04:12 2017"


def test_clamscanner_version_attrs(mocker, settings):
    scanner = setup_clamscanner()
    mock = mocker.patch.object(
        scanner, '_call',
        return_value="ClamAV 0.99.2/23992/Fri Oct 27 05:04:12 2017")

    assert scanner.version_attrs() == (
        "ClamAV 0.99.2",
        "23992/Fri Oct 27 05:04:12 2017",
    )
    mock.assert_called_once_with('-V')


def test_clamscanner_scan(mocker):
    scanner = setup_clamscanner()
    mock = mocker.patch.object(
        scanner, '_call',
        return_value='Output of clamscan')

    assert scanner.scan('/file') == (True, 'OK', None)
    mock.assert_called_once_with('/file')

    mock.side_effect = \
        subprocess.CalledProcessError(1, 'clamscan', 'Output of clamscan')
    assert scanner.scan('/file') == (False, 'FOUND', None)

    mock.side_effect = \
        subprocess.CalledProcessError(2, 'clamscan', 'Output of clamscan')
    assert scanner.scan('/file') == (False, 'ERROR', None)


