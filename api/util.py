import bottle
import json
from pathlib import Path


CONFIG_TYPES = {
    "cache": Path,
    "logPath": Path,
    "moneysFile": Path,
    "webAssets": Path,
}

from wmb import get_config, from_assets
CONFIG = get_config("api", base = from_assets(__file__), value_types = CONFIG_TYPES)


ERROR_PAGE_TEMPLATE = """
%try:
    %from bottle import HTTP_CODES, request
    <!DOCTYPE html>
    <html>
        <head>
            <title>Error: {{e.status}}</title>
            <style type="text/css">
                html {
                    background-color: #eee;
                    font-family: sans;
                }
                body {
                    background-color: #fff;
                    border: 1px solid #ddd;
                    padding: 15px;
                    margin: 15px;
                }
                pre {
                    background-color: #eee;
                    border: 1px solid #ddd;
                    padding: 5px;
                }
            </style>
        </head>
        <body>
            <h1>Error: {{e.status}}</h1>
            <p>Sorry, the requested URL <tt>{{repr(request.url)}}</tt> caused an error:</p>
            <pre>{{e.body}}</pre>
            %if e.exception:
                <h2>Exception:</h2>
                <pre>{{repr(e.exception)}}</pre>
            %end
            %if e.traceback:
                <h2>Traceback:</h2>
                <pre>{{e.traceback}}</pre>
            %end
        </body>
    </html>
%except ImportError:
    <b>ImportError:</b> Could not generate the error page. Please add bottle to
    the import path.
%end
"""

class Bottle(bottle.Bottle):
    def default_error_handler(self, res):
        return bottle.tob(bottle.template(ERROR_PAGE_TEMPLATE, e=res))

def map_image(map_dict):
    """Returns a PIL.Image.Image object of the map.

    Required arguments:
    map_dict -- A dict representing NBT data for a map, as returned by api_map_by_id
    """
    import PIL.Image

    map_palette = [
        (0, 0, 0), # special-cased to transparent in the code below
        (125, 176, 55),
        (244, 230, 161),
        (197, 197, 197),
        (252, 0, 0),
        (158, 158, 252),
        (165, 165, 165),
        (0, 123, 0),
        (252, 252, 252),
        (162, 166, 182),
        (149, 108, 76),
        (111, 111, 111),
        (63, 63, 252),
        (141, 118, 71),
        (252, 249, 242),
        (213, 125, 50),
        (176, 75, 213),
        (101, 151, 213),
        (226, 226, 50),
        (125, 202, 25),
        (239, 125, 163),
        (75, 75, 75),
        (151, 151, 151),
        (75, 125, 151),
        (125, 62, 176),
        (50, 75, 176),
        (101, 75, 50),
        (101, 125, 50),
        (151, 50, 50),
        (25, 25, 25),
        (247, 235, 76),
        (91, 216, 210),
        (73, 129, 252),
        (0, 214, 57),
        (21, 20, 31),
        (112, 2, 0),
        (127, 85, 48)
    ]
    ret = PIL.Image.new('RGBA', (map_dict['data']['width'], map_dict['data']['height']), color=(0, 0, 0, 0))
    for i, color in enumerate(map_dict['data']['colors']):
        y, x = divmod(i, map_dict['data']['width'])
        base_color, color_variant = divmod(color, 4)
        if base_color == 0:
            continue
        color = tuple(round(palette_color * [180, 220, 255, 135][color_variant] / 255) for palette_color in map_palette[base_color]) + (255,)
        ret.putpixel((x, y), color)
    return ret

def format_stats(stats):
    ret = {}
    for stat_name, value in stats.items():
        parent = ret
        key_path = stat_name.split('.')
        for key in key_path[:-1]:
            if key not in parent:
                parent[key] = {}
            elif not isinstance(parent[key], dict):
                parent[key] = {'summary': parent[key]}
            parent = parent[key]
        if key_path[-1] in parent:
            parent[key_path[-1]]['summary'] = value
        else:
            parent[key_path[-1]] = value
        if key_path[:2] == ['stat', 'pickup'] and len(key_path) > 2:
            if 'summary' not in ret['stat']['pickup']:
                ret['stat']['pickup']['summary'] = 0
            ret['stat']['pickup']['summary'] += value
    return ret
