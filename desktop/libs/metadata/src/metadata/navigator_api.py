#!/usr/bin/env python
# Licensed to Cloudera, Inc. under one
# or more contributor license agreements.  See the NOTICE file
# distributed with this work for additional information
# regarding copyright ownership.  Cloudera, Inc. licenses this file
# to you under the Apache License, Version 2.0 (the
# "License"); you may not use this file except in compliance
# with the License.  You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import json
import logging

try:
  from collections import OrderedDict
except ImportError:
  from ordereddict import OrderedDict # Python 2.6

from django.http import Http404
from django.utils.translation import ugettext as _
from django.views.decorators.http import require_POST

from desktop.lib.django_util import JsonResponse
from desktop.lib.i18n import force_unicode

from metadata.conf import has_navigator
from metadata.navigator_client import NavigatorApi


LOG = logging.getLogger(__name__)


class MetadataApiException(Exception):
  pass


def error_handler(view_fn):
  def decorator(*args, **kwargs):
    try:
      if has_navigator(args[0].user):
        return view_fn(*args, **kwargs)
      else:
        raise MetadataApiException('Navigator API is not configured.')
    except Http404, e:
      raise e
    except Exception, e:
      status = 500
      message = str(e)
      LOG.exception(message)

      if 'Could not find' in message:
        status = 200

      response = {
        'status': -1,
        'message': force_unicode(message)
      }
    return JsonResponse(response, status=status)
  return decorator


@error_handler
def search_entities(request):
  """
  For displaying results.
  """
  api = NavigatorApi()

  query_s = request.POST.get('query_s', '')
  offset = request.POST.get('offset', 0)
  limit = request.POST.get('limit', 100)
  sources = json.loads(request.POST.get('sources')) or []

  query_s = query_s.strip() or '*'

  entities = api.search_entities(query_s, limit=limit, offset=offset, sources=sources)

  response = {
    'entities': entities,
    'count': len(entities),
    'offset': offset,
    'limit': limit,
    'query_s': query_s,
    'status': 0
  }

  return JsonResponse(response)


@error_handler
def search_entities_interactive(request):
  """
  For search autocomplete.
  """
  api = NavigatorApi()

  query_s = request.POST.get('query_s', '')
  prefix = request.POST.get('prefix')
  offset = request.POST.get('offset', 0)
  limit = request.POST.get('limit', 25)
  field_facets = json.loads(request.POST.get('field_facets') or '[]')
  sources = json.loads(request.POST.get('sources') or '[]')


  f = {
      "outputFormat" : {
        "type" : "dynamic"
      },
      "name" : {
        "type" : "dynamic"
      },
      "lastModified" : {
        "type" : "date"
      },
      "sourceType" : {
        "type" : "dynamic"
      },
      "parentPath" : {
        "type" : "dynamic"
      },
      "deleteTime" : {
        "type" : "date"
      },
      "lastAccessed" : {
        "type" : "date"
      },
      "type" : {
        "type" : "dynamic"
      },
      "sourceId" : {
        "type" : "dynamic"
      },
      "partitionColNames" : {
        "type" : "dynamic"
      },
      "serDeName" : {
        "type" : "dynamic"
      },
      "created" : {
        "type" : "date"
      },
      "fileSystemPath" : {
        "type" : "dynamic"
      },
      "compressed" : {
        "type" : "bool"
      },
      "clusteredByColNames" : {
        "type" : "dynamic"
      },
      "deleted" : {
        "type" : "bool"
      },
      "originalName" : {
        "type" : "dynamic"
      },
      "owner" : {
        "type" : "dynamic"
      },
      "extractorRunId" : {
        "type" : "dynamic"
      },
      "userEntity" : {
        "type" : "bool"
      },
      "sortByColNames" : {
        "type" : "dynamic"
      },
      "inputFormat" : {
        "type" : "dynamic"
      },
      "serDeLibName" : {
        "type" : "dynamic"
      },
      "originalDescription" : {
        "type" : "dynamic"
      },
      "lastModifiedBy" : {
        "type" : "dynamic"
      }
    }

  field_facets = ["tags", "type"] + f.keys()

  last_query_term = [term for term in query_s.strip().split()][-1]

  if last_query_term and last_query_term != '*':
    last_query_term = last_query_term.rstrip('*')
    (fname, fval) = last_query_term.split(':') if ':' in last_query_term else (last_query_term, '')
    field_facets = [f for f in field_facets if f.startswith(fname)]
  field_facets = field_facets[:10]

  response = api.search_entities_interactive(
      query_s=query_s,
      limit=limit,
      offset=offset,
      facetFields=field_facets,
      facetPrefix=prefix,
      facetRanges=None,
      firstClassEntitiesOnly=None,
      sources=sources
  )

  if response.get('facets'): # Remove empty facets
    for fname, fvalues in response['facets'].items():
      fvalues = sorted([(k, v) for k, v in fvalues.items() if v > 0], key=lambda n: n[1], reverse=True)
      response['facets'][fname] = OrderedDict(fvalues)
      if ':' in last_query_term and not response['facets'][fname]:
        del response['facets'][fname]

  response['status'] = 0

  return JsonResponse(response)


@error_handler
def list_tags(request):
  api = NavigatorApi()

  prefix = request.POST.get('prefix')
  offset = request.POST.get('offset', 0)
  limit = request.POST.get('limit', 25)

  data = api.search_entities_interactive(facetFields=['tags'], facetPrefix=prefix, limit=limit, offset=offset)

  response = {
    'tags': data['facets']['tags'],
    'status': 0
  }

  return JsonResponse(response)


@error_handler
def find_entity(request):
  response = {'status': -1}

  api = NavigatorApi()
  entity_type = request.GET.get('type', '')
  database = request.GET.get('database', '')
  table = request.GET.get('table', '')
  name = request.GET.get('name', '')
  path = request.GET.get('path', '')

  # TODO: support arbitrary optional filter params

  if not entity_type:
    raise MetadataApiException("find_entity requires a type value, e.g. - 'database', 'table', 'file'")

  if entity_type.lower() == 'database':
    if not name:
      raise MetadataApiException('get_database requires name param')
    response['entity'] = api.get_database(name)
  elif entity_type.lower() == 'table':
    if not database or not name:
      raise MetadataApiException('get_table requires database and name param')
    response['entity'] = api.get_table(database, name)
  elif entity_type.lower() == 'field':
    if not database or not table or not name:
      raise MetadataApiException('get_field requires database, table, and name params')
    response['entity'] = api.get_field(database, table, name)
  elif entity_type.lower() == 'directory':
    if not path:
      raise MetadataApiException('get_directory requires path param')
    response['entity'] = api.get_directory(path)
  elif entity_type.lower() == 'file':
    if not path:
      raise MetadataApiException('get_file requires path param')
    response['entity'] = api.get_file(path)
  else:
    raise MetadataApiException("type %s is unrecognized" % entity_type)

  # Prevent nulls later
  if 'tags' in response['entity'] and not response['entity']['tags']:
    response['entity']['tags'] = []

  response['status'] = 0
  return JsonResponse(response)


@error_handler
def suggest(request):
  response = {'status': -1}

  api = NavigatorApi()
  prefix = request.POST.get('prefix')

  suggest = api.suggest(prefix)

  response['suggest'] = suggest
  response['status'] = 0

  return JsonResponse(response)


@error_handler
def get_entity(request):
  response = {'status': -1}

  api = NavigatorApi()
  entity_id = request.REQUEST.get('id')

  if not entity_id:
    raise MetadataApiException("get_entity requires an 'id' parameter")

  entity = api.get_entity(entity_id)

  response['entity'] = entity
  response['status'] = 0

  return JsonResponse(response)


@require_POST
@error_handler
def add_tags(request):
  response = {'status': -1}

  api = NavigatorApi()
  entity_id = json.loads(request.POST.get('id', ''))
  tags = json.loads(request.POST.get('tags', []))

  if not entity_id or not tags or not isinstance(tags, list):
    response['error'] = _("add_tags requires an 'id' parameter and 'tags' parameter that is a non-empty list of tags")
  else:
    response['entity'] = api.add_tags(entity_id, tags)
    response['status'] = 0

  return JsonResponse(response)


@require_POST
@error_handler
def delete_tags(request):
  response = {'status': -1}

  api = NavigatorApi()
  entity_id = json.loads(request.POST.get('id', ''))
  tags = json.loads(request.POST.get('tags', []))

  if not entity_id or not tags or not isinstance(tags, list):
    response['error'] = _("add_tags requires an 'id' parameter and 'tags' parameter that is a non-empty list of tags")
  else:
    response['entity'] = api.delete_tags(entity_id, tags)
    response['status'] = 0

  return JsonResponse(response)


@require_POST
@error_handler
def update_properties(request):
  response = {'status': -1}

  api = NavigatorApi()
  entity_id = json.loads(request.POST.get('id', ''))
  properties = json.loads(request.POST.get('properties', {}))

  if not entity_id or not properties or not isinstance(properties, dict):
    response['error'] = _("update_properties requires an 'id' parameter and 'properties' parameter that is a non-empty dict")
  else:
    response['entity'] = api.update_properties(entity_id, properties)
    response['status'] = 0

  return JsonResponse(response)


@require_POST
@error_handler
def delete_properties(request):
  response = {'status': -1}

  api = NavigatorApi()
  entity_id = json.loads(request.POST.get('id', ''))
  keys = json.loads(request.POST.get('keys', []))

  if not entity_id or not keys or not isinstance(keys, list):
    response['error'] = _("update_properties requires an 'id' parameter and 'keys' parameter that is a non-empty list")
  else:
    response['entity'] = api.delete_properties(entity_id, keys)
    response['status'] = 0

  return JsonResponse(response)


@error_handler
def get_lineage(request):
  response = {'status': -1, 'inputs': [], 'source_query': '', 'target_queries': [], 'targets': []}

  api = NavigatorApi()
  entity_id = request.REQUEST.get('id')

  if not entity_id:
    raise MetadataApiException("get_lineage requires an 'id' parameter")

  lineage = api.get_lineage(entity_id)
  entity_name = api.get_entity(entity_id)['originalName'].upper()

  response['id'] = entity_id

  # TODO: This is a cheat way to do to this for demo using filtering but we should really traverse relationships
  parent_operation = next((entity for entity in lineage['entities'] if entity.get('outputs', []) == [entity_name]), None)
  if parent_operation:
    response['inputs'] = [input.lower() for input in parent_operation['inputs']]
    response['source_query'] = parent_operation.get('queryText', '')

  children = [entity for entity in lineage['entities'] if entity.get('inputs') is not None and entity_name in entity.get('inputs')]
  if children is not None:
    response['target_queries'] = [child['queryText'] for child in children if child.get('queryText') is not None]
    outputs = [child['outputs'] for child in children if child.get('outputs') is not None]
    response['targets'] = [target.lower() for output in outputs for target in output]

  response['status'] = 0

  return JsonResponse(response)
