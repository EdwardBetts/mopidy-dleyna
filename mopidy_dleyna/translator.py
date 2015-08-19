from __future__ import absolute_import, unicode_literals

from os.path import basename as basepath  # FIXME: server path?

from mopidy import models

from uritools import uriencode, urijoin

ALBUM_TYPE = 'container.album.musicAlbum'

ARTIST_TYPE = 'container.person.musicArtist'

_QUERYMAP = {
    'any': lambda caps: (
        ' or '.join(s + ' {0} "{1}"' for s in caps & {
            'DisplayName', 'Album', 'Artist', 'Genre', 'Creator'
        })
    ),
    'album': lambda caps: (
        'Album {0} "{1}"' if 'Album' in caps else None
    ),
    'artist': lambda caps: (
        ' or '.join(s + ' {0} "{1}"' for s in caps & {'Artist', 'Creator'})
    ),
    'date': lambda caps: (
        'Date = "{1}"' if 'Date' in caps else None  # TODO: inexact?
    ),
    'genre': lambda caps: (
        'Genre {0} "{1}"' if 'Genre' in caps else None
    ),
    'track_name': lambda caps: (
        ('DisplayName {0} "{1}" and Type = "music"'
         if 'DisplayName' in caps and 'Type' in caps else None)
    ),
    'track_no': lambda caps: (
        'TrackNumber = "{1}"' if 'TrackNumber' in caps else None
    )
}


def _quote(s):
    return unicode(s).replace('\\', '\\\\').replace('"', '\\"')


def _album(baseuri, obj):
    if 'Album' not in obj:
        return None
    if 'Parent' in obj:
        baseuri += b'/' + basepath(obj['Parent'])
    name = obj['Album']
    images = [obj['AlbumArtURL']] if 'AlbumArtURL' in obj else None
    uri = baseuri + b'?' + uriencode('Album = "%s"' % _quote(name))
    return models.Album(images=images, name=name, uri=uri)


def _artists(baseuri, obj):
    artists = []
    if 'Parent' in obj:
        baseuri += b'/' + basepath(obj['Parent'])
    for name in filter(None, obj.get('Artists', [obj.get('Creator')])):
        uri = baseuri + b'?' + uriencode('Artist = "%s"' % _quote(name))
        artists.append(models.Artist(name=name, uri=uri))
    return artists


def ref(baseuri, obj):
    uri = urijoin(baseuri, basepath(obj.get('RefPath', obj['Path'])))
    name = obj['DisplayName']
    type = obj.get('TypeEx', obj['Type'])
    if type == 'music' or type == 'audio':
        return models.Ref.track(name=name, uri=uri)
    elif type == ALBUM_TYPE:
        return models.Ref.album(name=name, uri=uri)
    elif type == ARTIST_TYPE:
        return models.Ref.artist(name=name, uri=uri)
    elif type.startswith('container'):
        return models.Ref.directory(name=name, uri=uri)
    else:
        raise ValueError('Unsupported object type "%s"', type)


def album(baseuri, obj):
    return models.Album(
        artists=_artists(baseuri, obj),
        name=obj['DisplayName'],
        num_tracks=obj.get('ItemCount', obj.get('ChildCount')),
        uri=urijoin(baseuri, basepath(obj.get('RefPath', obj['Path'])))
    )


def artist(baseuri, obj):
    return models.Artist(
        name=obj['DisplayName'],
        uri=urijoin(baseuri, basepath(obj.get('RefPath', obj['Path'])))
    )


def track(baseuri, obj):
    return models.Track(
        album=_album(baseuri, obj),
        artists=_artists(baseuri, obj),
        date=obj.get('Date'),
        genre=obj.get('Genre'),
        length=obj.get('Duration', 0) * 1000 or None,
        name=obj['DisplayName'],
        track_no=obj.get('TrackNumber'),
        uri=urijoin(baseuri, basepath(obj.get('RefPath', obj['Path'])))
    )


def model(baseuri, obj):
    type = obj.get('TypeEx', obj['Type'])
    if type == 'music' or type == 'audio':
        return track(baseuri, obj)
    elif type == ALBUM_TYPE:
        return album(baseuri, obj)
    elif type == ARTIST_TYPE:
        return artist(baseuri, obj)
    else:
        raise ValueError('Unsupported object type "%s"', type)


def query(query, exact, searchcaps):
    terms = []
    caps = frozenset(searchcaps)
    op = '=' if exact else 'contains'
    for key, values in query.items():
        try:
            fmt = _QUERYMAP[key](caps)
        except KeyError:
            raise ValueError('Keyword "%s" not supported' % key)
        if fmt:
            terms.extend(fmt.format(op, _quote(value)) for value in values)
        else:
            raise ValueError('Keyword "%s" not supported by device' % key)
    return ('(%s)' % ') and ('.join(terms)) or '*'