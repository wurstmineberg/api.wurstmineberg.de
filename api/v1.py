import sys

sys.path.append('/opt/py')

import bottle
import json
import minecraft
import nbt.nbt
import os
import os.path
import pathlib
import re
import time

import api.util
import api.v2

DOCUMENTATION_INTRO = """
<h1>Wurstmineberg API v1</h1>
<p>Welcome to the Wurstmineberg Minecraft API. Feel free to play around!</p>
<p>This is version 1.18.1 of the API. Currently available API endpoints:</p>
"""

application = api.util.Bottle()

def nbtfile_to_dict(filename):
    if isinstance(filename, pathlib.Path):
        filename = str(filename)
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
    directory = minecraft.World().world_path / 'players'
    for root, dirs, files in os.walk(str(directory)):
        for file in files:
            if file.endswith('.dat'):
                name = os.path.splitext(file)[0]
                data.append(name)
    return data

@application.route('/')
def show_index():
    """The documentation page for version 1 of the API."""
    documentation = DOCUMENTATION_INTRO
    documentation += '<table id="api-endpoints"><tbody>\n'
    documentation += '<tr><th style="text-align: left">Endpoint</th><th style="text-align: left">Description</th>\n'
    documentation += '\n<tr><td><a href="/v2/">/v2/</td><td>The documentation page for version 2 of the API. See that page for the list of version 2 endpoints.</td></tr>'
    for route in application.routes:
        documentation += '\n<tr><td>' + route.rule + '</td><td>' + str(route.callback.__doc__) + '</td></tr>'
    documentation += '</tbody></table>'
    return documentation

@application.route('/deathgames/log.json')
def api_death_games_log():
    """Returns the Death Games log, listing attempts in chronological order. See http://wiki.wurstmineberg.de/Death_Games for more info."""
    with (api.util.CONFIG['logPath'] / 'deathgames.json').open() as death_games_logfile:
        return json.load(death_games_logfile)

@application.route('/minecraft/items/all.json')
def api_all_items():
    """Returns the item info JSON file, see http://assets.wurstmineberg.de/json/items.json.description.txt for documentation"""
    with (api.util.CONFIG['webAssets'] / 'json' / 'items.json').open() as items_file:
        return json.load(items_file)

@application.route('/minecraft/items/by-damage/:item_id/:item_damage')
def api_item_by_damage(item_id, item_damage):
    """Returns the item info for an item with the given numeric or text ID and numeric damage value. Text IDs may use a period instead of a colon to separate the plugin prefix, or omit the prefix entirely if it is “minecraft:”."""
    ret = api_item_by_id(item_id)
    if 'damageValues' in ret:
        if str(item_damage) in ret['damageValues']:
            ret.update(ret['damageValues'][str(item_damage)])
        del ret['damageValues']
    return ret

@application.route('/minecraft/items/by-effect/:item_id/:effect_id')
def api_item_by_effect(item_id, effect_id):
    """Returns the item info for an item with the given numeric or text ID, tagged with the given text effect ID. Text IDs may use a period instead of a colon to separate the plugin prefix, or omit the prefix entirely if it is “minecraft:”."""
    ret = api_item_by_id(item_id)
    if 'effects' not in ret:
        bottle.abort(404, '{} has no effect variants'.format(ret.get('name', 'Item')))
    effect_id = re.sub('\\.', ':', effect_id)
    if ':' in effect_id:
        effect_plugin, effect_id = effect_id.split(':')
    else:
        effect_plugin = 'minecraft'
    if effect_plugin not in ret['effects'] or effect_id not in ret['effects'][effect_plugin]:
        bottle.abort(404, 'Item {} has no effect variant for {}:{}'.format(ret['stringID'], effect_plugin, effect_id))
    ret.update(ret['effects'][effect_plugin][effect_id])
    del ret['effects']
    return ret

@application.route('/minecraft/items/by-tag/:item_id/:tag_value')
def api_item_by_tag_variant(item_id, tag_value):
    """Returns the item info for an item with the given numeric or text ID, tagged with the given tag variant for the tag path specified in items.json. Text IDs may use a period instead of a colon to separate the plugin prefix, or omit the prefix entirely if it is “minecraft:”."""
    ret = api_item_by_id(item_id)
    if 'tagPath' not in ret:
        bottle.abort(404, '{} has no tag variants'.format(ret.get('name', 'Item')))
    if str(tag_value) not in ret['tagVariants']:
        bottle.abort(404, 'Item {} has no tag variant for tag value {}'.format(ret['stringID'], tag_value))
    ret.update(ret['tagVariants'][str(tag_value)])
    del ret['tagPath']
    del ret['tagVariants']
    return ret

@application.route('/minecraft/items/by-id/:item_id')
def api_item_by_id(item_id):
    """Returns the item info for an item with the given numeric or text ID and the default damage value. Text IDs may use a period instead of a colon to separate the plugin prefix, or omit the prefix entirely if it is “minecraft:”."""
    all_items = api_all_items()
    try:
        item_id = int(item_id)
        id_is_numeric = True
    except ValueError:
        id_is_numeric = False
        item_id = re.sub('\\.', ':', str(item_id))
    if id_is_numeric:
        plugin = 'minecraft'
        for string_id, item in all_items[plugin].items():
            if item.get('blockID') == item_id:
                item_id = string_id
                ret = item
                if 'blockInfo' in ret:
                    ret.update(ret['blockInfo'])
                    del ret['blockInfo']
                break
            if item.get('itemID') == item_id:
                item_id = string_id
                ret = item
                if 'blockInfo' in ret:
                    del ret['blockInfo']
                break
        else:
            bottle.abort(404, 'No item with id ' + item_id)
    else:
        if ':' in item_id:
            plugin, item_id = item_id.split(':')
        else:
            plugin = 'minecraft'
        if plugin in all_items and item_id in all_items[plugin]:
            ret = all_items[plugin][item_id]
        else:
            bottle.abort(404, 'No item with id {}:{}'.format(plugin, item_id))
    ret['stringID'] = plugin + ':' + item_id
    return ret

@application.route('/minecraft/items/render/dyed-by-id/:item_id/:color/png.png')
def api_item_render_dyed_png(item_id, color):
    """Returns a dyed item's base texture (color specified in hex rrggbb), rendered as a PNG image file."""
    plugin, item_id = item_id.split(':', 1)
    return api.v2.api_item_render_dyed_png(plugin, item_id, color)

@application.route('/minigame/achievements/winners.json')
def api_achievement_winners():
    """Returns a list of Wurstmineberg IDs of all players who have completed all achievements, ordered chronologically by the time they got their last achievement. This list is emptied each time a new achievement is added to Minecraft."""
    return json.dumps(list(api.v2.api_achievement_winners(minecraft.World()).keys()), sort_keys=True, indent=4)

@application.route('/minigame/diary/all.json')
def api_diary():
    """Returns all diary entries, sorted chronologically. Note: the diary feature has been removed, so this will return an empty array."""
    return json.dumps([], sort_keys=True, indent=4)

@application.route('/player/:player_id/info.json')
def api_player_info(player_id):
    """Returns the section of people.json that corresponds to the player. See http://wiki.wurstmineberg.de/People_file/Version_2 for more info."""
    import people

    people_data = people.get_people_db().obj_dump(version=2)['people']
    person_data = list(filter(lambda a: player_id == a['id'], people_data))[0]
    if 'gravatar' in person_data:
        del person_data['gravatar']
    return person_data

@application.route('/player/people.json')
def api_player_people():
    """Returns the whole people.json file. See http://wiki.wurstmineberg.de/People_file/Version_2 for more info."""
    import people

    db = people.get_people_db().obj_dump(version=2)
    for person in db['people']:
        if 'gravatar' in person:
            del person['gravatar']
    return db

@application.route('/player/:player_minecraft_name/playerdata.json')
def api_player_data(player_minecraft_name):
    """Returns the player data encoded as JSON, also accepts the player id instead of the Minecraft name"""
    nbt_file = minecraft.World().world_path / 'players' / (player_minecraft_name + '.dat')
    if not nbt_file.exists():
        for whitelist_entry in json.loads(api_whitelist()):
            if whitelist_entry['name'] == player_minecraft_name:
                uuid = whitelist_entry['uuid']
                break
        else:
            uuid = api_player_info(player_minecraft_name)['minecraftUUID']
        if '-' not in uuid:
            uuid = uuid[:8] + '-' + uuid[8:12] + '-' + uuid[12:16] + '-' + uuid[16:20] + '-' + uuid[20:]
        nbt_file = minecraft.World().world_path / 'playerdata' / (uuid + '.dat')
    return nbtfile_to_dict(nbt_file)

@application.route('/player/:player_id/stats-grouped.json')
def api_player_stats_grouped(player_id):
    """Returns the player's stats formatted as JSON with stats grouped into objects by category"""
    stats = api_stats(player_id)
    return api.util.format_stats(stats)

@application.route('/player/:player_minecraft_name/stats.json')
def api_stats(player_minecraft_name):
    """Returns the stats JSON file from the server, also accepts the player id instead of the Minecraft name"""
    import api.util2

    try:
        player = api.util2.Player.by_minecraft_nick(player_minecraft_name)
    except LookupError:
        player = api.util2.Player(player_minecraft_name)
    stats_file = minecraft.World().world_path / 'stats' / '{}.json'.format(player.data['minecraft']['nicks'][-1])
    if not stats_file.exists():
        stats_file = minecraft.World().world_path / 'stats' / '{}.json'.format(player.uuid)
    with stats_file.open() as stats:
        return json.load(stats)

@application.route('/server/deaths/latest.json')
def api_latest_deaths():
    """Returns JSON containing information about the most recent death of each player"""
    return api.v2.api_latest_deaths(minecraft.World())

@application.route('/server/deaths/overview.json')
def api_deaths():
    """Returns JSON containing information about all recorded player deaths"""
    return api.v2.api_deaths(minecraft.World())

@application.route('/server/level.json')
def api_level():
    """Returns the level.dat encoded as JSON"""
    nbt_file = minecraft.World().world_path / 'level.dat'
    return nbtfile_to_dict(nbt_file)

@application.route('/server/maps/by-id/:identifier')
def api_map_by_id(identifier):
    """Returns info about the map item with damage value :identifier, see http://minecraft.gamepedia.com/Map_Item_Format for documentation"""
    nbt_file = minecraft.World().world_path / 'data' / 'map_{}.dat'.format(identifier)
    return nbtfile_to_dict(nbt_file)

@application.route('/server/maps/overview.json')
def api_maps_index():
    """Returns a list of existing maps with all of their fields except for the actual colors."""
    ret = {}
    for map_file in (minecraft.World().world_path / 'data').iterdir():
        match = re.match('map_([0-9]+).dat', map_file.name)
        if not match:
            continue
        map_id = int(match.group(1))
        nbt_dict = nbtfile_to_dict(map_file)['data']
        del nbt_dict['colors']
        ret[str(map_id)] = nbt_dict
    return ret

@application.route('/server/maps/render/:identifier/png.png')
def api_map_render_png(identifier):
    """Returns the map item with damage value :identifier, rendered as a PNG image file."""
    return api.v2.api_map_render_png(minecraft.World().name, identifier)

@application.route('/server/playerdata/by-id/:identifier')
def api_player_data_by_id(identifier):
    """Returns a dictionary with Minecraft nicks as the keys, and their player data fields :identifier as the values"""
    all_data = api_player_data_all()
    data = {}
    for player in all_data:
        playerdata = all_data[player]
        for name in playerdata:
            if name == identifier:
                data[player] = playerdata[name]
    return data

@application.route('/server/playerdata.json')
def api_player_data_all():
    """Returns the player data of all whitelisted players, encoded as JSON"""
    nbtdicts = {}
    for user in playernames():
        with contextlib.suppress(FileNotFoundError):
            nbtdata = api_player_data(user)
        nbtdicts[user] = nbtdata
    return nbtdicts

@application.route('/server/playernames.json')
def api_playernames():
    """Returns the Minecraft nicknames of all players on the whitelist"""
    return json.dumps(playernames(), sort_keys=True, indent=4)

@application.route('/server/playerstats.json')
def api_playerstats():
    """Returns all player stats in one file. This file can be potentially big. Please use one of the other APIs if possible."""
    data = {}
    people_data = None
    directory = minecraft.World().world_path / 'stats'
    for root, dirs, files in os.walk(str(directory)):
        for file_name in files:
            if file_name.endswith(".json"):
                with (directory / file_name).open('r') as playerfile:
                    name = os.path.splitext(file_name)[0]
                    uuid_filename = re.match('([0-9a-f]{8})-([0-9a-f]{4})-([0-9a-f]{4})-([0-9a-f]{4})-([0-9a-f]+)$', name)
                    if uuid_filename:
                        uuid = ''.join(uuid_filename.groups())
                        if people_data is None:
                            import people
                            people_data = people.get_people_db().obj_dump(version=2)['people']
                        for person in people_data:
                            if (person.get('minecraftUUID') == uuid or person.get('minecraftUUID') == name) and 'minecraft' in person:
                                name = person['minecraft']
                                break
                    data[name] = json.loads(playerfile.read())
    return data

@application.route('/server/playerstats/achievement.json')
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

@application.route('/server/playerstats/by-id/:identifier')
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
        bottle.abort(404, 'Identifier not found')
    return data

@application.route('/server/playerstats/entity.json')
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

@application.route('/server/playerstats/general.json')
def api_playerstats_general():
    """Returns all general stats in one file"""
    all_data = api_playerstats()
    data = {}
    for player, player_data in all_data.items():
        player_dict = {}
        for stat_str, value in player_data.items():
            stat = stat_str.split('.')
            if stat[0] == 'stat' and len(stat) == 2:
                player_dict[stat_str] = value
            elif stat[0] == 'stat' and stat[1] == 'pickup':
                if 'stat.pickup' not in player_dict:
                    player_dict['stat.pickup'] = 0
                player_dict['stat.pickup'] += value
        data[player] = player_dict
    return data

@application.route('/server/playerstats/item.json')
def api_playerstats_items():
    """Returns all item and block stats in one file"""
    all_data = api_playerstats()
    data = {}
    item_actions = 'useItem', 'craftItem', 'breakItem', 'mineBlock', 'pickup', 'drop'
    for player, player_data in all_data.items():
        player_dict = {}
        for stat_str, value in player_data.items():
            stat = stat_str.split('.')
            if stat[0] == 'stat' and stat[1] in item_actions:
                player_dict[stat_str] = value
        data[player] = player_dict
    return data

@application.route('/server/scoreboard.json')
def api_scoreboard():
    """Returns the scoreboard data encoded as JSON"""
    nbt_file = minecraft.World().world_path / 'data' / 'scoreboard.dat'
    return nbtfile_to_dict(nbt_file)

@application.route('/server/sessions/overview.json')
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
    with (api.util.CONFIG['logPath'] / 'logins.log').open() as logins_log:
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

@application.route('/server/sessions/lastseen.json')
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
    with (api.util.CONFIG['logPath'] / 'logins.log').open() as logins_log:
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

@application.route('/server/status.json')
def api_short_server_status():
    """Returns JSON containing whether the server is online, the current Minecraft version, and the list of people who are online."""
    status = api.v2.api_world_status(minecraft.World())
    return {
        'list': status['list'],
        'on': status['running'],
        'version': status['version']
    }

@application.route('/server/whitelist.json')
def api_whitelist():
    """For UUID-based Minecraft servers (1.7.6 and later), returns the whitelist. For older servers, the behavior is undefined."""
    with (minecraft.World().path / 'whitelist.json').open() as whitelist:
        return whitelist.read()

@application.route('/server/world/villages/end.json')
def api_villages():
    """Returns the villages.dat of the main world's End, encoded as JSON"""
    nbt_file = minecraft.World().world_path / 'data' / 'villages_end.dat'
    return nbtfile_to_dict(nbt_file)

@application.route('/server/world/villages/nether.json')
def api_villages():
    """Returns the villages.dat of the main world's Nether, encoded as JSON"""
    nbt_file = minecraft.World().world_path / 'data' / 'villages_nether.dat'
    return nbtfile_to_dict(nbt_file)

@application.route('/server/world/villages/overworld.json')
def api_villages():
    """Returns the villages.dat of the main world's Overworld, encoded as JSON"""
    nbt_file = minecraft.World().world_path / 'data' / 'villages.dat'
    return nbtfile_to_dict(nbt_file)

@application.route('/moneys/moneys.json')
def api_moneys():
    """Returns the moneys.json file."""
    with api.util.CONFIG['moneysFile'].open() as moneys_json:
        return json.load(moneys_json)
