#!/usr/bin/python
'''
A basic bottle app skeleton
'''

SERVERLOCATION="/opt/wurstmineberg/server/wurstmineberg"

DOCUMENTATION_INTRO="""
Welcome to the Wurstmineberg API. Feel free to play around!<br>
<br>
Currently available API endpoints:
"""

from bottle import *
from nbt import *

app = application = Bottle()

@app.route('/')
def show_index():
    '''
    The documentation page
    '''
    documentation = DOCUMENTATION_INTRO
    for route in app.routes:
        documentation += "<br>* " + route.rule + ": " + str(route.callback.__doc__)
    return documentation

def nbt_to_dict(nbtfile):
    dict = {}
    is_collection = False
    is_dict = False
    collection = []
    for tag in nbtfile.tags:
        if "tags" in tag.__dict__:
            if tag.name == "":
                collection.append(nbt_to_dict(tag))
                is_collection = True
            else:
                dict[tag.name] = nbt_to_dict(tag)
                is_dict = True
        else:
            if tag.name == "":
                collection.append(tag.value)
                is_collection = True
            else:
                dict[tag.name] = tag.value
                is_dict = True

    if is_dict and is_collection:
        dict["collection"] = collection
        return dict

    if is_collection:
        return collection
    else:
        return dict

@app.route('/player/:player_name/playerdata.json')
def api_player_data(player_name):
    '''
    Returns the player data encoded as JSON
    '''
    nbtfile = nbt.NBTFile(SERVERLOCATION + "/players/" + player_name + ".dat")

    return nbt_to_dict(nbtfile)

@app.route('/player/:player_name/stats.json')
def api_stats(player_name):
    '''
    Returns the stats JSON file from the server
    '''
    return static_file('/stats/' + player_name + '.json', SERVERLOCATION)

@app.route('/server/scoreboard.json')
def api_scoreboard():
    '''
    Returns the scoreboard data encoded as JSON
    '''
    nbtfile = nbt.NBTFile(SERVERLOCATION + "/data/scoreboard.dat")
    return nbt_to_dict(nbtfile)

@app.route('/server/level.json')
def api_level():
    '''
    Returns the level.dat encoded as JSON
    '''
    nbtfile = nbt.NBTFile(SERVERLOCATION + "/level.dat")
    return nbt_to_dict(nbtfile)

class StripPathMiddleware(object):
    '''
    Get that slash out of the request
    '''
    def __init__(self, a):
        self.a = a
    def __call__(self, e, h):
        e['PATH_INFO'] = e['PATH_INFO'].rstrip('/')
        return self.a(e, h)

if __name__ == '__main__':
    run(app=StripPathMiddleware(app),
        server='python_server',
        host='0.0.0.0',
        port=8080)

