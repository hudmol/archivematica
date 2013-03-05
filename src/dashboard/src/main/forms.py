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

from django import forms
from django.forms import ModelForm
from django.forms.models import modelformset_factory
from django.forms.widgets import TextInput, Textarea, CheckboxInput, HiddenInput
from main import models

TEXTAREA_ATTRS = {'rows': '4', 'class': 'span11'}
TEXTAREA_WITH_HELP_ATTRS = {'rows': '4', 'class': 'span11 has_contextual_help'}
INPUT_ATTRS = {'class': 'span11'}
INPUT_WITH_HELP_ATTRS = {'class': 'span11 has_contextual_help'}

class DublinCoreMetadataForm(forms.Form):
    title = forms.CharField(required=False, widget=TextInput(attrs=INPUT_WITH_HELP_ATTRS))
    creator = forms.CharField(required=False, widget=TextInput(attrs=INPUT_WITH_HELP_ATTRS))
    subject = forms.CharField(required=False, widget=TextInput(attrs=INPUT_WITH_HELP_ATTRS))
    description = forms.CharField(required=False, widget=Textarea(attrs=TEXTAREA_WITH_HELP_ATTRS))
    publisher = forms.CharField(required=False, widget=TextInput(attrs=INPUT_WITH_HELP_ATTRS))
    contributor = forms.CharField(required=False, widget=TextInput(attrs=INPUT_WITH_HELP_ATTRS))
    date = forms.CharField(required=False, help_text='Use ISO 8061 (YYYY-MM-DD or YYYY-MM-DD/YYYY-MM-DD)', widget=TextInput(attrs=INPUT_WITH_HELP_ATTRS))
    type = forms.CharField(required=False, widget=TextInput(attrs=INPUT_ATTRS))
    format = forms.CharField(required=False, widget=TextInput(attrs=INPUT_WITH_HELP_ATTRS))
    identifier = forms.CharField(required=False, widget=TextInput(attrs=INPUT_WITH_HELP_ATTRS))
    source = forms.CharField(required=False, widget=TextInput(attrs=INPUT_WITH_HELP_ATTRS))
    relation = forms.CharField(required=False, label='Relation', widget=TextInput(attrs=INPUT_WITH_HELP_ATTRS))
    language = forms.CharField(required=False, help_text='Use ISO 3166', widget=TextInput(attrs=INPUT_WITH_HELP_ATTRS))
    coverage = forms.CharField(required=False, widget=TextInput(attrs=INPUT_WITH_HELP_ATTRS))
    rights = forms.CharField(required=False, widget=Textarea(attrs=TEXTAREA_WITH_HELP_ATTRS))

class AdministrationForm(forms.Form):
    arguments = forms.CharField(required=False, widget=Textarea(attrs=TEXTAREA_ATTRS))

class AgentForm(ModelForm):
    identifiervalue = forms.CharField(required=True, widget=TextInput(attrs=INPUT_ATTRS))
    name = forms.CharField(required=True, widget=TextInput(attrs=INPUT_ATTRS))

    class Meta:
        model = models.Agent
        exclude = ('identifiertype')

class MicroServiceChoiceReplacementDicForm(ModelForm):
    class Meta:
        model = models.MicroServiceChoiceReplacementDic
        exclude = (
            'id', )
        widgets = {
            'description': TextInput(attrs=INPUT_ATTRS),
            'replacementdic': Textarea(attrs=TEXTAREA_ATTRS),
            'choiceavailableatlink': HiddenInput
        }
