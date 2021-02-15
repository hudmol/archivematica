#!/usr/bin/env python2

import argparse
import logging
import os
import re
from shutil import copyfile

from main.models import ArchivesSpaceDIPObjectResourcePairing, File
from fpr.models import FormatVersion

# archivematicaCommon
from xml2obj import mets_file

# Third party dependencies, alphabetical by import source
from agentarchives.archivesspace import ArchivesSpaceClient
from agentarchives.archivesspace import ArchivesSpaceError

# initialize Django (required for Django 1.7)
import django
import scandir

django.setup()
from django.db import transaction

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
logger.addHandler(logging.NullHandler())
logger.addHandler(logging.FileHandler("/tmp/as_upload.log", mode="a"))


def recursive_file_gen(mydir):
    for root, dirs, files in scandir.walk(mydir):
        for file in files:
            yield os.path.join(root, file)


def get_files_from_dip(dip_location):
    # need to find files in objects dir of dip:
    # go to dipLocation/objects
    # get a directory listing
    # for each item, set fileName and go
    try:
        # remove trailing slash
        if dip_location != os.path.sep:
            dip_location = dip_location.rstrip(os.path.sep)
        mydir = os.path.join(dip_location, "objects")
        mylist = list(recursive_file_gen(mydir))

        if len(mylist) > 0:
            return mylist
        else:
            logger.error("no files in " + mydir)
            raise ValueError("cannot find dip")
    except Exception:
        raise


def get_pairs(dip_uuid):
    return {
        pair.fileuuid: pair.resourceid
        for pair in ArchivesSpaceDIPObjectResourcePairing.objects.filter(
            dipuuid=dip_uuid
        )
    }


def delete_pairs(dip_uuid):
    ArchivesSpaceDIPObjectResourcePairing.objects.filter(dipuuid=dip_uuid).delete()



def get_parser(RESTRICTIONS_CHOICES, EAD_ACTUATE_CHOICES, EAD_SHOW_CHOICES):
    parser = argparse.ArgumentParser(
        description="A program to take digital objects from a DIP and upload them to an ArchivesSpace db"
    )
    parser.add_argument(
        "--base-url",
        default="http://localhost:8089",
        dest="base_url",
        metavar="base_url",
        help="Hostname of ArchivesSpace",
    )
    parser.add_argument("--user", dest="user", help="Administrative user")
    parser.add_argument("--passwd", dest="passwd", help="Administrative user password")
    parser.add_argument("--dip_location", help="DIP location")
    parser.add_argument("--dip_name", help="DIP name")
    parser.add_argument("--dip_uuid", help="DIP UUID")
    parser.add_argument(
        "--restrictions",
        help="Restrictions apply",
        default="premis",
        choices=RESTRICTIONS_CHOICES,
    )
    parser.add_argument("--object_type", help="object type", default="")
    parser.add_argument(
        "--xlink_actuate",
        help="XLink actuate",
        default="onRequest",
        choices=EAD_ACTUATE_CHOICES,
    )
    parser.add_argument(
        "--xlink_show", help="XLink show", default="new", choices=EAD_SHOW_CHOICES
    )
    parser.add_argument("--use_statement", help="USE statement")
    parser.add_argument("--uri_prefix", help="URI prefix")
    parser.add_argument(
        "--access_conditions", help="Conditions governing access", default=""
    )
    parser.add_argument("--use_conditions", help="Conditions governing use", default="")
    parser.add_argument(
        "--inherit_notes",
        help="Inherit digital object notes from the parent component",
        default="no",
        type=str,
    )
    parser.add_argument("--version", action="version", version="%(prog)s 0.1.0")
    return parser


def call(jobs):
    RESTRICTIONS_CHOICES = ["yes", "no", "premis"]
    EAD_SHOW_CHOICES = ["embed", "new", "none", "other", "replace"]
    EAD_ACTUATE_CHOICES = ["none", "onLoad", "other", "onRequest"]
    INHERIT_NOTES_CHOICES = ["yes", "y", "true", "1"]

    parser = get_parser(RESTRICTIONS_CHOICES, EAD_ACTUATE_CHOICES, EAD_SHOW_CHOICES)

    with transaction.atomic():
        for job in jobs:
            with job.JobContext(logger=logger):
                args = parser.parse_args(job.args[1:])

                args.inherit_notes = args.inherit_notes.lower() in INHERIT_NOTES_CHOICES

                try:
                    files = get_files_from_dip(args.dip_location)
                except ValueError:
                    job.set_status(2)
                    continue
                except Exception:
                    job.set_status(3)
                    continue

                for file_path in files:
                    file_name = re.sub('^.*/objects/', '', file_path)
                    target_path = os.path.join('/var/archivematica/sharedDirectory/www/DIPsStore/', 'QSADIPs', args.dip_uuid, file_name)

                    print "Copying DIP file %s to %s" % (file_path, target_path)

                    try:
                        os.makedirs(os.path.dirname(target_path))
                    except:
                        pass

                    copyfile(file_path, target_path)

                job.set_status(0)