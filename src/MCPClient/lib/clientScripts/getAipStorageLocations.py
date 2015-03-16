#!/usr/bin/python2 -OO

import logging
import sys

# archivematicaCommon
from custom_handlers import GroupWriteRotatingFileHandler
import storageService as storage_service


def get_aip_storage_locations(purpose):
    """ Return a dict of AIP Storage Locations and their descriptions."""
    storage_directories = storage_service.get_location(purpose=purpose)
    logging.debug("Storage Directories: {}".format(storage_directories))
    choices = {}
    for storage_dir in storage_directories:
        choices[storage_dir['description']] = storage_dir['resource_uri']
    print choices


if __name__ == '__main__':
    logger = logging.getLogger("archivematica")
    logger.addHandler(GroupWriteRotatingFileHandler("/var/log/archivematica/MCPClient/getAipStorageLocations.log", maxBytes=4194304))
    logger.setLevel(logging.INFO)

    try:
        purpose = sys.argv[1]
    except IndexError:
        purpose = "AS"
    get_aip_storage_locations(purpose)
