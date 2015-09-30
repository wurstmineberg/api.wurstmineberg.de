import datetime
import enum
import gzip
import minecraft
import re
import uuid

import api.util
import api.util2

LineType = enum.Enum('LineType', [
    'achievement', # player earns an achievement
    'chat_action', # /me
    'chat_message',
    'gibberish', # cannot parse timestamp, origin thread, and/or log level
    'join', # player joins the game
    'leave', # player leaves the game
    'unknown' # can parse timestamp, origin thread, and log level, but the rest of the message is not in a known format
], module=__name__)

class Line:
    def __init__(self, line_type, **kwargs):
        self.type = line_type
        self.data = kwargs

    def as_json(self):
        def value_as_json(value):
            if isinstance(value, api.util2.Player):
                return str(value)
            if isinstance(value, datetime.datetime):
                return value.strftime('%Y-%m-%d %H:%M:%S')
            if isinstance(value, str):
                return value
            return repr(value)

        result = {'type': self.type.name}
        result.update({key: value_as_json(value) for key, value in self.data.items()})
        return result

class Log:
    def __init__(self, world, *, files=None, reversed=False):
        if isinstance(world, str):
            world = minecraft.World(world)
        if isinstance(world, minecraft.World):
            self.world = world
        else:
            raise TypeError('Invalid world type')
        self.log_files = files
        self.reversed = reversed

    def __iter__(self):
        def iter_file(log_file):
            player_uuids = {}
            for raw_line in self.raw_lines(log_file, yield_reversed=False):
                if raw_line == '':
                    continue
                match_prefix = '({}) {} '.format(Regexes.full_timestamp, Regexes.prefix)
                base_match = re.fullmatch(match_prefix + '(.*)', raw_line)
                if base_match:
                    # has a well-formatted timestamp, origin thread and log level
                    timestamp, origin_thread, log_level, text = base_match.group(1, 2, 3, 4)
                    time = datetime.datetime.strptime(timestamp, '%Y-%m-%d %H:%M:%S').replace(tzinfo=datetime.timezone.utc)
                    if origin_thread == 'Server thread':
                        if log_level == 'INFO':
                            matches = {
                                'achievement': '(' + Regexes.minecraft_nick + ') has just earned the achievement \\[(.+)\\]',
                                'chat_action': '\\* (' + Regexes.minecraft_nick + ') (.*)',
                                'chat_message': '<(' + Regexes.minecraft_nick + ')> (.*)',
                                'join_leave': '(' + Regexes.minecraft_nick + ') (joined|left) the game'
                            }
                            for match_type, match_string in matches.items():
                                match = re.fullmatch(match_prefix + match_string, raw_line)
                                if not match:
                                    continue # not the type of message currently being tested for
                                if match.group(4) in player_uuids:
                                    player = player_uuids[match.group(4)]
                                else:
                                    player = player_uuids[match.group(4)] = api.util2.Player.by_minecraft_nick(match.group(4), at=time)
                                if match_type == 'achievement':
                                    yield Line(LineType.achievement, time=time, player=player, achievement=match.group(5))
                                    break
                                elif match_type == 'chat_action':
                                    yield Line(LineType.chat_action, time=time, player=player, message=match.group(5))
                                    break
                                elif match_type == 'chat_message':
                                    yield Line(LineType.chat_message, time=time, player=player, message=match.group(5))
                                    break
                                elif match_type == 'join_leave':
                                    yield Line(LineType.join if match.group(5) == 'joined' else LineType.leave, time=time, player=player)
                                    break
                            else:
                                yield Line(LineType.unknown, time=time, origin_thread=origin_thread, log_level=log_level, text=text)
                        else:
                            yield Line(LineType.unknown, time=time, origin_thread=origin_thread, log_level=log_level, text=text)
                    elif origin_thread.startswith('User Authenticator'):
                        if log_level == 'INFO':
                            match = re.fullmatch(match_prefix + 'UUID of player ({}) is ({})'.format(Regexes.minecraft_nick, Regexes.uuid), raw_line)
                            if match:
                                player_uuids[match.group(4)] = api.util2.Player(match.group(5))
                            else:
                                yield Line(LineType.unknown, time=time, origin_thread=origin_thread, log_level=log_level, text=text)
                        else:
                            yield Line(LineType.unknown, time=time, origin_thread=origin_thread, log_level=log_level, text=text)
                    else:
                        yield Line(LineType.unknown, time=time, origin_thread=origin_thread, log_level=log_level, text=text)
                else:
                    yield Line(LineType.gibberish, text=raw_line)

        for log_file in self.files:
            if self.reversed:
                yield from reversed(list(iter_file(log_file)))
            else:
                yield from iter_file(log_file)

    def __reversed__(self):
        return self.__class__(self.world, files=reversed(self.files), reversed=not self.reversed)

    @property
    def files(self):
        if self.log_files is not None:
            self.log_files = []
            if (self.world.path / 'server.log').exists():
                self.log_files.append(self.world.path / 'server.log')
            for log_path in sorted((self.world.path / 'logs').iterdir()):
                if log_path.name != 'latest.log':
                    self.log_files.append(log_path)
            self.log_files.append(self.world.path / 'logs' / 'latest.log')
        yield from self.log_files

    @classmethod
    def latest(cls, world):
        return cls(world, files=(world.path / 'logs' / 'latest.log'))

    def raw_lines(self, files=None, *, yield_reversed=None):
        if files is None:
            files = self.files
        elif isinstance(files, pathlib.Path):
            files = [files]
        if yield_reversed is None:
            yield_reversed = self.reversed
        for log_path in files:
            if log_path.name != 'latest.log':
                if log_path.suffix == '.gz':
                    open_func = lambda path: gzip.open(str(path))
                else:
                    open_func = lambda path: path.open()
                with open_func(log_path) as log:
                    for line in (reversed(list(log)) if yield_reversed else log):
                        if not isinstance(line, str):
                            line = line.decode('utf-8')
                        yield line.rstrip('\r\n')

class Regexes:
    full_timestamp = '[0-9]{4}-[0-9]{2}-[0-9]{2} [0-9]{2}:[0-9]{2}:[0-9]{2}'
    minecraft_nick = '[A-Za-z0-9_]{1,16}'
    old_timestamp = '\\[[0-9]{2}:[0-9]{2}:[0-9]{2}\\]'
    prefix = '\\[(.+?)/(.+?)\\]:?'
    uuid = '[0-9A-Fa-f]{8}-?[0-9A-Fa-f]{4}-?[0-9A-Fa-f]{4}-?[0-9A-Fa-f]{4}-?[0-9A-Fa-f]{12}'
