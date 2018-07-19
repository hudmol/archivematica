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

from django.conf.urls import url, include
from django.conf import settings

from rest_framework import routers, viewsets, mixins

from components.par import views
from components.par import rest


router = routers.SimpleRouter()
router.register(r'fileFormats', rest.FileFormatsViewSet, base_name='fileFormats')
router.register(r'tools', rest.ToolsViewSet, base_name='tools')
router.register(r'preservation_action_types', rest.PreservationActionTypesViewSet, base_name='preservation_action_types')
router.register(r'preservation_actions', rest.PreservationActionsViewSet, base_name='preservation_actions')

urlpatterns = [
    url(r'docs/', include('rest_framework_swagger.urls')),
    # url(r'fileFormats/?$', views.par_formats),
    # url(r'fileFormats/(?P<pronom_id>.+)', views.par_format),
    # url(r'tools/?$', views.par_tools),
    # url(r'tools/(?P<slug>.+)', views.par_tool),
    # url(r'preservation_action_types/?$', views.par_preservation_action_types),
    # url(r'preservation_actions/?$', views.par_preservation_actions),
]

urlpatterns += router.urls