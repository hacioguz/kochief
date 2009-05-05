# Copyright 2009 Gabriel Farrell
#
# This file is part of Kochief.
# 
# Kochief is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
# 
# Kochief is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
# 
# You should have received a copy of the GNU General Public License
# along with Kochief.  If not, see <http://www.gnu.org/licenses/>.

import rdflib
from rdflib import plugin
from rdflib.store import Store
from rdflib.Graph import ConjunctiveGraph as Graph

from django.contrib import admin
from django.contrib.auth.models import User
from django.db import models
from django.utils import simplejson

from kochief import settings

DB_MAP = {
    'sqlite3': 'SQLite',
}

default_graph_uri = settings.BASE_URL + 'triplestore'

store = plugin.get(DB_MAP[settings.DATABASE_ENGINE], 
        Store)(settings.DATABASE_NAME)
rt = store.open('', create=False)
graph = Graph(store, identifier = rdflib.URIRef(default_graph_uri))

# TODO: replace with local namespace
rdflibns = rdflib.Namespace('http://rdflib.net/test/')

# TODO: timestamps for triples

class Record(object):
    def __init__(self, subject=None, field_list=None):
        ''' 
        field_list is a list of tuples, each corresponding to a field
        in the record.
        '''
        self.subject = subject
        if field_list:
            self.fields = field_list
        else:
            self.fields = []
        self.existing = self._get_existing_triples()
        for row in self.existing:
            self.fields.append((unicode(row[1]), unicode(row[2])))
            for field in field_list:
                self.fields.append(field)

    def _get_existing_triples(self):
        return graph.query(
            'SELECT ?s ?p ?o WHERE {rdflibns:%s ?p ?o.}' % self.subject, 
            initNs={'rdflibns': rdflib.Namespace('http://rdflib.net/test/')})

    def save(self):
        # find intersection of self.fields and self.existing
        # remove self.existing not in intersection
        # add self.fields not in intersection
        for field in self.fields:
            graph.add((rdflibns[self.subject], rdflibns[field[0]],
                rdflib.Literal(field[1])))
        graph.commit()
    
    def delete(self):
        pass


#class Record(models.Model):
#    def __unicode__(self):
#        return unicode(self.id)
#
#    def get_current(self):
#        return self.get_versions()[0]
#
#    def get_versions(self):
#        return self.version_set.order_by('-id')
#
#class Version(models.Model):
#    record = models.ForeignKey(Record)
#    data = models.TextField()
#    timestamp = models.DateTimeField(auto_now_add=True)
#    message = models.CharField(max_length=256)
#    committer = models.ForeignKey(User)
#
#    class Meta:
#        ordering = ['-timestamp']
#
#    def __unicode__(self):
#        return self.message
#
#    def get_data(self):
#        return simplejson.loads(self.data)
#
#class VersionInline(admin.TabularInline):
#    model = Version
#    extra = 1
#
#class RecordAdmin(admin.ModelAdmin):
#    inlines = [VersionInline]
#
#admin.site.register(Record, RecordAdmin)
#admin.site.register(Version)
