import json

from rest_framework import routers, viewsets, mixins, serializers, routers
from rest_framework.pagination import LimitOffsetPagination
from rest_framework.response import Response
from fpr.models import FormatVersion, FPTool, FPRule, Format, FormatGroup
from datetime import datetime

class ParMixin(object):

    def _parse_offset_and_limit(self, request):
        offset = request.GET.get('offset')
        limit = request.GET.get('limit')
        if offset != None and limit != None: limit = int(offset) + int(limit)
        return offset, limit

    # FIXME move to serializer
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


class FileFormatSerializer(serializers.Serializer):

    def _to_par_id(self, id, uuid):
        return {
            'guid': uuid,
            'name': id,
            }

    def to_representation(self, obj):
        return {
            'id': self._to_par_id(obj.pronom_id, obj.format.uuid),
            'localLastModifiedDate': str(obj.lastmodified),
            'version': obj.version,
            'name': obj.slug,
            'description': obj.description,
            'types': [obj.format.group.description],
            }

    def to_internal_value(self, data):
        # FIXME do this
        pass


class FileFormatsViewSet(ParMixin, mixins.ListModelMixin, mixins.RetrieveModelMixin, mixins.CreateModelMixin, viewsets.GenericViewSet):
    lookup_field = 'pronom_id'
    lookup_value_regex = '[a-z]+\/[0-9]+'
    serializer_class = serializers.Serializer
    queryset = FormatVersion.active
    pagination_class = LimitOffsetPagination

    def list(self, request):
        """
        offset         -- Offset of the first record to show
        limit          -- Limit the number of records to show
        modifiedAfter  -- Modified After (YYYY-MM-DD)
        modifiedBefore -- Modified Before (YYYY-MM-DD)
        """

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
            # LOGGER.error(err)
            print err
            return Response({'error': True, 'message': 'Server failed to handle the request.'}, 502)

        serializer = FileFormatSerializer(format_versions[offset:limit], many=True)
        return Response(serializer.data)


    def create(self, request):
        try:
            format_version = self._to_fpr_format_version(request.data)

            # See if a format already exists for this version
            format = Format.objects.filter(description=format_version['description']).first()

            if format == None:
                # We need to create a format
                group_name = request.data.get('types', [format_version['description']])[0]
                group = FormatGroup.objects.filter(description=group_name).first()
                if group == None:
                    # And a group ... sigh
                    # Note: The db says a format doesn't need a group, but the dashboard blows up if it doesn't have one
                    group = FormatGroup.objects.create(**self._to_fpr_format_group(group_name))

                format_hash = self._to_fpr_format(format_version['description'])
                format_hash['group_id'] = group.uuid
                format = Format.objects.create(**format_hash)

            format_version['format_id'] = format.uuid

            FormatVersion.objects.create(**format_version)
        except Exception as err:
            # LOGGER.error(err)
            print err
            return Response({'error': True, 'message': 'Server failed to handle the request.'}, 502)

        return Response({'message': 'File format successfully created.', 'uri': request.path + format_version['pronom_id']}, 201)

    def retrieve(self, request, pronom_id=None):
        try:
            format_version = FormatVersion.active.filter(pronom_id=pronom_id)[0]
            serializer = FileFormatSerializer(format_version)
            return Response(serializer.data)
        except FormatVersion.DoesNotExist:
            # FIXME doesn't hit this?
            return Response({'error': True, 'message': 'File format not found'}, 400)
        except IndexError:
            return Response({'error': True, 'message': 'File format not found'}, 400)


class ToolSerializer(serializers.Serializer):

    def to_representation(self, tool):
        return {
            'toolId': tool.slug,
            'toolVersion': tool.version,
            'toolName': tool.description,
            }

    def to_internal_value(self, data):
        toolName = data.get('toolName')
        toolVersion = data.get('toolVersion')


        if not toolName:
                    raise serializers.ValidationError({
                        'toolName': 'This field is required.'
                    })
        if not toolVersion:
                    raise serializers.ValidationError({
                        'toolVersion': 'This field is required.'
                    })


        return {
            'description': toolName,
            'version': toolVersion,
            }


class ToolsViewSet(ParMixin, mixins.ListModelMixin, mixins.RetrieveModelMixin, mixins.CreateModelMixin, viewsets.GenericViewSet):
    lookup_field = 'slug'
    lookup_value_regex = '.*' #FIXME
    serializer_class = ToolSerializer
    queryset = FPTool.objects
    pagination_class = LimitOffsetPagination

    def list(self, request):
        offset, limit = self._parse_offset_and_limit(request)

        try:
            tools = FPTool.objects.all()[offset:limit]
        except Exception as err:
            # LOGGER.error(err)
            print err
            return Response({'error': True, 'message': 'Server failed to handle the request.'}, 502)

        serializer = ToolSerializer(tools, many=True)
        return Response(serializer.data)

    def create(self, request):
        try:
            serializer = ToolSerializer(data=request.data)
            if (serializer.is_valid()):
                tool = self._to_fpr_tool(serializer.validated_data)
                created_tool = FPTool.objects.create(**tool)
            else:
                return Response({'error': True, 'message': 'Invalid POST', 'errors': serializer.errors}, 502)
        except Exception as err:
            # LOGGER.error(err)
            print err
            return Response({'error': True, 'message': 'Server failed to handle the request.'}, 502)

        return Response({'message': 'Tool successfully created.', 'uri': request.path + created_tool.slug}, 201)


    def retrieve(self, request, slug=None):
        try:
            tool = FPTool.objects.get(slug=slug)
        except FPTool.DoesNotExist:
            return Response({'error': True, 'message': 'Tool not found'}, 400)

        serializer = ToolSerializer(tool)
        return Response(serializer.data)


class PreservationActionTypeSerializer(serializers.Serializer):

    def _to_par_id(self, id, uuid):
        return {
            'guid': uuid,
            'name': id,
            }

    def to_representation(self, obj):
        type = obj['purpose']

        return {
            'id': self._to_par_id(type, type),
            'label': type,
            }


class PreservationActionTypesViewSet(ParMixin, mixins.ListModelMixin, viewsets.GenericViewSet):
    serializer_class = PreservationActionTypeSerializer
    queryset = FPRule.objects
    pagination_class = LimitOffsetPagination

    def list(self, request):
        try:
            rules = FPRule.objects.values('purpose').distinct()
        except Exception as err:
            # LOGGER.error(err)
            print err
            return Response({'error': True, 'message': 'Server failed to handle the request.'}, 502)

        serializer = PreservationActionTypeSerializer(rules, many=True)
        return Response(serializer.data)


class PreservationActionSerializer(serializers.Serializer):

    def _to_par_tool(self, tool):
        return {
            'toolId': tool.slug,
            'toolVersion': tool.version,
            'toolName': tool.description,
            }

    def _to_par_id(self, id, uuid):
        return {
            'guid': uuid,
            'name': id,
            }

    def _to_par_io_file(self, name):
        return {
            'type': 'File',
            'name': name,
            }

    def _to_par_preservation_action_type(self, type):
        return {
            'id': self._to_par_id(type, type),
            'label': type,
            }

    def to_representation(self, rule):
        return {
            'id': self._to_par_id(rule.uuid, rule.uuid),
            'description': rule.command.description,
            'type': self._to_par_preservation_action_type(rule.purpose),
            'inputs': [self._to_par_io_file(rule.format.description)],
            'outputs': [self._to_par_io_file(rule.command.output_format.description)],
            'tool': self._to_par_tool(rule.command.tool),
            }


class PreservationActionsViewSet(ParMixin, mixins.ListModelMixin, viewsets.GenericViewSet):
    serializer_class = PreservationActionSerializer
    queryset = FPRule.objects
    pagination_class = LimitOffsetPagination

    def list(self, request):
        offset, limit = self._parse_offset_and_limit(request)

        try:
            rules = FPRule.objects.all()[offset:limit]
        except Exception as err:
            # LOGGER.error(err)
            print err
            return Response({'error': True, 'message': 'Server failed to handle the request.'}, 502)

        serializer = PreservationActionSerializer(rules, many=True)
        return Response(serializer.data)
