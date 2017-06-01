import sys

sys.path.append('/opt/py')

import bottle
import collections
import contextlib
import datetime
import hashlib
import json
import minecraft
import more_itertools
import pathlib
import re
import subprocess
import xml.sax.saxutils

import api.log
import api.util
import api.util2

from api.version import __version__

DOCUMENTATION_INTRO = """
<!DOCTYPE html>
<h1>Wurstmineberg API v2</h1>
<p>Welcome to the Wurstmineberg Minecraft API. Feel free to play around!</p>
<p>This is version {} of the API. Currently available API endpoints:</p>
""".format(__version__)

application = api.util.Bottle()

@application.route('/')
def show_index():
    """The documentation page for version 2 of the API."""
    yield DOCUMENTATION_INTRO
    yield '<table id="api-endpoints"><tbody>\n'
    yield '<tr><th style="text-align: left">Endpoint</th><th style="text-align: left">Description</th>\n'
    for route in application.routes:
        if route.rule == '/':
            yield '\n<tr><td style="white-space: nowrap; font-weight: bold;">/v2/</td><td>This documentation page for version 2 of the API.</td></tr>'
        elif route.rule.endswith('.json') and any(route.rule[:-4] + 'dat' == iter_route.rule for iter_route in application.routes):
            # JSONified version of an NBT endpoint
            continue
        elif route.rule.endswith('.dat'):
            if '<' in route.rule:
                yield '\n<tr><td style="white-space: nowrap;">/v2' + xml.sax.saxutils.escape(route.rule[:-4]) + '.json (or .dat)</td><td>' + route.callback.__doc__.format(host=api.util.CONFIG['host']) + '</td></tr>'
            else:
                yield '\n<tr><td style="white-space: nowrap;"><a href="/v2' + route.rule[:-4] + '.json">/v2' + route.rule[:-4] + '.json</a> (or <a href="/v2' + route.rule + '">.dat</a>)</td><td>' + route.callback.__doc__.format(host=api.util.CONFIG['host']) + '</td></tr>'
        else:
            if '<' in route.rule:
                yield '\n<tr><td style="white-space: nowrap;">/v2' + xml.sax.saxutils.escape(route.rule) + '</td><td>' + route.callback.__doc__.format(host=api.util.CONFIG['host']) + '</td></tr>'
            else:
                yield '\n<tr><td style="white-space: nowrap;"><a href="/v2' + route.rule + '">/v2' + route.rule + '</a></td><td>' + route.callback.__doc__.format(host=api.util.CONFIG['host']) + '</td></tr>'
    yield '</tbody></table>'

@api.util2.json_route(application, '/meta/config/api')
def api_api_config():
    """Returns the API configuration, for debugging purposes."""
    result = {key: (str(value) if isinstance(value, pathlib.Path) else value) for key, value in api.util.CONFIG.items()}
    return result

@api.util2.json_route(application, '/meta/moneys')
def api_moneys():
    """Returns the moneys.json file."""
    with api.util.CONFIG['moneysFile'].open() as moneys_json:
        return json.load(moneys_json)

@api.util2.json_route(application, '/meta/version')
def api_version():
    """Returns version numbers of known Wurstmineberg services (currently only this API instance)"""
    return {
        'api': __version__
    }

@api.util2.json_route(application, '/minecraft/items/all')
def api_all_items():
    """Returns the item info JSON file (<a href="http://assets.{host}/json/items.json.description.txt">documentation</a>)"""
    with (api.util.CONFIG['webAssets'] / 'json' / 'items.json').open() as items_file:
        return json.load(items_file)

@api.util2.json_route(application, '/minecraft/items/by-damage/<plugin>/<item_id>/<item_damage>')
@api.util2.decode_args
def api_item_by_damage(plugin, item_id, item_damage: int):
    """Returns the item info for an item with the given text ID and numeric damage value."""
    ret = api_item_by_id(plugin, item_id)
    if 'damageValues' not in ret:
        bottle.abort(404, '{} has no damage variants'.format(ret.get('name', 'Item')))
    if str(item_damage) not in ret['damageValues']:
        bottle.abort(404, 'Item {}:{} has no damage variant for damage value {}'.format(plugin, item_id, item_damage))
    ret.update(ret['damageValues'][str(item_damage)])
    del ret['damageValues']
    return ret

@api.util2.json_route(application, '/minecraft/items/by-effect/<plugin>/<item_id>/<effect_plugin>/<effect_id>')
def api_item_by_effect(plugin, item_id, effect_plugin, effect_id):
    """Returns the item info for an item with the given text ID, tagged with the given text effect ID."""
    ret = api_item_by_id(plugin, item_id)
    if 'effects' not in ret:
        bottle.abort(404, '{} has no effect variants'.format(ret.get('name', 'Item')))
    if effect_plugin not in ret['effects'] or effect_id not in ret['effects'][effect_plugin]:
        bottle.abort(404, 'Item {}:{} has no effect variant for {}:{}'.format(plugin, item_id, effect_plugin, effect_id))
    ret.update(ret['effects'][effect_plugin][effect_id])
    del ret['effects']
    return ret

@api.util2.json_route(application, '/minecraft/items/by-id/<plugin>/<item_id>')
def api_item_by_id(plugin, item_id):
    """Returns the item info for an item with the given text ID, including variant info."""
    all_items = api_all_items()
    if plugin in all_items and item_id in all_items[plugin]:
        ret = all_items[plugin][item_id]
    else:
        bottle.abort(404, 'No item with id {}:{}'.format(plugin, item_id))
    return ret

@api.util2.json_route(application, '/minecraft/items/by-tag/<plugin>/<item_id>/<tag_value>')
def api_item_by_tag_variant(plugin, item_id, tag_value):
    """Returns the item info for an item with the given text ID, tagged with the given tag variant for the tag path specified in items.json."""
    ret = api_item_by_id(plugin, item_id)
    if 'tagPath' not in ret:
        bottle.abort(404, '{} has no tag variants'.format(ret.get('name', 'Item')))
    if str(tag_value) not in ret['tagVariants']:
        bottle.abort(404, 'Item {}:{} has no tag variant for tag value {}'.format(plugin, item_id, tag_value))
    ret.update(ret['tagVariants'][str(tag_value)])
    del ret['tagPath']
    del ret['tagVariants']
    return ret

@application.route('/minecraft/items/render/dyed-by-id/<plugin>/<item_id>/<color>.png')
@api.util2.decode_args
def api_item_render_dyed_png(plugin, item_id, color: 'color'):
    """Returns a dyed item's base texture (color specified in hex rrggbb), rendered as a PNG image file."""
    cache_path = 'dyed-items/{}/{}/{:02x}{:02x}{:02x}.png'.format(plugin, item_id, *color)

    def image_func():
        import PIL.Image
        import PIL.ImageChops

        item = api_item_by_id(plugin, item_id)

        image = PIL.Image.open(api.util.CONFIG['webAssets'] / 'img' / 'grid-base' / item['image'])
        image = PIL.ImageChops.multiply(image, PIL.Image.new('RGBA', image.size, color=color + (255,)))
        return image

    def cache_check(image_path):
        if not image_path.exists():
            return False
        return True #TODO check if base texture has changed

    return api.util2.cached_image(cache_path, image_func, cache_check)

@api.util2.json_route(application, '/minigame/achievements/<world>/scoreboard')
@api.util2.decode_args
def api_achievement_scores(world: minecraft.World):
    """Returns an object mapping player's IDs to their current score in the achievement run."""
    return {player_id: more_itertools.quantify((value['value'] if isinstance(value, dict) else value) > 0 for value in achievement_data.values()) for player_id, achievement_data in api_playerstats_achievements(world).items()}

@api.util2.json_route(application, '/minigame/achievements/<world>/winners')
@api.util2.decode_args
def api_achievement_winners(world: minecraft.World):
    """Returns an object mapping IDs of players who have completed all achievements to the UTC datetime they got their last achievement. This list is emptied each time a new achievement is added to Minecraft."""
    # get the current number of achievements
    with (api.util.CONFIG['webAssets'] / 'json' / 'achievements.json').open() as achievements_f:
        num_achievements = len(json.load(achievements_f))
    # get the set of players who have completed all achievements
    winners = {api.util2.Player(player) for player, score in api_achievement_scores(world).items() if score == num_achievements}
    # load from cache
    cache_path = api.util.CONFIG['cache'] / 'achievement-winners.json'
    try:
        with cache_path.open() as cache_f:
            cache = json.load(cache_f)
        if cache['numAchievements'] == num_achievements:
            # no new achievements introduced, start with the cache
            result = cache['result']
            winners -= {api.util2.Player(player) for player in result}
        else:
            # new achievements introduced, any completions must have happened since cache creation
            result = {}
        log = api.log.Log(world)[datetime.date.fromtimestamp(cache_path.stat().st_mtime) - datetime.timedelta(days=2):].reversed() # only look at the new logs, plus 2 more days to account for timezone weirdness
    except:
        result = {}
        log = api.log.Log(world).reversed()
    # look for new completions
    if len(winners) > 0:
        for line in log:
            if line.type is api.log.LineType.achievement and line.data['player'] in winners:
                result[str(line.data['player'])] = line.data['time'].strftime('%Y-%m-%d %H:%M:%S')
                winners.remove(line.data['player'])
                if len(winners) == 0:
                    break
    # write to cache
    if api.util.CONFIG['cache'].exists():
        with cache_path.open('w') as cache_f:
            json.dump({
                'numAchievements': num_achievements,
                'result': result
            }, cache_f, sort_keys=True, indent=4)
    return result

@api.util2.json_route(application, '/minigame/deathgames/log')
def api_death_games_log():
    """Returns the <a href="http://wiki.{host}/Death_Games">Death Games</a> log, listing attempts in chronological order."""
    with (api.util.CONFIG['logPath'] / 'deathgames.json').open() as death_games_logfile:
        return json.load(death_games_logfile)

@api.util2.json_route(application, '/people')
def api_player_people():
    """Returns the whole <a href="http://wiki.{host}/People_file/Version_3">people.json</a> file, except for the "gravatar" private field, which is replaced by the gravatar URL."""
    import people

    db = people.get_people_db().obj_dump(version=3)
    for person in db['people'].values():
        if 'gravatar' in person:
            person['gravatar'] = 'https://www.gravatar.com/avatar/{}'.format(hashlib.md5(person['gravatar'].encode('utf-8')).hexdigest())
    return db

@api.util2.json_route(application, '/player/<player>/info')
@api.util2.decode_args
def api_player_info(player: api.util2.Player):
    """Returns the section of <a href="http://wiki.{host}/People_file/Version_3">people.json</a> that corresponds to the player, except for the "gravatar" private field, which is replaced by the gravatar URL."""
    person_data = player.data
    if 'gravatar' in person_data:
        person_data['gravatar'] = 'https://www.gravatar.com/avatar/{}'.format(hashlib.md5(person_data['gravatar'].encode('utf-8')).hexdigest())
    return person_data

@application.route('/player/<player>/skin/render/front/<size>.png')
@api.util2.decode_args
def api_skin_render_front_png(player: api.util2.Player, size: range(1025)):
    """Returns a player skin in front view (including the overlay layers), as a &lt;size&gt;×(2*&lt;size&gt;)px PNG image file. Requires playerhead."""
    def image_func():
        import playerhead

        return playerhead.body(player.data['minecraft']['nicks'][-1], profile_id=player.uuid).resize((size, 2 * size))

    return api.util2.cached_image('skins/front-views/{}/{}.png'.format(size, player), image_func, api.util2.skin_cache_check)

@application.route('/player/<player>/skin/render/head/<size>.png')
@api.util2.decode_args
def api_skin_render_head_png(player: api.util2.Player, size: range(1025)):
    """Returns a player skin's head (including the hat layer), as a &lt;size&gt;×&lt;size&gt;px PNG image file. Requires playerhead."""
    def image_func():
        import playerhead

        return playerhead.head(player.data['minecraft']['nicks'][-1], profile_id=player.uuid).resize((size, size))

    return api.util2.cached_image('skins/heads/{}/{}.png'.format(size, player), image_func, api.util2.skin_cache_check)

@application.route('/world/<world>/backup/latest.tar.gz')
@api.util2.decode_args
def api_latest_backup(world: minecraft.World):
    """Sends the latest backup of the world directory as a gzipped tarball."""
    import backuproll

    if float(backuproll.__version__) < 0.2:
        backup_roll = backuproll.BackupRoll('/opt/wurstmineberg/backup/{}'.format(world), '{}_'.format(world), '.tar.gz', '%Y-%m-%d_%Hh%M', None, simulate=True)
        try:
            latest_backup = backup_roll.list_backups_recent()[-1]
        except IndexError:
            bottle.abort(404, 'No backups exist for the {} world'.format(world))

        return bottle.static_file(latest_backup.filename, root=latest_backup.basedir)
    else:
        store = backuproll.MinecraftBackupRoll.get_readonly_store()
        collection = store.get_collection(str(world))
        backup = collection.get_retain_group('recent').get_latest_backup()
        bottle.response.content_type = 'application/x-compressed'
        bottle.response.set_header('Content-Disposition', 'attachment; filename={}.tar.gz'.format(backup.name))
        return backup.tar_file_iterator(subdir=str(world))

@api.util2.json_route(application, '/world/<world>/chunks/overview')
@api.util2.decode_args
def api_chunk_overview(world: minecraft.World):
    """Returns a list of all chunk columns that have been generated, grouped by dimension."""
    import anvil

    result = {}
    for dimension in api.util2.Dimension:
        if dimension.region_path(world).exists():
            result[dimension.name] = []
            for region_path in dimension.region_path(world).iterdir():
                if region_path.suffix != '.mca':
                    continue
                result[dimension.name] += ({'x': col.x, 'z': col.z} for col in anvil.Region(region_path))
    return result

@api.util2.nbt_route(application, '/world/<world>/chunks/<dimension>/column/<x>/<z>')
@api.util2.decode_args
def api_chunk_column(world: minecraft.World, dimension: api.util2.Dimension, x: int, z: int):
    """Returns the given chunk column in JSON-encoded <a href="http://minecraft.gamepedia.com/Anvil_file_format">Anvil</a> NBT."""
    import anvil

    region = anvil.Region(dimension.region_path(world) / 'r.{}.{}.mca'.format(x // 32, z // 32))
    chunk_column = region.chunk_column(x, z)
    return chunk_column.data

@api.util2.json_route(application, '/world/<world>/chunks/<dimension>/chunk/<x>/<y>/<z>')
@api.util2.decode_args
def api_chunk_info(world: minecraft.World, dimension: api.util2.Dimension, x: int, y: range(16), z: int):
    """Returns information about the given chunk section in JSON format. The nested arrays can be indexed in y-z-x order."""
    return api.util2.chunk_section_info(api_chunk_column.dict(world, dimension, x, z), x, y, z)

@api.util2.json_route(application, '/world/<world>/chunks/<dimension>/block/<x>/<y>/<z>')
@api.util2.decode_args
def api_block_info(world: minecraft.World, dimension: api.util2.Dimension, x: int, y: range(256), z: int):
    """Returns information about a single block in JSON format."""
    chunk_x, block_x = divmod(x, 16)
    chunk_y, block_y = divmod(y, 16)
    chunk_z, block_z = divmod(z, 16)
    return api_chunk_info(world, dimension, chunk_x, chunk_y, chunk_z)[block_y][block_z][block_x]

@api.util2.json_route(application, '/world/<world>/deaths/latest')
@api.util2.decode_args
def api_latest_deaths(world: minecraft.World):
    """Returns JSON containing information about the most recent death of each player"""
    def newest_timestamp(item):
        player_id, deaths = item
        return datetime.datetime.strptime(deaths[-1]['timestamp'], '%Y-%m-%d %H:%M:%S').replace(tzinfo=datetime.timezone.utc)

    all_deaths = api_deaths(world)
    return {
        'deaths': {player_id: deaths[-1] for player_id, deaths in all_deaths.items()},
        'lastPerson': more_itertools.first(sorted(all_deaths.items(), key=newest_timestamp, reverse=True), (None, []))[0]
    }

@api.util2.json_route(application, '/world/<world>/deaths/all')
@api.util2.decode_args
def api_deaths(world: minecraft.World):
    """Returns JSON containing information about all player deaths"""
    # load from cache
    cache_path = api.util.CONFIG['cache'] / 'all-deaths.json'
    result = collections.defaultdict(list)
    log = api.log.Log(world)
    if cache_path.exists():
        with cache_path.open() as cache_f:
            with contextlib.suppress(ValueError):
                cache = json.load(cache_f)
                if cache['numMessages'] == len(api.log.death_messages):
                    result.update(cache['deaths'])
                    log = api.log.Log(world)[datetime.date.fromtimestamp(cache_path.stat().st_mtime) - datetime.timedelta(days=2):] # only look at the new logs, plus 2 more days to account for timezone weirdness
    # look for new deaths
    for line in log:
        if line.type is api.log.LineType.death:
            result[str(line.data['player'])].append({
                'cause': line.data['cause'],
                'timestamp': line.data['time'].strftime('%Y-%m-%d %H:%M:%S')
            })
    # write to cache
    if api.util.CONFIG['cache'].exists():
        with cache_path.open('w') as cache_f:
            json.dump({
                'deaths': result,
                'numMessages': len(api.log.death_messages)
            }, cache_f, sort_keys=True, indent=4)
    return result

@api.util2.nbt_route(application, '/world/<world>/level')
@api.util2.decode_args
def api_level(world: minecraft.World):
    """Returns the level.dat encoded as JSON"""
    return world.world_path / 'level.dat'

@api.util2.json_route(application, '/world/<world>/logs/all')
@api.util2.decode_args
def api_logs_all(world: minecraft.World):
    """Returns a JSON-formatted version of all available logs for the world. Warning: this file is potentially very big. Please use one of the other APIs if possible."""
    for line in api.log.Log(world):
        yield line.as_json()

@api.util2.json_route(application, '/world/<world>/logs/latest')
@api.util2.decode_args
def api_logs_latest(world: minecraft.World):
    """Returns a JSON-formatted version of the world's latest.log"""
    for line in api.log.Log.latest(world):
        yield line.as_json()

@api.util2.nbt_route(application, '/world/<world>/maps/by-id/<identifier>')
@api.util2.decode_args
def api_map_by_id(world: minecraft.World, identifier: int):
    """Returns info about the map item with damage value &lt;identifier&gt;, see <a href="http://minecraft.gamepedia.com/Map_Item_Format">Map Item Format</a> for documentation"""
    return world.world_path / 'data' / 'map_{}.dat'.format(identifier)

@api.util2.json_route(application, '/world/<world>/maps/overview')
@api.util2.decode_args
def api_maps_index(world: minecraft.World):
    """Returns a list of existing maps with all of their fields except for the actual colors."""
    ret = {}
    for map_file in (world.world_path / 'data').iterdir():
        match = re.match('map_([0-9]+).dat', map_file.name)
        if not match:
            continue
        map_id = int(match.group(1))
        nbt_dict = api.util2.nbtfile_to_dict(map_file)['data']
        del nbt_dict['colors']
        ret[str(map_id)] = nbt_dict
    return ret

@application.route('/world/<world>/maps/render/<identifier>.png')
@api.util2.decode_args
def api_map_render_png(world: minecraft.World, identifier: int):
    """Returns the map item with damage value &lt;identifier&gt;, rendered as a PNG image file."""
    def cache_check(image_path):
        if not image_path.exists():
            return False
        if image_path.stat().st_mtime < (world.world_path / 'data' / 'map_{}.dat'.format(identifier)).stat().st_mtime + 60:
            return False
        return True

    def image_func():
        return api.util.map_image(api_map_by_id(world, identifier))

    return api.util2.cached_image('map-renders/{}.png'.format(identifier), image_func, cache_check)

@api.util2.json_route(application, '/world/<world>/player/<player>/advancements')
@api.util2.decode_args
def api_player_advancements(world: minecraft.World, player: api.util2.Player):
    """Returns the advancements.json for this player."""
    advancements_path = world.world_path / 'advancements' / '{}.json'.format(player.uuid)
    with advancements_path.open() as advancements_file:
        return json.load(advancements_file)

@api.util2.nbt_route(application, '/world/<world>/player/<player>/playerdata')
@api.util2.decode_args
def api_player_data(world: minecraft.World, player: api.util2.Player):
    """Returns the <a href="http://minecraft.gamepedia.com/Player.dat_format">player data</a> encoded as JSON"""
    return world.world_path / 'playerdata' / '{}.dat'.format(player.uuid)

@api.util2.json_route(application, '/world/<world>/player/<player>/stats')
@api.util2.decode_args
def api_player_stats(world: minecraft.World, player: api.util2.Player):
    """Returns the player's stats formatted as JSON with stats grouped into objects by category"""
    stats_path = world.world_path / 'stats' / '{}.json'.format(player.uuid)
    if not stats_path.exists():
        player_minecraft_name = player.data['minecraft']['nicks'][-1]
        stats_path = world.world_path / 'stats' / '{}.json'.format(player_minecraft_name)
    with stats_path.open() as stats_file:
        stats = json.load(stats_file)
    return api.util.format_stats(stats)

@api.util2.json_route(application, '/world/<world>/playerdata/all')
@api.util2.decode_args
def api_player_data_all(world: minecraft.World):
    """Returns the player data of all known players, encoded as JSON"""
    nbt_dicts = {}
    for data_path in (world.world_path / 'playerdata').iterdir():
        if data_path.suffix == '.dat':
            player = api.util2.Player(data_path.stem)
            nbt_dicts[str(player)] = api.util2.nbtfile_to_dict(data_path)
    return nbt_dicts

@api.util2.json_route(application, '/world/<world>/playerdata/by-id/<identifier>')
@api.util2.decode_args
def api_player_data_by_id(world: minecraft.World, identifier):
    """Returns a dictionary with player IDs as the keys, and their player data fields &lt;identifier&gt; as the values"""
    all_data = api_player_data_all(world)
    data = {}
    for player in all_data:
        playerdata = all_data[player]
        for name in playerdata:
            if name == identifier:
                data[player] = playerdata[name]
    return data

@api.util2.json_route(application, '/world/<world>/playerstats/all')
@api.util2.decode_args
def api_playerstats(world: minecraft.World):
    """Returns all stats for all players in one file."""
    data = {}
    people = None
    stats_dir = world.world_path / 'stats'
    for stats_path in stats_dir.iterdir():
        if stats_path.suffix == '.json':
            with stats_path.open() as stats_file:
                person = api.util2.Player(stats_path.stem)
                data[str(person)] = api.util.format_stats(json.load(stats_file))
    return data

@api.util2.json_route(application, '/world/<world>/playerstats/achievement')
@api.util2.decode_args
def api_playerstats_achievements(world: minecraft.World):
    """Returns all achievement stats in one file. Does not include players who have logged in since 17w13a."""
    all_data = api_playerstats(world)
    data = {}
    for player_id, player_data in all_data.items():
        if 'achievement' in player_data:
            data[player_id] = player_data['achievement']
    return data

@api.util2.json_route(application, '/world/<world>/playerstats/by-id/<identifier>')
@api.util2.decode_args
def api_playerstats_by_id(world: minecraft.World, identifier):
    """Returns the stat item &lt;identifier&gt; from all player stats."""
    all_data = api_playerstats(world)
    key_path = identifier.split('.')
    data = {}
    for player_id, player_data in all_data.items():
        parent = player_data
        for key in key_path[:-1]:
            if key not in parent:
                parent[key] = {}
            elif not isinstance(parent[key], dict):
                parent[key] = {'summary': parent[key]}
            parent = parent[key]
        if key_path[-1] in parent:
            data[player_id] = parent[key_path[-1]]
    if len(data) == 0: #TODO only error if the stat is also not found in assets
        bottle.abort(404, 'Identifier not found')
    return data

@api.util2.json_route(application, '/world/<world>/playerstats/entity')
@api.util2.decode_args
def api_playerstats_entities(world: minecraft.World):
    """Returns all entity stats in one file"""
    all_data = api_playerstats(world)
    data = {}
    for player_id, player_data in all_data.items():
        for stat_str, value in player_data.get('stat', {}).items():
            if stat_str in ('killEntity', 'entityKilledBy'):
                if player_id not in data:
                    data[player_id] = {}
                data[player_id][stat_str] = value
    return data

@api.util2.json_route(application, '/world/<world>/playerstats/general')
@api.util2.decode_args
def api_playerstats_general(world: minecraft.World):
    """Returns all general stats in one file"""
    all_data = api_playerstats(world)
    non_general = (
        'breakItem',
        'craftItem',
        'drop',
        'entityKilledBy',
        'killEntity',
        'mineBlock',
        'pickup',
        'useItem'
    )
    data = {}
    for player_id, player_data in all_data.items():
        filtered = {stat_id: stat for stat_id, stat in player_data.get('stat', {}).items() if stat_id not in non_general}
        if len(filtered) > 0:
            data[player_id] = filtered
    return data

@api.util2.json_route(application, '/world/<world>/playerstats/item')
@api.util2.decode_args
def api_playerstats_items(world: minecraft.World):
    """Returns all item and block stats in one file"""
    all_data = api_playerstats(world)
    data = {}
    for player_id, player_data in all_data.items():
        for stat_str, value in player_data.get('stat', {}).items():
            if stat_str in ('useItem', 'craftItem', 'breakItem', 'mineBlock', 'pickup', 'drop'):
                if player_id not in data:
                    data[player_id] = {}
                data[player_id][stat_str] = value
    return data

@api.util2.nbt_route(application, '/world/<world>/scoreboard')
@api.util2.decode_args
def api_scoreboard(world: minecraft.World):
    """Returns the scoreboard data encoded as JSON"""
    return world.world_path / 'data' / 'scoreboard.dat'

@api.util2.json_route(application, '/world/<world>/sessions/all')
@api.util2.decode_args
def api_sessions(world: minecraft.World):
    """Returns all player sessions since the first logged server start"""
    log = api.log.Log(world)
    current_uptime = None
    for line in log:
        if line.type is api.log.LineType.start:
            start_time_str = line.data['time'].strftime('%Y-%m-%d %H:%M:%S')
            if current_uptime is not None:
                current_uptime['endTime'] = start_time_str
                for session in current_uptime.get('sessions', []):
                    if 'leaveTime' not in session:
                        session['leaveTime'] = start_time_str
                        session['leaveReason'] = 'serverStartOverride'
                yield current_uptime
            current_uptime = {
                'startTime': start_time_str,
                'version': line.data['version']
            }
        elif line.type is api.log.LineType.stop:
            stop_time_str = line.data['time'].strftime('%Y-%m-%d %H:%M:%S')
            if current_uptime is not None:
                current_uptime['endTime'] = stop_time_str
                for session in current_uptime.get('sessions', []):
                    if 'leaveTime' not in session:
                        session['leaveTime'] = stop_time_str
                        session['leaveReason'] = 'serverStop'
                yield current_uptime
                current_uptime = None
        elif line.type is api.log.LineType.join:
            if current_uptime is None:
                continue
            join_time_str = line.data['time'].strftime('%Y-%m-%d %H:%M:%S')
            if 'sessions' not in current_uptime:
                current_uptime['sessions'] = []
            current_uptime['sessions'].append({
                'joinTime': join_time_str,
                'person': str(line.data['player'])
            })
        elif line.type is api.log.LineType.leave:
            if current_uptime is None:
                continue
            leave_time_str = line.data['time'].strftime('%Y-%m-%d %H:%M:%S')
            for session in current_uptime.get('sessions', []):
                if 'leaveTime' not in session and session['person'] == str(line.data['player']):
                    session['leaveTime'] = leave_time_str
                    session['leaveReason'] = 'logout'
                    break

    if current_uptime is not None:
        for session in current_uptime.get('sessions', []):
            if 'leaveTime' not in session:
                session['leaveReason'] = 'currentlyOnline'
        yield current_uptime

@api.util2.json_route(application, '/world/<world>/sessions/lastseen')
@api.util2.decode_args
def api_sessions_last_seen_world(world: minecraft.World):
    """Returns the last known session for each player"""
    # load from cache
    cache_path = api.util.CONFIG['cache'] / 'last-seen' / '{}.json'.format(world)
    try:
        with cache_path.open() as cache_f:
            result = json.load(cache_f)
        log = api.log.Log(world)[datetime.date.fromtimestamp(cache_path.stat().st_mtime) - datetime.timedelta(days=2):] # only look at the new logs, plus 2 more days to account for timezone weirdness
    except:
        result = {}
        log = api.log.Log(world)
    # look for new join/leave lines
    for line in log:
        if line.type is api.log.LineType.join or line.type is api.log.LineType.leave:
            result[str(line.data['player'])] = line.data['time'].strftime('%Y-%m-%d %H:%M:%S')
    # write to cache
    if api.util.CONFIG['cache'].exists():
        if not cache_path.parent.exists():
            cache_path.parent.mkdir()
        with cache_path.open('w') as cache_f:
            json.dump(result, cache_f, sort_keys=True, indent=4)
    return result

@api.util2.json_route(application, '/world/<world>/status')
@api.util2.decode_args
def api_world_status(world: minecraft.World):
    """Returns JSON containing info about the given world, including whether the server is running, the current Minecraft version, and the list of people who are online. Requires mcstatus."""
    import mcstatus

    result = api.util2.short_world_status(world)
    server = mcstatus.MinecraftServer.lookup(api.util.CONFIG['worldHost'] if world.is_main else '{}.{}'.format(world, api.util.CONFIG['worldHost']))
    try:
        status = server.status()
    except ConnectionRefusedError:
        result['list'] = []
    else:
        result['list'] = [str(api.util2.Player(player.id)) for player in (status.players.sample or [])]
    return result

@api.util2.nbt_route(application, '/world/<world>/villages/<dimension>')
@api.util2.decode_args
def api_villages(world: minecraft.World, dimension: api.util2.Dimension):
    """Returns the villages.dat for the given dimension, encoded as JSON"""
    return world.world_path / 'data' / {
        api.util2.Dimension.overworld: 'villages.dat',
        api.util2.Dimension.nether: 'villages_nether.dat',
        api.util2.Dimension.end: 'villages_end.dat'
    }[dimension]

@api.util2.json_route(application, '/world/<world>/whitelist')
@api.util2.decode_args
def api_whitelist(world: minecraft.World):
    """Returns the whitelist."""
    with (world.path / 'whitelist.json').open() as whitelist:
        return json.load(whitelist)

@api.util2.json_route(application, '/server/players')
def api_player_ids():
    """Returns an array of all known player IDs (Wurstmineberg IDs and Minecraft UUIDs)"""
    for player in api.util2.Player.all():
        yield str(player)

@api.util2.json_route(application, '/server/sessions/lastseen')
def api_sessions_last_seen_all():
    """Returns the last known session for each player, including the world name."""
    def read_timestamp(timestamp):
        return datetime.datetime.strptime(timestamp, '%Y-%m-%d %H:%M:%S').replace(tzinfo=datetime.timezone.utc)

    result = {}
    for world in minecraft.worlds():
        for player_id, timestamp in api_sessions_last_seen_world(world).items():
            if player_id not in result or read_timestamp(timestamp) > read_timestamp(result[player_id]['time']):
                    result[player_id] = {
                        'time': timestamp,
                        'world': world.name
                    }
    return result

@api.util2.json_route(application, '/server/worlds')
def api_worlds():
    """Returns an object mapping existing world names to short status summaries (like those returned by /world/&lt;world&gt;/status.json but without the lists of online players)"""
    return {world.name: api.util2.short_world_status(world) for world in minecraft.worlds()}
