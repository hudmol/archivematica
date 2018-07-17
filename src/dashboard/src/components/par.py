"""
PAR related gubbins
"""

def to_par_file_format(format_version):
    return {
        'id': format_version.pronom_id,
        'localLastModifiedDate': str(format_version.lastmodified),
        'version': format_version.version,
        'name': format_version.slug,
        'description': format_version.description,
        'families': [format_version.format.group.description],
        }

def to_fpr_format_version(file_format):
    return {
        'version': file_format.get('version'),
        'pronom_id': file_format.get('id'),
        'description': file_format.get('description'),
        }

def to_fpr_format_group(group):
    return {
        'description': group,
        }

def to_fpr_format(format):
    return {
        'description': format,
        }

def to_par_tool(tool):
    return {
        'toolId': tool.slug,
        'toolVersion': tool.version,
        'toolName': tool.description,
        }

def to_fpr_tool(tool):
    return {
        'description': tool.get('toolName'),
        'version': tool.get('toolVersion'),
        }
