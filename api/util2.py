import bottle
import datetime
import enum
import functools
import inspect
import io
import json
import minecraft
import nbt.nbt
import os.path
import pathlib
import random
import re
import requests
import time
import tempfile
import types
import uuid

import api.util

PLAYER_CACHE = {}

@enum.unique
class Dimension(enum.Enum):
    overworld = 0
    nether = -1
    end = 1

    def region_path(self, world):
        return world.world_path / {
            Dimension.overworld: 'region',
            Dimension.nether: 'DIM-1/region',
            Dimension.end: 'DIM1/region'
        }[self]

class Player:
    def __init__(self, player_id):
        if isinstance(player_id, str) and re.fullmatch('[a-z][0-9a-z]{1,15}', player_id):
            import people

            db = people.get_people_db()
            self.wurstmineberg_id = player_id
            self.data = db.obj_dump(version=3)['people'][self.wurstmineberg_id]
            self.uuid = None
        elif isinstance(player_id, uuid.UUID):
            self.uuid = player_id
            self.wurstmineberg_id = None
        else:
            try:
                self.uuid = uuid.UUID(player_id)
                self.wurstmineberg_id = None
            except Exception as e:
                raise ValueError('Invalid player ID: {}'.format(player_id)) from e
        if self.wurstmineberg_id is None:
            try:
                import people
            except ImportError:
                self.data = None
            else:
                db = people.get_people_db()
                for wurstmineberg_id, person_data in db.obj_dump(version=3)['people'].items():
                    if 'minecraft' in person_data:
                        if 'uuid' in person_data['minecraft']:
                            person_uuid = uuid.UUID(person_data['minecraft']['uuid'])
                        elif len(person_data['minecraft'].get('nicks', [])) > 0: # Minecraft UUID missing but Minecraft nick(s) present
                            person_uuid = uuid.UUID(requests.get('https://api.mojang.com/users/profiles/minecraft/{}'.format(person_data['minecraft']['nicks'][-1])).json()['id']) # get UUID from Mojang
                            db.person_set_key(wurstmineberg_id, 'minecraft.uuid', str(person_uuid)) # write back to people database
                        else:
                            continue
                        if person_uuid == self.uuid:
                            self.wurstmineberg_id = wurstmineberg_id
                            self.data = person_data
                            self.data['minecraft']['uuid'] = str(self.uuid) # make sure the UUID is included in the JSON data
                            break
                else:
                    names_response = requests.get('https://api.mojang.com/user/profiles/{}/names'.format(self.uuid.hex))
                    if names_response.status_code == 200:
                        self.data = PLAYER_CACHE[self.uuid] = {
                            'minecraft': {
                                'uuid': str(self.uuid),
                                'nicks': [name_info['name'] for name_info in names_response.json()]
                            }
                        }
                    elif names_response.status_code == 204:
                        profile = requests.get('https://sessionserver.mojang.com/session/minecraft/profile/{}'.format(self.uuid.hex)).json()
                        self.data = PLAYER_CACHE[self.uuid] = {
                            'minecraft': {
                                'uuid': str(self.uuid),
                                'nicks': [profile['name']]
                            }
                        }
                    elif names_response.status_code == 429:
                        if self.uuid in PLAYER_CACHE:
                            self.data = PLAYER_CACHE[self.uuid]
                        else:
                            raise RuntimeError('Rate limited by Mojang API but no profile cached for player with UUID {}'.format(self.uuid))
                    else:
                        raise NotImplementedError('Unimplemented response status: {}'.format(names_response.status_code))
        if self.uuid is None and 'minecraft' in self.data:
            if 'uuid' in self.data['minecraft']:
                self.uuid = uuid.UUID(self.data['minecraft']['uuid'])
            elif len(self.data['minecraft'].get('nicks', [])) > 0: # Minecraft UUID missing but Minecraft nick(s) present
                self.uuid = uuid.UUID(requests.get('https://api.mojang.com/users/profiles/minecraft/{}'.format(self.data['minecraft']['nicks'][-1])).json()['id']) # get UUID from Mojang
                db.person_set_key(self.wurstmineberg_id, 'minecraft.uuid', str(self.uuid)) # write back to people database
                self.data['minecraft']['uuid'] = str(self.uuid) # make sure the UUID is included in the JSON data

    def __eq__(self, other):
        if not isinstance(other, Player):
            return False
        if self.wurstmineberg_id is not None:
            return self.wurstmineberg_id == other.wurstmineberg_id
        return self.uuid == other.uuid

    def __hash__(self):
        if self.wurstmineberg_id is not None:
            return hash(self.wurstmineberg_id)
        return hash(self.uuid)

    def __str__(self):
        if self.wurstmineberg_id is None:
            return str(self.uuid)
        else:
            return self.wurstmineberg_id

    @classmethod
    def all(cls):
        """Yields all known players."""
        found = set()
        def find(person_id):
            person = cls(person_id)
            if person not in found:
                found.add(person)
                yield person

        # from people file
        try:
            import people
        except ImportError:
            pass # no people db
        else:
            for wurstmineberg_id in people.get_people_db().obj_dump(version=3)['people']:
                yield from find(wurstmineberg_id)
        # from player data files
        for world in minecraft.worlds():
            if (world.world_path / 'playerdata').exists():
                for player_path in (world.world_path / 'playerdata').iterdir():
                    if player_path.suffix == '.dat':
                        yield from find(player_path.stem)

    @classmethod
    def by_minecraft_nick(cls, minecraft_nick, at=None):
        if at is None:
            try:
                return cls(requests.get('https://api.mojang.com/users/profiles/minecraft/{}'.format(minecraft_nick)).json()['id'])
            except Exception as e:
                raise LookupError('Could not get player from Minecraft nick {!r}'.format(minecraft_nick)) from e
        else:
            try:
                return cls(requests.get('https://api.mojang.com/users/profiles/minecraft/{}?at={}'.format(minecraft_nick, int(at.timestamp()))).json()['id'])
            except Exception as e:
                raise LookupError('Could not get player from Minecraft nick {!r} at {:%Y-%m-%d %H:%M:%S}'.format(minecraft_nick, at)) from e

def nbtfile_to_dict(filename, *, add_metadata=True):
    """Generates a JSON-serializable value from a path (string or pathlib.Path) representing a NBT file.

    Keyword-only arguments:
    add_metadata -- If true, converts the result to a dict and adds the .apiTimeLastModified and .apiTimeResultFetched fields.
    """
    if isinstance(filename, pathlib.Path):
        filename = str(filename)
    nbt_file = nbt.nbt.NBTFile(filename)
    nbt_dict = nbt_to_dict(nbt_file)
    if add_metadata:
        if not isinstance(nbt_dict, dict):
            nbt_dict = {'data': nbt_dict}
        if 'apiTimeLastModified' not in nbt_dict:
            nbt_dict['apiTimeLastModified'] = os.path.getmtime(filename)
        if 'apiTimeResultFetched' not in nbt_dict:
            nbt_dict['apiTimeResultFetched'] = time.time()
    return nbt_dict

def nbt_to_dict(nbt_file):
    """Generates a JSON-serializable value from an nbt.nbt.NBTFile object."""
    dict = {}
    is_collection = False
    is_dict = False
    collection = []
    for tag in nbt_file.tags:
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

def short_world_status(world):
    """Returns an object in the format required for /server/worlds.json and /world/<world>/status.json (without the player list)"""
    return {
        'main': world.is_main,
        'running': world.status(),
        'version': world.version(),
        'whitelist': world.config['whitelist']
    }

def chunk_section_info(column, x, y, z):
    def nybble(data, idx):
        result = data[idx // 2]
        if idx % 2 == 0:
            return result & 15
        else:
            return result >> 4

    for section in column['Level']['Sections']:
        if section['Y'] == y:
            break
    else:
        section = None
    with (api.util.CONFIG['webAssets'] / 'json' / 'biomes.json').open() as biomes_file:
        biomes = json.load(biomes_file)
    with (api.util.CONFIG['webAssets'] / 'json' / 'items.json').open() as items_file:
        items = json.load(items_file)
    layers = []
    for layer in range(16):
        block_y = y * 16 + layer
        rows = []
        for row in range(16):
            block_z = z * 16 + row
            blocks = []
            for block in range(16):
                block_x = x * 16 + block
                block_info = {
                    'x': block_x,
                    'y': block_y,
                    'z': block_z
                }
                if 'Biomes' in column['Level']:
                    block_info['biome'] = biomes['biomes'][str(column['Level']['Biomes'][16 * row + block])]['id']
                if section is not None:
                    block_index = 256 * layer + 16 * row + block
                    block_id = section['Blocks'][block_index]
                    if 'Add' in section:
                        block_id += nybble(section['Add'], block_index) << 8
                    block_info['id'] = block_id
                    for plugin, plugin_items in items.items():
                        for item_id, item_info in plugin_items.items():
                            if 'blockID' in item_info and item_info['blockID'] == block_id:
                                block_info['id'] = '{}:{}'.format(plugin, item_id)
                                break
                    block_info['damage'] = nybble(section['Data'], block_index)
                    block_info['blockLight'] = nybble(section['BlockLight'], block_index)
                    block_info['skyLight'] = nybble(section['SkyLight'], block_index)
                blocks.append(block_info)
            rows.append(blocks)
        layers.append(rows)
    if 'Entities' in column['Level']:
        for entity in column['Level']['Entities']:
            if y * 16 <= entity['Pos'][1] < y * 16 + 16: # make sure the entity is in the right section
                block_info = layers[int(entity['Pos'][1]) & 15][int(entity['Pos'][2]) & 15][int(entity['Pos'][0]) & 15]
                if 'entities' not in block_info:
                    block_info['entities'] = []
                block_info['entities'].append(entity)
    if 'TileEntities' in column['Level']:
        for tile_entity in column['Level']['TileEntities']:
            if y * 16 <= tile_entity['y'] < y * 16 + 16: # make sure the entity is in the right section
                block_info = layers[tile_entity['y'] & 15][tile_entity['z'] & 15][tile_entity['x'] & 15]
                del tile_entity['x']
                del tile_entity['y']
                del tile_entity['z']
                if 'tileEntities' in block_info:
                    block_info['tileEntities'].append(tile_entity)
                elif 'tileEntity' in block_info:
                    block_info['tileEntities'] = [block_info['tileEntity'], tile_entity]
                    del block_info['tileEntity']
                else:
                    block_info['tileEntity'] = tile_entity
    return layers

def cached_image(cache_path, image_func, cache_check):
    if api.util.CONFIG['cache'].exists():
        image_path = api.util.CONFIG['cache'] / cache_path
        if cache_check(image_path):
            return bottle.static_file(image_path.name, str(image_path.parent), mimetype='image/png')
        else:
            if not image_path.parent.exists():
                image_path.parent.mkdir(parents=True)
            image_file = image_path.open('wb')
    else:
        image_file = tempfile.NamedTemporaryFile(suffix='.png', delete=False)
        image_path = pathlib.Path(image_file.name)
    with image_file:
        image = image_func()
        image.save(image_file, 'PNG')
    return bottle.static_file(image_path.name, str(image_path.parent), mimetype='image/png')

def skin_cache_check(image_path):
    if not image_path.exists():
        return False # image has not been rendered yet
    max_age = datetime.timedelta(hours=random.randrange(4, 8), minutes=random.randrange(0, 60)) # use a random value between 4 and 8 hours for the cache expiration check
    if datetime.datetime.utcfromtimestamp(image_path.stat().st_mtime) < datetime.datetime.utcnow() - max_age:
        return False # image is older than max_age
    return True

def decode_args(f):
    @functools.wraps(f)
    def decorated(*args, **kwargs):
        for param, arg in zip(inspect.signature(f).parameters.values(), args):
            if param.name not in kwargs:
                kwargs[param.name] = arg
        decoded_args = {}
        for param in inspect.signature(f).parameters.values():
            arg = kwargs[param.name]
            if param.kind is not inspect.Parameter.POSITIONAL_OR_KEYWORD:
                raise ValueError('The decode_args function only works for POSITIONAL_OR_KEYWORD parameters, but a {} parameter was found'.format(param.kind))
            if param.annotation is inspect.Parameter.empty or not isinstance(arg, str): # no annotation or a direct function call
                decoded_args[param.name] = arg
            elif param.annotation is Dimension:
                try:
                    int(arg)
                except:
                    decoded_args[param.name] = Dimension[arg]
                else:
                    decoded_args[param.name] = Dimension(int(arg))
            elif param.annotation is Player:
                decoded_args[param.name] = Player(arg)
            elif param.annotation is int:
                decoded_args[param.name] = int(arg)
            elif param.annotation is minecraft.World:
                decoded_args[param.name] = minecraft.World(arg)
            elif param.annotation == 'color':
                decoded_args[param.name] = (int(arg[:2], 16), int(arg[2:4], 16), int(arg[4:6], 16))
            elif isinstance(param.annotation, range):
                if int(arg) not in param.annotation:
                    bottle.abort(403, 'Parameter {} must be in {}'.format(param.name, param.annotation))
                decoded_args[param.name] = int(arg)
            else:
                raise TypeError('The decode_args function is not implemented for the argument type {:?}'.format(param.annotation))
        return f(**decoded_args)

    return decorated

def json_route(app, route):
    def decorator(f):
        @app.route(route + '.json')
        @functools.wraps(f)
        def json_encoded(*args, **kwargs):
            bottle.response.content_type = 'application/json'
            result = f(*args, **kwargs)
            if isinstance(result, types.GeneratorType):
                empty = True
                for value in result:
                    if empty:
                        yield '['
                        empty = False
                    else:
                        yield ','
                    yield '\n    '
                    yield '\n    '.join(json.dumps(value, sort_keys=True, indent=4).split('\n'))
                if empty:
                    yield '[]\n'
                else:
                    yield '\n]\n'
            else:
                yield json.dumps(result, sort_keys=True, indent=4)

        pass #TODO add HTML view endpoint
        return f

    return decorator

def nbt_route(app, route):
    def decorator(f):
        @functools.wraps(f)
        def nbt_filed(*args, **kwargs):
            result = f(*args, **kwargs)
            if isinstance(result, pathlib.Path):
                return nbt.nbt.NBTFile(str(result))
            elif isinstance(result, nbt.nbt.NBTFile):
                return result
            else:
                raise NotImplementedError('Cannot convert value of type {} to NBTFile'.format(type(result)))

        @app.route(route + '.json')
        @functools.wraps(f)
        def json_encoded(*args, **kwargs):
            bottle.response.content_type = 'application/json'
            result = f(*args, **kwargs)
            if isinstance(result, pathlib.Path):
                return json.dumps(nbtfile_to_dict(result), sort_keys=True, indent=4)
            elif isinstance(result, nbt.nbt.NBTFile):
                return json.dumps(nbt_to_dict(result), sort_keys=True, indent=4)
            else:
                raise NotImplementedError('Cannot convert value of type {} to JSON'.format(type(result)))

        @app.route(route + '.nbt')
        @functools.wraps(f)
        def raw_nbt(*args, **kwargs):
            result = f(*args, **kwargs)
            if isinstance(result, pathlib.Path):
                return bottle.static_file(result.name, str(result.parent), mimetype='application/x-minecraft-nbt')
            elif isinstance(result, nbt.nbt.NBTFile):
                buf = io.BytesIO()
                result.write_file(fileobj=buf)
                return buf
            else:
                raise NotImplementedError('Cannot convert value of type {} to NBT'.format(type(result)))

        pass #TODO add HTML view endpoint
        return nbt_filed

    return decorator
