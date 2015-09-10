import bottle

try:
    import uwsgi
    CONFIG_PATH = pathlib.Path(uwsgi.opt['config_path'])
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
        (0, 0, 0),
        (127, 178, 56),
        (247, 233, 163),
        (167, 167, 167),
        (255, 0, 0),
        (160, 160, 255),
        (167, 167, 167),
        (0, 124, 0),
        (255, 255, 255),
        (164, 168, 184),
        (183, 106, 47),
        (112, 112, 112),
        (64, 64, 255),
        (104, 83, 50),
        (255, 252, 245),
        (216, 127, 51),
        (178, 76, 216),
        (102, 153, 216),
        (229, 229, 51),
        (127, 204, 25),
        (242, 127, 165),
        (76, 76, 76),
        (153, 153, 153),
        (76, 127, 153),
        (127, 63, 178),
        (51, 76, 178),
        (102, 76, 51),
        (102, 127, 51),
        (153, 51, 51),
        (25, 25, 25),
        (250, 238, 77),
        (92, 219, 213),
        (74, 128, 255),
        (0, 217, 58),
        (21, 20, 31),
        (112, 2, 0)
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
