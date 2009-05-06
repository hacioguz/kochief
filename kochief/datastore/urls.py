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

from django.conf.urls.defaults import *

urlpatterns = patterns('kochief.datastore.views',
    url(r'^resource/(.*)\.rdf$', 'resource_view', {'format': 'xml'}, 
        name='datastore-resource-rdf'),
    url(r'^resource/(.*)\.n3$', 'resource_view', {'format': 'n3'}, 
        name='datastore-resource-n3'),
    url(r'^resource/(.*)\.nt$', 'resource_view', {'format': 'nt'}, 
        name='datastore-resource-nt'),
    url(r'^resource/(.*)$', 'resource_view', name='datastore-resource'),
)