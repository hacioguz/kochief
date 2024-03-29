# -*- coding: utf8 -*-

# Copyright 2008 Gabriel Sean Farrell
# Copyright 2008 Mark A. Matienzo
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

"""Helpers for MARC processing."""

import csv
import pymarc
import re
import sys
import time
import unicodedata
import urllib

from django.conf import settings
from django.contrib.sites.models import Site
from django.utils import simplejson

try:
    set
except NameError:
    from sets import Set as set

# local libs
import marc_maps

NONINT_RE = re.compile(r'\D')
ISBN_RE = re.compile(r'(\b\d{10}\b|\b\d{13}\b)')
UPC_RE = re.compile(r'\b\d{12}\b')
FIELDNAMES = [
    'audience',
    'author',
    'bib_num',
    'collection',
    'contents',
    'corporate_name',
    'ctrl_num',
    'description',
    'format',
    'full_title',
    'genre',
    'id',
    'imprint',
    'isbn',
    'language',
    'language_dubbed', 
    'language_subtitles',
    'oclc_num',
    'notes',
    'personal_name',
    'place',
    'publisher',
    'pubyear',
    'series',
    'summary',
    'title',
    'title_sort',
    'topic',
    'upc',
    'url',
]

class RowDict(dict):
    """
    Subclass of dict that joins sequences and encodes to utf-8 on get.
    Encoding to utf-8 is necessary for Python's csv library because it 
    can't handle unicode.
    >>> row = RowDict()
    >>> row['bob'] = ['Montalb\\xe2an, Ricardo', 'Roddenberry, Gene']
    >>> row.get('bob')
    'Montalb\\xc3\\xa1n, Ricardo|Roddenberry, Gene'
    >>> print row.get('bob')
    Montalbán, Ricardo|Roddenberry, Gene
    """
    def get(self, key, *args):
        value = dict.get(self, key, *args)
        if not value:
            return ''
        if hasattr(value, '__iter__'):
            value = '|'.join([x for x in value if x])
        # converting to utf8 with yaz-marcdump instead -- it handles
        # oddities better
        #return pymarc.marc8.marc8_to_unicode(value).encode('utf8')
        # convert to unicode if value is a string
        if type(value) == type(''):
            value = unicode(value, 'utf8')
        # converting to NFC form lessens character encoding issues 
        value = unicodedata.normalize('NFC', value)
        return value.encode('utf8')

def normalize(value):
    if value:
        return value.replace('.', '').strip(',:/; ')
  
def subfield_list(field, subfield_indicator):
    subfields = field.get_subfields(subfield_indicator)
    if subfields is not None:
        return [normalize(subfield) for subfield in subfields]
    else:
        return []

def multi_field_list(fields, indicators):
    values = []
    for f in fields:
        for i in indicators:
            values.extend(subfield_list(f, i))
    return set(values)

# Dragged over from Casey's processors.py.
def get_format(record):
    format = ''
    description = ''
    if record['007']:
        description = record['007'].value()
    leader = record.leader
    if len(leader) > 7:
        if len(description) > 5:
            if description[0] == 'c':            # electronic resource
                if description[1] == 'r':        # remote resource
                    if description[5] == 'a':    # has sound
                        format = 'eAudio'
                    else:
                        format = 'eBook'
                elif description[1] == 'o':      # optical disc
                    format = 'CD-ROM'
            elif description[0] == 's':          # sound recording
                if leader[6] == 'i':             # nonmusical sound recording
                    if description[1] == 's':   # sound cassette
                        format = 'Book On Cassette'
                    elif description[1] == 'd':    # sound disc
                        if description[6] == 'g' or description[6] == 'z':
                            # 4 3/4 inch or Other size
                            format = 'Book On CD'
                elif leader[6] == 'j':        # musical sound recording
                    if description[1] == 's':    # sound cassette
                        format = 'Cassette'
                    elif description[1] == 'd':    # sound disc
                        if description[6] == 'g' or description[6] == 'z':
                            # 4 3/4 inch or Other size
                            format = 'Music CD'
                        elif description[6] == 'e':   # 12 inch
                            format = 'Phono Record'
            elif description[0] == 'v':            # videorecording
                if description[1] == 'd':        # videodisc
                    format = 'DVD'
                elif description[1] == 'f':        # videocassette
                    format = 'Videocassette'
    # now do guesses that are NOT based upon physical description 
    # (physical description is going to be the most reliable indicator, 
    # when it exists...) 
    elif leader[6] == 'a':                # language material
        fixed = record['008'].value()
        if leader[7] == 'm':            # monograph
            if len(fixed) > 22:
                if fixed[23] == 'd':    # form of item = large print
                    format = 'Large Print Book'
                elif fixed[23] == 's':    # electronic resource
                    format = 'eBook'
                else:
                    format = 'Book'
            else:
                format = 'Book'
        elif leader[7] == 's':            # serial
            if len(fixed) > 18:
                frequencies = ['b', 'c', 'd', 'e', 'f', 'i', 'j', 
                        'm', 'q', 's', 't', 'w']
                if fixed[18] in frequencies:
                    format = 'Journal'
                else:
                    # this is here to prevent stuff that librarians 
                    # and nobody else would consider to be a serial 
                    # from being labeled as a magazine.
                    format = 'Book'
    elif leader[6] == 'e':
        format = 'Map'
    elif leader[6] == 'c':
        format = 'Musical Score'
    return format

def parse_008(record, marc_record):
    if marc_record['008']:
        field008 = marc_record['008'].value()

        # "a" added for noninteger search to work
        dates = (field008[7:11] + 'a', field008[11:15] + 'a')
        # test for which date is more precise based on searching for
        # first occurence of nonintegers, i.e. 196u > 19uu
        occur0 = NONINT_RE.search(dates[0]).start()
        occur1 = NONINT_RE.search(dates[1]).start()
        # if both are specific to the year, pick the earlier of the two
        if occur0 == 4 and occur1 == 4:
            date = min(dates[0], dates[1])
        else:
            if occur0 >= occur1:
                date = dates[0]
            else:
                date = dates[1]
        # don't use it if it starts with a noninteger
        if NONINT_RE.match(date):
            record['pubyear'] = ''
        else:
            # substitute all nonints with dashes, chop off "a"
            date = NONINT_RE.sub('-', date[:4])
            record['pubyear'] = date
            # maybe try it as a solr.DateField at some point
            #record['pubyear'] = '%s-01-01T00:00:01Z' % date
    
        audience_code = field008[22]
        if audience_code != ' ':
            try:
                record['audience'] = marc_maps.AUDIENCE_CODING_MAP[audience_code]
            except KeyError, error:
                #sys.stderr.write("\nIllegal audience code: %s\n" % error)
                record['audience'] = ''

        language_code = field008[35:38]
        try:
            record['language'] = marc_maps.LANGUAGE_CODING_MAP[language_code]
        except KeyError:
            record['language'] = ''
    return record

def id_match(id_fields, id_re):
    id_list = []
    for field in id_fields:
        id_str = normalize(field['a'])
        if id_str:
            id_match = id_re.match(id_str)
            if id_match:
                id = id_match.group()
                id_list.append(id)
    return id_list

def get_languages(language_codes):
    split_codes = []
    for code in language_codes:
        code = code.lower()
        if len(code) > 3:
            split_code = [code[k:k+3] for k in range(0, len(code), 3)]
            split_codes.extend(split_code)
        else:
            split_codes.append(code)
    languages = []
    for code in split_codes:
        try:
            language = marc_maps.LANGUAGE_CODING_MAP[code]
        except KeyError:
            language = None
        if language:
            languages.append(language)
    return set(languages)

# Roles with names (i.e. "Glover, Crispin (Actor)") looks neat but is
# kind of useless from a searching point of view.  A search for "Law,
# Jude (Actor)" won't return plain old "Law, Jude".  I welcome other
# ideas for incorporating roles.
#def extract_name(field):
#    role_map = maps.ROLE_CODING_MAP
#    name = normalize(field['a'])
#    if name:
#        role_key = field['4']
#        if role_key:
#            try:
#                name = '%s (%s)' % (name, role_map[role_key])
#            except KeyError:
#                pass
#    return name
        
def generate_records(data_handle):
    reader = pymarc.MARCReader(data_handle)
    for marc_record in reader:
        record = get_record(marc_record)
        if record:  # skip when get_record returns None
            yield record

def get_record(marc_record, ils=None):
    """
    Pulls the fields from a MARCReader record into a dictionary.
    >>> marc_file_handle = open('test/marc.dat')
    >>> reader = pymarc.MARCReader(marc_file_handle)
    >>> for marc_record in reader:
    ...     record = get_record(marc_record)
    ...     print record['author']
    ...     break
    ...
    George, Henry, 1839-1897.
    """
    record = {}

    # TODO: split ILS-specific into separate parsers that subclass this one:
    # horizonmarc, iiimarc, etc.
    try:
        if ils == 'Horizon':
            record['id'] = marc_record['999']['a']
        elif ils == 'III':
            # [1:-1] because that's how it's referred to in the opac
            record['id'] = marc_record['907']['a'][1:-1]
        elif ils == 'Unicorn':
            record['id'] = marc_record['35']['a']
        else:
            # Includes Aleph and Voyager.
            record['id'] = marc_record['001'].value()
    except AttributeError:
        # try other fields for id?
        #sys.stderr.write("\nNo value in ID field, leaving ID blank\n")
        #record['id'] = ''
        # if it has no id let's not include it
        return
    
    record['format'] = get_format(marc_record)

    # should ctrl_num default to 001 or 035?
    if marc_record['001']:
        record['ctrl_num'] = marc_record['001'].value() 

    # there should be a test here for the 001 to start with 'oc'
    try:
        oclc_number = marc_record['001'].value()
    except AttributeError:
        oclc_number = ''
    record['oclc_num'] = oclc_number

    record = parse_008(record, marc_record)

    isbn_fields = marc_record.get_fields('020')
    record['isbn'] = id_match(isbn_fields, ISBN_RE)
        
    upc_fields = marc_record.get_fields('024')
    record['upc'] = id_match(upc_fields, UPC_RE)

    if marc_record['041']:
        language_dubbed_codes = marc_record['041'].get_subfields('a')
        languages_dubbed = get_languages(language_dubbed_codes)
        record['language_dubbed'] = []
        for language in languages_dubbed:
            if language != record['language']:
                record['language_dubbed'].append(language)
        language_subtitles_codes = marc_record['041'].get_subfields('b')
        languages_subtitles = get_languages(language_subtitles_codes)
        if languages_subtitles:
            record['language_subtitles'] = languages_subtitles

    record['author'] = marc_record.author()

    # are there any subfields we don't want for the full_title?
    if marc_record['245']:
        full_title = marc_record['245'].format_field()
        try:
            nonfiling = int(marc_record['245'].indicator2)
        except ValueError:
            nonfiling = 0
        record['full_title'] = full_title
        title_sort = full_title[nonfiling:].strip()
        # good idea, but need to convert to unicode first
        #title_sort = unicodedata.normalize('NFKD', title_sort)
        record['title_sort'] = title_sort
        if marc_record.title() is not None:
            record['title'] = marc_record['245']['a'].strip(' /:;')
        else:
            record['title'] = full_title
    
    if marc_record['260']:
        record['imprint'] = marc_record['260'].format_field()
        record['publisher'] = normalize(marc_record['260']['b'])
        # grab date from 008
        #if marc_record['260']['c']:
        #    date_find = DATE_RE.search(marc_record['260']['c'])
        #    if date_find:
        #        record['date'] = date_find.group()

    description_fields = marc_record.get_fields('300')
    record['description'] = [field.value() for field in description_fields]
    
    series_fields = marc_record.get_fields('440', '490')
    record['series'] = multi_field_list(series_fields, 'a')

    notes_fields = marc_record.get_fields('500')
    record['notes'] = [field.value() for field in notes_fields]
    
    contents_fields = marc_record.get_fields('505')
    record['contents'] = multi_field_list(contents_fields, 'a')
    
    summary_fields = marc_record.get_fields('520')
    record['summary'] = [field.value() for field in summary_fields]
    
    subjname_fields = marc_record.get_fields('600')
    subjectnames = multi_field_list(subjname_fields, 'a')
    
    subjentity_fields = marc_record.get_fields('610')
    subjectentities = multi_field_list(subjentity_fields, 'ab')
    
    subject_fields = marc_record.subjects()  # gets all 65X fields

    genres = []
    topics = []
    places = []
    for field in subject_fields:
        genres.extend(subfield_list(field, 'v'))
        topics.extend(subfield_list(field, 'x'))
        places.extend(subfield_list(field, 'z'))
        if field.tag == '650':
            if field['a'] != 'Video recordings for the hearing impaired.':
                topics.append(normalize(field['a']))
        elif field.tag == '651':
            places.append(normalize(field['a']))
        elif field.tag == '655':
            if field['a'] != 'Video recordings for the hearing impaired.':
                genres.append(normalize(field['a']))
        #for subfield_indicator in ('a', 'v', 'x', 'y', 'z'):
        #    more_topics = subfield_list(subfield_indicator)
        #    topics.extend(more_topics)
    record['genre'] = set(genres)
    record['topic'] = set(topics)
    record['place'] = set(places)

    personal_name_fields = marc_record.get_fields('700')
    record['personal_name'] = []
    for field in personal_name_fields:
        subfields = field.get_subfields('a', 'b', 'c', 'd')
        personal_name = ' '.join([x.strip() for x in subfields])
        record['personal_name'].append(personal_name)

    corporate_name_fields = marc_record.get_fields('710')
    record['corporate_name'] = []
    for field in corporate_name_fields:
        subfields = field.get_subfields('a', 'b')
        corporate_name = ' '.join([x.strip() for x in subfields])
        record['corporate_name'].append(corporate_name)

    url_fields = marc_record.get_fields('856')
    record['url'] = multi_field_list(url_fields, 'u')

    return record

def get_row(record):
    """Converts record dict to row for CSV input."""
    row = RowDict(record)
    return row

def write_csv(marc_file_handle, csv_file_handle, collections=None, 
        ils=settings.ILS):
    """
    Convert a MARC dump file to a CSV file.
    """
    # This doctest commented out until field names are stable.
    #>>> write_csv('test/marc.dat', 'test/records.csv')
    #>>> csv_records = open('test/records.csv').read()
    #>>> csv_measure = open('test/measure.csv').read()
    #>>> csv_records == csv_measure
    #True
    #>>> os.remove('test/records.csv')

    # TODO: move xml parsing to marcxml parser
    #if in_xml:
    #    reader = pymarc.marcxml.parse_xml_to_array(marc_file_handle)
    #else:
    reader = pymarc.MARCReader(marc_file_handle)
    fieldname_dict = {}
    for fieldname in FIELDNAMES:
        fieldname_dict[fieldname] = fieldname
    #for record in reader
    count = 0
    try:
        writer = csv.DictWriter(csv_file_handle, FIELDNAMES)
        writer.writerow(fieldname_dict)
        for marc_record in reader:
            count += 1
            try:
                record = get_record(marc_record, ils=ils)
                if record:  # skip when get_record returns None
                    if collections:
                        new_collections = []
                        old_record = get_old_record(record['id'])
                        if old_record:
                            old_collections = old_record.get('collection')
                            if old_collections:
                                new_collections.extend(old_collections)
                        new_collections.extend(collections)
                        try:
                            record['collection'].extend(new_collections)
                        except (AttributeError, KeyError):
                            record['collection'] = new_collections
                    row = get_row(record)
                    writer.writerow(row)
            except:
                if marc_record.title() is not None:
                    title = marc_record.title()
                else:
                    title = marc_record['245'].format_field()
                sys.stderr.write("\nError in MARC record #%s (%s):\n" % 
                        (count, title.encode('ascii', 'ignore')))
                raise
            else:
                if count % 1000:
                    sys.stderr.write(".")
                else:
                    sys.stderr.write(str(count))
    finally:
        marc_file_handle.close()
        csv_file_handle.close()
    sys.stderr.write("\nProcessed %s records.\n" % count)
    return count

def get_old_record(id):
    id_query = 'id:%s' % id
    params = [
        ('fq', id_query.encode('utf8')),
        ('q.alt', '*:*'),
        ('qt', 'dismax'),
        ('wt', 'json'),
    ]
    urlparams = urllib.urlencode(params)
    url = '%sselect?%s' % (settings.SOLR_URL, urlparams)
    try:
        solr_response = urllib.urlopen(url)
    except IOError:
        raise IOError, 'Unable to connect to the Solr instance.'
    try:
        response = simplejson.load(solr_response)
    except ValueError, e:
        print urllib.urlopen(url).read()
        raise ValueError, 'Solr response was not a valid JSON object.'
    try:
        doc = response['response']['docs'][0]
    except IndexError:
        doc = None
    return doc

