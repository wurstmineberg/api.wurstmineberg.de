import json
import nbt.nbt
import os.path
import pathlib
import time

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
