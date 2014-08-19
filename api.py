#!/usr/bin/env python3
"""
Wurstmineberg API server
"""

import sys

sys.path.append('/opt/py')

import bottle
import collections
from datetime import datetime
import io
import json
import nbt.nbt
import os
import os.path
import re
import subprocess
import time

def parse_version_string():
    path = __file__
    while os.path.islink(path):
        path = os.path.join(os.path.dirname(path), os.readlink(path))
    path = os.path.dirname(path) # go up one level, from repo/api.py to repo, where README.md is located
    while os.path.islink(path):
        path = os.path.join(os.path.dirname(path), os.readlink(path))
    try:
        version = subprocess.check_output(['git', 'rev-parse', '--abbrev-ref', 'HEAD'], cwd=path).decode('utf-8').strip('\n')
        if version == 'master':
            try:
                with open(os.path.join(path, 'README.md')) as readme:
                    for line in readme.read().splitlines():
                        if line.startswith('This is version '):
                            return line.split(' ')[3]
            except:
                pass
        return subprocess.check_output(['git', 'rev-parse', '--short', 'HEAD'], cwd=path).decode('utf-8').strip('\n')
    except:
        pass

__version__ = str(parse_version_string())

CONFIG_PATH = '/opt/wurstmineberg/config/api.json'

DOCUMENTATION_INTRO = """
<h1>Wurstmineberg API</h1>
<p>Welcome to the Wurstmineberg Minecraft API. Feel free to play around!</p>
<p>This is version {} of the API. Currently available API endpoints:</p>
""".format(__version__)

app = application = bottle.Bottle() # aliased as application for uwsgi to find

def config(key=None):
    default_config = {
        'jlogPath': '/opt/wurstmineberg/jlog',
        'logPath': '/opt/wurstmineberg/log',
        'peopleFile': '/opt/wurstmineberg/config/people.json',
        'serverDir': '/opt/wurstmineberg/server',
        'webAssets': '/opt/hub/wurstmineberg/assets.wurstmineberg.de/json',
        'worldName': 'wurstmineberg'
    }
    try:
        with open(CONFIG_PATH) as config_file:
            j = json.load(config_file)
    except:
        j = default_config
    if key is None:
        return j
    return j.get(key, default_config.get(key))

def nbtfile_to_dict(filename):
    nbtfile = nbt.nbt.NBTFile(filename)
    nbtdict = nbt_to_dict(nbtfile)
    if isinstance(nbtdict, dict):
        nbtdict['api-time-last-modified'] = os.path.getmtime(filename)
        nbtdict['api-time-result-fetched'] = time.time()
    return nbtdict

def nbt_to_dict(nbtfile):
    """Generates a JSON-serializable value from an nbt.nbt.NBTFile object."""
    dict = {}
    is_collection = False
    is_dict = False
    collection = []
    for tag in nbtfile.tags:
        if hasattr(tag, 'tags'):
            if tag.name is None or tag.name == '':
                collection.append(nbt_to_dict(tag))
                is_collection = True
            else:
                dict[tag.name] = nbt_to_dict(tag)
                is_dict = True
        else:
            value = tag.value
            if isinstance(value, bytearray):
                value = list(value)
            if tag.name is None or tag.name == '':
                collection.append(value)
                is_collection = True
            else:
                dict[tag.name] = value
                is_dict = True
    if is_collection and is_dict:
        dict['collection'] = collection
    if is_dict:
        return dict
    else:
        return collection

def playernames():
    """Returns all player names it can find"""
    try:
        data = [entry['name'] for entry in json.loads(api_whitelist())]
    except:
        data = []
    directory = os.path.join(config('serverDir'), config('worldName'), 'players')
    for root, dirs, files in os.walk(directory):
        for file in files:
            if file.endswith('.dat'):
                name = os.path.splitext(file)[0]
                data.append(name)
    return data

@app.route('/')
def show_index():
    """The documentation page"""
    documentation = DOCUMENTATION_INTRO
    documentation += '<table id="api-endpoints"><tbody>\n'
    documentation += '<tr><th style="text-align: left">Endpoint</th><th style="text-align: left">Description</th>\n'
    for route in app.routes:
        documentation += '\n<tr><td>' + route.rule + '</td><td>' + str(route.callback.__doc__) + '</td></tr>'
    documentation += '</tbody></table>'
    return documentation

@app.route('/deathgames/log.json')
def api_death_games_log():
    """Returns the Death Games log, listing attempts in chronological order. See http://wiki.wurstmineberg.de/Death_Games for more info."""
    with open(os.path.join(config('logPath'), 'deathgames.json')) as death_games_logfile:
        return json.load(death_games_logfile)

@app.route('/minecraft/items/all.json')
def api_all_items():
    """Returns the item info JSON file, see http://assets.wurstmineberg.de/json/items.json.description.txt for documentation"""
    with open(os.path.join(config('webAssets'), 'items.json')) as items_file:
        return json.load(items_file)

@app.route('/minecraft/items/by-damage/:item_id/:item_damage')
def api_item_by_damage(item_id, item_damage):
    """Returns the item info for an item with the given numeric or text ID and numeric damage value. Note that text IDs may be ambiguous and will return an arbitrary matching item."""
    all_items = api_all_items()
    try:
        item_id = int(item_id)
        id_is_numeric = True
    except ValueError:
        id_is_numeric = False
        item_id = re.sub('\\.', ':', str(item_id))
        if ':' not in item_id:
            item_id = 'minecraft:' + item_id
    if id_is_numeric:
        if str(item_id) in all_items:
            ret = all_items[str(item_id)]
        else:
            abort(404, 'No item with id ' + str(item_id))
    else:
        for _, item in all_items.items():
            if 'id' in item and item['id'] == item_id:
                ret = item
                break
        else:
            abort(404, 'No item with id ' + item_id)
    if 'damageValues' in ret:
        if str(item_damage) in ret['damageValues']:
            ret.update(ret['damageValues'][str(item_damage)])
        del ret['damageValues']
    return ret

@app.route('/minecraft/items/by-id/:item_id')
def api_item_by_id(item_id):
    """Returns the item info for an item with the given numeric or text ID and the default damage value. Note that text IDs may be ambiguous and will return an arbitrary matching item."""
    return api_item_by_damage(item_id, None)

@app.route('/minigame/achievements/winners.json')
def api_achievement_winners():
    """Returns a list of Wurstmineberg IDs of all players who have completed all achievements, ordered chronologically by the time they got their last achievement. This list is emptied each time a new achievement is added to Minecraft."""
    with open(os.path.join(config('logPath'), 'achievements.log')) as achievements_log:
        return json.dumps(list(line.strip() for line in achievements_log))

@app.route('/minigame/diary/all.json')
def api_diary():
    """Returns all diary entries, sorted chronologically."""
    ret = []
    with open(os.path.join(config('jlogPath'), 'diary.jlog')) as diary_jlog:
        for line in diary_jlog:
            ret.append(json.loads(line))
    return json.dumps(ret, sort_keys=True, indent=4)

@app.route('/player/:player_id/info.json')
def api_player_info(player_id):
    """Returns the section of people.json that corresponds to the player. See http://wiki.wurstmineberg.de/People_file for more info."""
    person_data = None
    with open(config('peopleFile')) as people_json:
        data = json.load(people_json)
        if isinstance(data, dict):
            data = data['people']
        person_data = list(filter(lambda a: player_id == a['id'], data))[0]
    return person_data

@app.route('/player/:player_minecraft_name/playerdata.json')
def api_player_data(player_minecraft_name):
    """Returns the player data encoded as JSON, also accepts the player id instead of the Minecraft name"""
    nbtfile = os.path.join(config('serverDir'), config('worldName'), 'players', player_minecraft_name + '.dat')
    if not os.path.exists(nbtfile):
        for whitelist_entry in json.loads(api_whitelist()):
            if whitelist_entry['name'] == player_minecraft_name:
                uuid = whitelist_entry['uuid']
                break
        else:
            uuid = api_player_info(player_minecraft_name)['minecraftUUID']
        if '-' not in uuid:
            uuid = uuid[:8] + '-' + uuid[8:12] + '-' + uuid[12:16] + '-' + uuid[16:20] + '-' + uuid[20:]
        nbtfile = os.path.join(config('serverDir'), config('worldName'), 'playerdata', uuid + '.dat')
    return nbtfile_to_dict(nbtfile)

@app.route('/player/:player_minecraft_name/stats.json')
def api_stats(player_minecraft_name):
    """Returns the stats JSON file from the server, also accepts the player id instead of the Minecraft name"""
    stats_file = os.path.join(config('serverDir'), config('worldName'), 'stats', player_minecraft_name + '.json')
    if not os.path.exists(stats_file):
        for whitelist_entry in json.loads(api_whitelist()):
            if whitelist_entry['name'] == player_minecraft_name:
                uuid = whitelist_entry['uuid']
                break
        else:
            uuid = api_player_info(player_minecraft_name)['minecraftUUID']
        if '-' not in uuid:
            uuid = uuid[:8] + '-' + uuid[8:12] + '-' + uuid[12:16] + '-' + uuid[16:20] + '-' + uuid[20:]
        stats_file = os.path.join(config('serverDir'), config('worldName'), 'stats', uuid + '.json')
    with open(stats_file) as stats:
        return json.load(stats)

@app.route('/server/deaths/latest.json')
def api_latest_deaths():
    """Returns JSON containing information about the most recent death of each player"""
    last_person = None
    people_ids = {}
    with open(config('peopleFile')) as people_json:
        people_data = json.load(people_json)
        if isinstance(people_data, dict):
            people_data = people_data['people']
        for person in people_data:
            if 'id' in person and 'minecraft' in person:
                people_ids[person['minecraft']] = person['id']
    deaths = {}
    with open(os.path.join(config('logPath'), 'deaths.log')) as deaths_log:
        for line in deaths_log:
            match = re.match('([0-9]{4}-[0-9]{2}-[0-9]{2} [0-9]{2}:[0-9]{2}:[0-9]{2}) ([^@ ]+) (.*)', line)
            if match and match.group(2) in people_ids:
                last_person = person_id = people_ids[match.group(2)]
                deaths[person_id] = {
                    'cause': match.group(3),
                    'timestamp': match.group(1)
                }
    return {
        'deaths': deaths,
        'lastPerson': last_person
    }

@app.route('/server/deaths/overview.json')
def api_deaths():
    """Returns JSON containing information about all recorded player deaths"""
    people_ids = {}
    with open(config('peopleFile')) as people_json:
        people_data = json.load(people_json)
        if isinstance(people_data, dict):
            people_data = people_data['people']
        for person in people_data:
            if 'id' in person and 'minecraft' in person:
                people_ids[person['minecraft']] = person['id']
    deaths = collections.defaultdict(list)
    with open(os.path.join(config('logPath'), 'deaths.log')) as deaths_log:
        for line in deaths_log:
            match = re.match('([0-9]{4}-[0-9]{2}-[0-9]{2} [0-9]{2}:[0-9]{2}:[0-9]{2}) ([^@ ]+) (.*)', line)
            if match and match.group(2) in people_ids:
                person_id = people_ids[match.group(2)]
                deaths[person_id].append({
                    'cause': match.group(3),
                    'timestamp': match.group(1)
                })
    return deaths

@app.route('/server/level.json')
def api_level():
    """Returns the level.dat encoded as JSON"""
    nbtfile = os.path.join(config('serverDir'), config('worldName'), 'level.dat')
    return nbtfile_to_dict(nbtfile)

@app.route('/server/maps/by-id/:identifier')
def api_map_by_id(identifier):
    """Returns info about the map item with damage value :identifier, see http://minecraft.gamepedia.com/Map_Item_Format for documentation"""
    nbt_file = os.path.join(config('serverDir'), config('worldName'), 'data', 'map_' + str(identifier) + '.dat')
    return nbtfile_to_dict(nbt_file)

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

@app.route('/server/maps/render/:identifier/png.png')
def api_map_render_png(identifier):
    """Returns the map item with damage values :identifier, rendered as a PNG image file."""
    img_io = io.BytesIO()
    image = map_image(api_map_by_id(identifier))
    image.save(img_io, 'PNG')
    img_io.seek(0)
    return img_io

@app.route('/server/playerdata/by-id/:identifier')
def api_player_data_by_id(identifier):
    """Returns all the player data with the specified ID"""
    all_data = api_player_data_all()
    data = {}
    for player in all_data:
        playerdata = all_data[player]
        for name in playerdata:
            if name == identifier:
                data[player] = playerdata[name]
    return data

@app.route('/server/playerdata.json')
def api_player_data_all():
    """Returns all the player data encoded as JSON"""
    nbtdicts = {}
    for user in playernames():
        nbtdata = api_player_data(user)
        nbtdicts[user] = nbtdata
    return nbtdicts

@app.route('/server/playernames.json')
def api_playernames():
    """Returns all player names it can find"""
    return json.dumps(playernames())

@app.route('/server/playerstats.json')
def api_playerstats():
    """Returns all player stats in one file. This file can be potentially big. Please use one of the other APIs if possible."""
    data = {}
    people = None
    directory = os.path.join(config('serverDir'), config('worldName'), 'stats')
    for root, dirs, files in os.walk(directory):
        for file_name in files:
            if file_name.endswith(".json"):
                with open(os.path.join(directory, file_name), 'r') as playerfile:
                    name = os.path.splitext(file_name)[0]
                    uuid_filename = re.match('([0-9a-f]{8})-([0-9a-f]{4})-([0-9a-f]{4})-([0-9a-f]{4})-([0-9a-f]+)$', name)
                    if uuid_filename:
                        uuid = ''.join(uuid_filename.groups())
                        if people is None:
                            with open(config('peopleFile')) as people_json:
                                people = json.load(people_json)
                                if isinstance(data, dict):
                                    people = people['people']
                        for person in people:
                            if (person.get('minecraftUUID') == uuid or person.get('minecraftUUID') == name) and 'minecraft' in person:
                                name = person['minecraft']
                                break
                    data[name] = json.loads(playerfile.read())
    return data

@app.route('/server/playerstats/achievement.json')
def api_playerstats_achievements():
    """Returns all achievement stats in one file"""
    alldata = api_playerstats()
    data = {}
    for player in alldata:
        playerdata = alldata[player]
        playerdict = {}
        for statstr in playerdata:
            value = playerdata[statstr]
            stat = statstr.split('.')
            if stat[0] == 'achievement':
                playerdict[statstr] = value
        data[player] = playerdict
    return data

@app.route('/server/playerstats/by-id/:identifier')
def api_playerstats_by_id(identifier):
    """Returns the stat item :identifier from all player stats"""
    alldata = api_playerstats()
    data = {}
    for player in alldata:
        playerdata = alldata[player]
        playerdict = {}
        if identifier in playerdata:
            data[player] = playerdata[identifier]
    if len(data) == 0:
        abort(404, "Identifier not found")
    return data

@app.route('/server/playerstats/entity.json')
def api_playerstats_entities():
    """Returns all entity stats in one file"""
    alldata = api_playerstats()
    data = {}
    entityActions = ['killEntity', 'entityKilledBy']
    for player in alldata:
        playerdata = alldata[player]
        playerdict = {}
        for statstr in playerdata:
            value = playerdata[statstr]
            stat = statstr.split('.')
            if stat[0] == 'stat' and stat[1] in entityActions:
                playerdict[statstr] = value
        data[player] = playerdict
    return data

@app.route('/server/playerstats/general.json')
def api_playerstats_general():
    """Returns all general stats in one file"""
    alldata = api_playerstats()
    data = {}
    nonGeneralActions = [
        'useItem', 'craftItem', 'breakItem', 'mineBlock', 'killEntity', 'entityKilledBy']
    for player in alldata:
        playerdata = alldata[player]
        playerdict = {}
        for statstr in playerdata:
            value = playerdata[statstr]
            stat = statstr.split('.')
            if stat[0] == 'stat' and stat[1] not in nonGeneralActions:
                playerdict[statstr] = value
        data[player] = playerdict
    return data

@app.route('/server/playerstats/item.json')
def api_playerstats_items():
    """Returns all item and block stats in one file"""
    alldata = api_playerstats()
    data = {}
    itemActions = ['useItem', 'craftItem', 'breakItem', 'mineBlock']
    for player in alldata:
        playerdata = alldata[player]
        playerdict = {}
        for statstr in playerdata:
            value = playerdata[statstr]
            stat = statstr.split('.')
            if stat[0] == 'stat' and stat[1] in itemActions:
                playerdict[statstr] = value
        data[player] = playerdict
    return data

@app.route('/server/scoreboard.json')
def api_scoreboard():
    """Returns the scoreboard data encoded as JSON"""
    nbtfile = os.path.join(config('serverDir'), config('worldName'), 'data', 'scoreboard.dat')
    return nbtfile_to_dict(nbtfile)

@app.route('/server/sessions/overview.json')
def api_sessions():
    """Returns known players' sessions since the first recorded server restart"""
    uptimes = []
    current_uptime = None
    matches = {
        'join': '([0-9]{4}-[0-9]{2}-[0-9]{2} [0-9]{2}:[0-9]{2}:[0-9]{2}) ([a-z0-9]+|\\?) joined ([A-Za-z0-9_]{1,16})',
        'leave': '([0-9]{4}-[0-9]{2}-[0-9]{2} [0-9]{2}:[0-9]{2}:[0-9]{2}) ([a-z0-9]+|\\?) left ([A-Za-z0-9_]{1,16})',
        'restart': '([0-9]{4}-[0-9]{2}-[0-9]{2} [0-9]{2}:[0-9]{2}:[0-9]{2}) @restart',
        'start': '([0-9]{4}-[0-9]{2}-[0-9]{2} [0-9]{2}:[0-9]{2}:[0-9]{2}) @start ([^ ]+)',
        'stop': '([0-9]{4}-[0-9]{2}-[0-9]{2} [0-9]{2}:[0-9]{2}:[0-9]{2}) @stop'
    }
    with open(os.path.join(config('logPath'), 'logins.log')) as logins_log:
        for log_line in logins_log:
            for match_type, match_string in matches.items():
                match = re.match(match_string, log_line.strip('\n'))
                if match:
                    break
            else:
                continue
            if match_type == 'restart':
                if current_uptime is not None:
                    current_uptime['endTime'] = match.group(1)
                    for session in current_uptime.get('sessions', []):
                        if 'leaveTime' not in session:
                            session['leaveTime'] = match.group(1)
                            session['leaveReason'] = 'restart'
                    uptimes.append(current_uptime)
                current_uptime = {'startTime': match.group(1)}
            elif match_type == 'start':
                if current_uptime is not None:
                    current_uptime['endTime'] = match.group(1)
                    for session in current_uptime.get('sessions', []):
                        if 'leaveTime' not in session:
                            session['leaveTime'] = match.group(1)
                            session['leaveReason'] = 'serverStartOverride'
                    uptimes.append(current_uptime)
                current_uptime = {
                    'startTime': match.group(1),
                    'version': match.group(2)
                }
            elif match_type == 'stop':
                if current_uptime is not None:
                    current_uptime['endTime'] = match.group(1)
                    for session in current_uptime.get('sessions', []):
                        if 'leaveTime' not in session:
                            session['leaveTime'] = match.group(1)
                            session['leaveReason'] = 'serverStop'
                    uptimes.append(current_uptime)
            elif current_uptime is None or match.group(2) == '?':
                continue
            elif match_type == 'join':
                if 'sessions' not in current_uptime:
                    current_uptime['sessions'] = []
                current_uptime['sessions'].append({
                    'joinTime': match.group(1),
                    'minecraftNick': match.group(3),
                    'person': match.group(2)
                })
            elif match_type == 'leave':
                for session in current_uptime.get('sessions', []):
                    if 'leaveTime' not in session and session['person'] == match.group(2):
                        session['leaveTime'] = match.group(1)
                        session['leaveReason'] = 'logout'
                        break
    if current_uptime is not None:
        for session in current_uptime.get('sessions', []):
            if 'leaveTime' not in session:
                session['leaveReason'] = 'currentlyOnline'
        uptimes.append(current_uptime)
    return {'uptimes': uptimes}

@app.route('/server/sessions/lastseen.json')
def api_sessions_last_seen():
    """Returns the last known session for each player"""
    matches = {
        'join': '([0-9]{4}-[0-9]{2}-[0-9]{2} [0-9]{2}:[0-9]{2}:[0-9]{2}) ([a-z0-9]+|\\?) joined ([A-Za-z0-9_]{1,16})',
        'leave': '([0-9]{4}-[0-9]{2}-[0-9]{2} [0-9]{2}:[0-9]{2}:[0-9]{2}) ([a-z0-9]+|\\?) left ([A-Za-z0-9_]{1,16})',
        'restart': '([0-9]{4}-[0-9]{2}-[0-9]{2} [0-9]{2}:[0-9]{2}:[0-9]{2}) @restart',
        'start': '([0-9]{4}-[0-9]{2}-[0-9]{2} [0-9]{2}:[0-9]{2}:[0-9]{2}) @start ([^ ]+)',
        'stop': '([0-9]{4}-[0-9]{2}-[0-9]{2} [0-9]{2}:[0-9]{2}:[0-9]{2}) @stop'
    }
    ret = {}
    with open(os.path.join(config('logPath'), 'logins.log')) as logins_log:
        for log_line in logins_log:
            for match_type, match_string in matches.items():
                match = re.match(match_string, log_line.strip('\n'))
                if match:
                    break
            else:
                continue
            if match_type == 'restart':
                for session in ret.values():
                    if 'leaveTime' not in session:
                        session['leaveTime'] = match.group(1)
                        session['leaveReason'] = 'restart'
            elif match_type == 'start':
                for session in ret.values():
                    if 'leaveTime' not in session:
                        session['leaveTime'] = match.group(1)
                        session['leaveReason'] = 'serverStartOverride'
            elif match_type == 'stop':
                for session in ret.values():
                    if 'leaveTime' not in session:
                        session['leaveTime'] = match.group(1)
                        session['leaveReason'] = 'serverStop'
            elif match_type == 'join':
                if match.group(2) == '?':
                    continue
                ret[match.group(2)] = {
                    'joinTime': match.group(1),
                    'minecraftNick': match.group(3),
                    'person': match.group(2)
                }
            elif match_type == 'leave':
                if match.group(2) not in ret:
                    continue
                ret[match.group(2)]['leaveTime'] = match.group(1)
                ret[match.group(2)]['leaveReason'] = 'logout'
    for session in ret.values():
        if 'leaveTime' not in session:
            session['leaveReason'] = 'currentlyOnline'
    return ret

@app.route('/server/whitelist.json')
def api_whitelist():
    """For UUID-based Minecraft servers (1.7.6 and later), returns the whitelist. For older servers, the behavior is undefined."""
    with open(os.path.join(config('serverDir'), 'whitelist.json')) as whitelist:
        return whitelist.read()

class StripPathMiddleware:
    """Get that slash out of the request"""
    def __init__(self, a):
        self.app = a
    
    def __call__(self, e, h):
        e['PATH_INFO'] = e['PATH_INFO'].rstrip('/')
        return self.app(e, h)

if __name__ == '__main__':
    bottle.run(app=StripPathMiddleware(app), host='0.0.0.0', port=8081)
