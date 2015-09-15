import bottle
import datetime
import json
import pathlib
import random
import tempfile

try:
    import uwsgi
    CONFIG_PATH = pathlib.Path(uwsgi.opt['config_path'].decode('utf-8') if isinstance(uwsgi.opt['config_path'], bytes) else uwsgi.opt['config_path'])
except:
    CONFIG_PATH = pathlib.Path('/opt/wurstmineberg/config/api.json')

def config():
    try:
        with CONFIG_PATH.open() as config_file:
            loaded_config = json.load(config_file)
    except:
        loaded_config = {}
    result = {
        'isDev': loaded_config.get('isDev', False)
    }
    result['cache'] = pathlib.Path(loaded_config.get('cache', '/opt/wurstmineberg/dev-api-cache' if result['isDev'] else '/opt/wurstmineberg/api-cache'))
    result['host'] = loaded_config.get('host', 'dev.wurstmineberg.de' if result['isDev'] else 'wurstmineberg.de')
    result['jlogPath'] = pathlib.Path(loaded_config.get('jlogPath', '/opt/wurstmineberg/jlog'))
    result['logPath'] = pathlib.Path(loaded_config.get('logPath', '/opt/wurstmineberg/log'))
    result['moneysFile'] = pathlib.Path(loaded_config.get('moneysFile', '/opt/wurstmineberg/moneys/moneys.json'))
    result['webAssets'] = pathlib.Path(loaded_config.get('webAssets', '/opt/git/github.com/wurstmineberg/assets.wurstmineberg.de/branch/dev' if result['isDev'] else '/opt/git/github.com/wurstmineberg/assets.wurstmineberg.de/master'))
    return result

CONFIG = config()

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

def cached_image(cache_path, image_func, cache_check):
    if CONFIG['cache'].exists():
        image_path = CONFIG['cache'] / cache_path
        if cache_check(image_path):
            return bottle.static_file(image_path.name, str(image_path.parent), mimetype='image/png')
        else:
            if not image_path.parent.exists():
                image_path.parent.mkdir(parents=True)
            image_file = image_path.open('wb')
    else:
        image_file = tempfile.NamedTemporaryFile(suffix='.png', delete=False)
        image_path = pathlib.Path(image_file.name)
    image = image_func()
    image.save(image_file, 'PNG')
    image_file.close()
    return bottle.static_file(image_path.name, str(image_path.parent), mimetype='image/png')

def skin_cache_check(image_path):
    if not image_path.exists():
        return False # image has not been rendered yet
    max_age = datetime.timedelta(hours=random.randrange(4, 8), minutes=random.randrange(0, 60)) # use a random value between 4 and 8 hours for the cache expiration check
    if datetime.datetime.utcfromtimestamp(image_path.stat().st_mtime) < datetime.datetime.utcnow() - max_age:
        return False # image is older than max_age
    return True
