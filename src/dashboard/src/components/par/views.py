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

# stdlib, alphabetical
import base64
import json
import shutil
import logging
import os
import uuid
import re

# Core Django, alphabetical
from django.db.models import Q
import django.http
from django.conf import settings as django_settings

# External dependencies, alphabetical
from tastypie.authentication import ApiKeyAuthentication, MultiAuthentication, SessionAuthentication

# This project, alphabetical
import archivematicaFunctions
from contrib.mcp.client import MCPClient
from components.filesystem_ajax import views as filesystem_ajax_views
from components.unit import views as unit_views
from components import helpers
from main import models
from processing import install_builtin_config
from components.api.views import _api_endpoint

# PAR related
#from rest_framework_swagger.views import get_swagger_view
from components.par import par
from fpr.models import Format, FormatGroup, FormatVersion, FPTool, FPRule
from datetime import datetime

LOGGER = logging.getLogger('archivematica.dashboard')
SHARED_DIRECTORY_ROOT = django_settings.SHARED_DIRECTORY
UUID_REGEX = re.compile(r'^[0-9A-F]{8}-[0-9A-F]{4}-4[0-9A-F]{3}-[89AB][0-9A-F]{3}-[0-9A-F]{12}$', re.IGNORECASE)


@_api_endpoint(expected_methods=['GET'])
def par_format(request, pronom_id):
    """
    GET an fpr.FormatVersion by pronom_id and return it as a PAR format object

    Example: http://127.0.0.1:62080/api/beta/par/fileFormats/fmt/30?username=test&api_key=test
    """

    try:
        format_version = FormatVersion.active.filter(pronom_id=pronom_id)[0]
    except FormatVersion.DoesNotExist:
        return helpers.json_response({'error': True, 'message': 'File format not found'}, 400)

    return helpers.json_response(par.to_par_file_format(format_version))


@_api_endpoint(expected_methods=['GET', 'POST'])
def par_formats(request):
    """
    POST a PAR format object to create an fpr.FormatVersion ... and possibly an fpr.Format and fpr.FormatGroup

    FIXME: Some tricky logic in the mapping has been largely fudged so far

    Example:
      http://127.0.0.1:62080/api/beta/par/fileFormats?username=test&api_key=test
        {"id": "fmt/jjj", "description": "111 Happy Street", "types": ["Audio"]}

    or

    GET a list of fpr.FormatVersions as PAR format objects

    Accepts modifiedBefore and modifiedAfter filters as 'YYYY-MM-DD'
    Also accepts offset and limit to return a subset of fileFormats
    FIXME: the current state of the spec asks for time and timezone support too so might have to add that later

    Examples:
      All:
        http://127.0.0.1:62080/api/beta/par/fileFormats?username=test&api_key=test
      Modified after 2010-01-01:
        http://127.0.0.1:62080/api/beta/par/fileFormats?username=test&api_key=test&modifiedAfter=2010-01-01
      Modified after 2010-01-01 and before 2010-06-30:
        http://127.0.0.1:62080/api/beta/par/fileFormats?username=test&api_key=test&modifiedAfter=2010-01-01&modifiedBefore=2010-06-30
      Paginated:
        http://127.0.0.1:62080/api/beta/par/fileFormats?username=test&api_key=test&modifiedAfter=2010-01-01&offset=100&limit=20
    """

    if request.method == 'POST':
        try:
            payload = json.loads(request.body)
            format_version = par.to_fpr_format_version(payload)

            # See if a format already exists for this version
            format = Format.objects.filter(description=format_version['description']).first()

            if format == None:
                # We need to create a format
                group_name = payload.get('types', [format_version['description']])[0]
                group = FormatGroup.objects.filter(description=group_name).first()
                if group == None:
                    # And a group ... sigh
                    # Note: The db says a format doesn't need a group, but the dashboard blows up if it doesn't have one
                    group = FormatGroup.objects.create(par.to_fpr_format_group(group_name))

                format_hash = par.to_fpr_format(format_version['description'])
                format_hash['group_id'] = group.uuid
                format = Format.objects.create(**format_hash)

            format_version['format_id'] = format.uuid

            FormatVersion.objects.create(**format_version)
        except Exception as err:
            LOGGER.error(err)
            return helpers.json_response({'error': True, 'message': 'Server failed to handle the request.'}, 502)

        return helpers.json_response({'message': 'File format successfully created.', 'uri': request.path + '/' + format_version['pronom_id']}, 201)


    after = request.GET.get('modifiedAfter')
    before = request.GET.get('modifiedBefore')

    offset, limit = par.parse_offset_and_limit(request)

    try:
        format_versions = FormatVersion.active
        if after != None:
            format_versions = format_versions.filter(lastmodified__gte=datetime.strptime(after, '%Y-%m-%d'))

        if before != None:
            format_versions = format_versions.filter(lastmodified__lte=datetime.strptime(before, '%Y-%m-%d'))

        if after == None and before == None:
            format_versions = format_versions.all()

    except Exception as err:
        LOGGER.error(err)
        return helpers.json_response({'error': True, 'message': 'Server failed to handle the request.'}, 502)

    return helpers.json_response([par.to_par_file_format(fv) for fv in format_versions[offset:limit]])


@_api_endpoint(expected_methods=['GET'])
def par_tool(request, slug):
    """
    GET an fpr.tool by slug and return it as a PAR tool object

    Example: http://127.0.0.1:62080/api/beta/par/tools/jhove-16?username=test&api_key=test
    """

    try:
        tool = FPTool.objects.get(slug=slug)
    except FPTool.DoesNotExist:
        return helpers.json_response({'error': True, 'message': 'Tool not found'}, 400)

    return helpers.json_response(par.to_par_tool(tool))


@_api_endpoint(expected_methods=['GET', 'POST'])
def par_tools(request):
    """
    POST a PAR tool object to create an fpr.FPTool

    Example:
      http://127.0.0.1:62080/api/beta/par/tools?username=test&api_key=test
        {"toolName": "md5sum", "toolVersion": "8.13"}

    or

    GET a list of fpr.FPTools as PAR tool objects

    Accepts offset and limit to select a subset of tools

    Examples:
      http://127.0.0.1:62080/api/beta/par/tools?username=test&api_key=test
      http://127.0.0.1:62080/api/beta/par/tools?username=test&api_key=test&offset=10&limit=10
      http://127.0.0.1:62080/api/beta/par/tools?username=test&api_key=test&offset=100
      http://127.0.0.1:62080/api/beta/par/tools?username=test&api_key=test&limit=20
    """

    if request.method == 'POST':
        try:
            tool = par.to_fpr_tool(json.loads(request.body))

            created_tool = FPTool.objects.create(**tool)
        except Exception as err:
            LOGGER.error(err)
            return helpers.json_response({'error': True, 'message': 'Server failed to handle the request.'}, 502)

        return helpers.json_response({'message': 'Tool successfully created.', 'uri': request.path + '/' + created_tool.slug}, 201)


    offset, limit = par.parse_offset_and_limit(request)

    try:
        tools = FPTool.objects.all()[offset:limit]
    except Exception as err:
        LOGGER.error(err)
        return helpers.json_response({'error': True, 'message': 'Server failed to handle the request.'}, 502)

    return helpers.json_response([par.to_par_tool(fpt) for fpt in tools])


@_api_endpoint(expected_methods=['GET'])
def par_preservation_action_types(request):
    """
    GET a list of distinct fpr.FPRule.purpose values as PAR preservation_action_type objects

    Examples:
      http://127.0.0.1:62080/api/beta/par/preservation_action_types?username=test&api_key=test
    """

    try:
        rules = FPRule.objects.values('purpose').distinct()
    except Exception as err:
        LOGGER.error(err)
        return helpers.json_response({'error': True, 'message': 'Server failed to handle the request.'}, 502)

    return helpers.json_response([par.to_par_preservation_action_type(rule['purpose']) for rule in rules])


@_api_endpoint(expected_methods=['GET'])
def par_preservation_actions(request):
    """
    GET a list of fpr.FPRules as PAR preservation_action objects

    Accepts offset and limit to select a subset of preservation_actions

    Examples:
      http://127.0.0.1:62080/api/beta/par/preservation_actions?username=test&api_key=test
      http://127.0.0.1:62080/api/beta/par/preservation_actions?username=test&api_key=test&offset=10&limit=10
      http://127.0.0.1:62080/api/beta/par/preservation_actions?username=test&api_key=test&offset=100
      http://127.0.0.1:62080/api/beta/par/preservation_actions?username=test&api_key=test&limit=20
    """

    offset, limit = par.parse_offset_and_limit(request)

    try:
        rules = FPRule.objects.all()[offset:limit]
    except Exception as err:
        LOGGER.error(err)
        return helpers.json_response({'error': True, 'message': 'Server failed to handle the request.'}, 502)

    return helpers.json_response([par.to_par_preservation_action(fprule) for fprule in rules])
