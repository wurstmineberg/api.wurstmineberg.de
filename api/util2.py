import api.util
import bottle
import datetime
import functools
import inspect
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
import uuid

class Player:
    def __init__(self, player_id):
        if re.fullmatch('[a-z][0-9a-z]{1,15}', player_id):
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
                    self.data = None
        if self.uuid is None and 'minecraft' in self.data:
            if 'uuid' in self.data['minecraft']:
                self.uuid = uuid.UUID(self.data['minecraft']['uuid'])
            elif len(self.data['minecraft'].get('nicks', [])) > 0: # Minecraft UUID missing but Minecraft nick(s) present
                self.uuid = uuid.UUID(requests.get('https://api.mojang.com/users/profiles/minecraft/{}'.format(self.data['minecraft']['nicks'][-1])).json()['id']) # get UUID from Mojang
                db.person_set_key(self.wurstmineberg_id, 'minecraft.uuid', str(self.uuid)) # write back to people database
                self.data['minecraft']['uuid'] = str(self.uuid) # make sure the UUID is included in the JSON data

    def __str__(self):
        if self.wurstmineberg_id is None:
            return str(self.uuid)
        else:
            return self.wurstmineberg_id

def all_players(): #TODO change to use Wurstmineberg/Minecraft IDs
    """Returns all known player IDs (Wurstmineberg IDs and Minecraft UUIDs)"""
    try:
        data = [entry['name'] for entry in json.loads(api_whitelist())]
    except:
        data = []
    directory = os.path.join(config('serverDir'), config('worldName'), 'players') #TODO multiworld
    for root, dirs, files in os.walk(directory):
        for file in files:
            if file.endswith('.dat'):
                name = os.path.splitext(file)[0]
                data.append(name)
    return data

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

def decode_args(f):
    @functools.wraps(f)
    def decorated(**kwargs):
        decoded_args = {}
        for param in inspect.signature(f).parameters.values():
            arg = kwargs[param.name]
            if param.kind is not inspect.Parameter.POSITIONAL_OR_KEYWORD:
                raise ValueError('The decode_args function only works for POSITIONAL_OR_KEYWORD parameters, but a {} parameter was found'.format(param.kind))
            if param.annotation is inspect.Parameter.empty or not isinstance(arg, str): # no annotation or a direct function call
                decoded_args[param.name] = arg
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
        def json_encoded(**kwargs):
            bottle.response.content_type = 'application/json'
            return json.dumps(f(**kwargs), sort_keys=True, indent=4)

        pass #TODO add HTML view endpoint
        return f

    return decorator
