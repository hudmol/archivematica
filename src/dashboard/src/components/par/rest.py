from rest_framework import routers, viewsets, mixins, serializers, routers
from rest_framework.response import Response
from fpr.models import FormatVersion, FPTool, FPRule


class ParMixin(object):

    def _parse_offset_and_limit(self, request):
        offset = request.GET.get('offset')
        limit = request.GET.get('limit')
        if offset != None and limit != None: limit = int(offset) + int(limit)
        return offset, limit

    def _to_par_id(self, id, uuid):
        return {
            'guid': uuid,
            'name': id,
            }

    def _to_par_file_format(self, format_version):
        return {
            'id': self._to_par_id(format_version.pronom_id, format_version.format.uuid),
            'localLastModifiedDate': str(format_version.lastmodified),
            'version': format_version.version,
            'name': format_version.slug,
            'description': format_version.description,
            'types': [format_version.format.group.description],
            }

    def _to_fpr_format_version(self, file_format):
        return {
            'version': file_format.get('version'),
            'pronom_id': file_format.get('id'),
            'description': file_format.get('description'),
            }

    def _to_fpr_format_group(self, group):
        return {
            'description': group,
            }

    def _to_fpr_format(self, format):
        return {
            'description': format,
            }

    def _to_par_tool(self, tool):
        return {
            'toolId': tool.slug,
            'toolVersion': tool.version,
            'toolName': tool.description,
            }

    def _to_fpr_tool(self, tool):
        return {
            'description': tool.get('toolName'),
            'version': tool.get('toolVersion'),
            }

    def _to_par_preservation_action_type(self, type):
        return {
            'id': self._to_par_id(type, type),
            'label': type,
            }

    def _to_par_io_file(self, name):
        return {
            'type': 'File',
            'name': name,
            }

    def _to_par_preservation_action(self, rule):
        return {
            'id': self._to_par_id(rule.uuid, rule.uuid),
            'description': rule.command.description,
            'type': self._to_par_preservation_action_type(rule.purpose),
            'inputs': [self._to_par_io_file(rule.format.description)],
            'outputs': [self._to_par_io_file(rule.command.output_format.description)],
            'tool': self._to_par_tool(rule.command.tool),
            }


# class FileFormatSerializer(serializers.BaseSerializer):
#     def _to_par_id(self, id, uuid):
#         return {
#             'guid': uuid,
#             'name': id,
#             }
#
#     def to_representation(self, obj):
#         return {
#             'id': self._to_par_id(obj.pronom_id, obj.format.uuid),
#             'localLastModifiedDate': str(obj.lastmodified),
#             'version': obj.version,
#             'name': obj.slug,
#             'description': obj.description,
#             'types': [obj.format.group.description],
#             }


class FileFormatsViewSet(ParMixin, mixins.ListModelMixin, mixins.RetrieveModelMixin, mixins.CreateModelMixin, viewsets.GenericViewSet):
    lookup_field = 'pronom_id'
    lookup_value_regex = '[a-z]+\/[0-9]+'
    serializer_class = serializers.Serializer
    queryset = FormatVersion.active

    def list(self, request):
        after = request.GET.get('modifiedAfter')
        before = request.GET.get('modifiedBefore')

        offset, limit = self._parse_offset_and_limit(request)

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
            return Response({'error': True, 'message': 'Server failed to handle the request.'}, 502)

        return Response([self._to_par_file_format(fv) for fv in format_versions[offset:limit]])


    def create(self, request):
        try:
            payload = json.loads(request.body)
            format_version = self._to_fpr_format_version(payload)

            # See if a format already exists for this version
            format = Format.objects.filter(description=format_version['description']).first()

            if format == None:
                # We need to create a format
                group_name = payload.get('types', [format_version['description']])[0]
                group = FormatGroup.objects.filter(description=group_name).first()
                if group == None:
                    # And a group ... sigh
                    # Note: The db says a format doesn't need a group, but the dashboard blows up if it doesn't have one
                    group = FormatGroup.objects.create(self._to_fpr_format_group(group_name))

                format_hash = self._to_fpr_format(format_version['description'])
                format_hash['group_id'] = group.uuid
                format = Format.objects.create(**format_hash)

            format_version['format_id'] = format.uuid

            FormatVersion.objects.create(**format_version)
        except Exception as err:
            LOGGER.error(err)
            return Response({'error': True, 'message': 'Server failed to handle the request.'}, 502)

        return Response({'message': 'File format successfully created.', 'uri': request.path + '/' + format_version['pronom_id']}, 201)

    def retrieve(self, request, pronom_id=None):
        try:
            format_version = FormatVersion.active.filter(pronom_id=pronom_id)[0]
            return Response(self._to_par_file_format(format_version))
        except FormatVersion.DoesNotExist:
            # FIXME doesn't hit this?
            return Response({'error': True, 'message': 'File format not found'}, 400)
        except IndexError:
            return Response({'error': True, 'message': 'File format not found'}, 400)


class ToolsViewSet(ParMixin, mixins.ListModelMixin, mixins.RetrieveModelMixin, mixins.CreateModelMixin, viewsets.GenericViewSet):
    lookup_field = 'slug'
    lookup_value_regex = '.*' #FIXME
    serializer_class = serializers.Serializer
    queryset = FPTool.objects

    def list(self, request):
        offset, limit = self._parse_offset_and_limit(request)

        try:
            tools = FPTool.objects.all()[offset:limit]
        except Exception as err:
            LOGGER.error(err)
            return Response({'error': True, 'message': 'Server failed to handle the request.'}, 502)

        return Response([self._to_par_tool(fpt) for fpt in tools])


    def create(self, request):
        try:
            tool = self._to_fpr_tool(json.loads(request.body))

            created_tool = FPTool.objects.create(**tool)
        except Exception as err:
            LOGGER.error(err)
            return Response({'error': True, 'message': 'Server failed to handle the request.'}, 502)

        return Response({'message': 'Tool successfully created.', 'uri': request.path + '/' + created_tool.slug}, 201)


    def retrieve(self, request, slug=None):
        try:
            tool = FPTool.objects.get(slug=slug)
        except FPTool.DoesNotExist:
            return Response({'error': True, 'message': 'Tool not found'}, 400)

        return Response(self._to_par_tool(tool))


class PreservationActionTypesViewSet(ParMixin, mixins.ListModelMixin, viewsets.GenericViewSet):
    serializer_class = serializers.Serializer
    queryset = FPRule.objects

    def list(self, request):
        try:
            rules = FPRule.objects.values('purpose').distinct()
        except Exception as err:
            LOGGER.error(err)
            return Response({'error': True, 'message': 'Server failed to handle the request.'}, 502)

        return Response([self._to_par_preservation_action_type(rule['purpose']) for rule in rules])


class PreservationActionsViewSet(ParMixin, mixins.ListModelMixin, viewsets.GenericViewSet):
    serializer_class = serializers.Serializer
    queryset = FPRule.objects

    def list(self, request):
        offset, limit = self._parse_offset_and_limit(request)

        try:
            rules = FPRule.objects.all()[offset:limit]
        except Exception as err:
            LOGGER.error(err)
            return Response({'error': True, 'message': 'Server failed to handle the request.'}, 502)

        return Response([self._to_par_preservation_action(fprule) for fprule in rules])

