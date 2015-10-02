import datetime
import enum
import gzip
import minecraft
import pathlib
import re
import uuid

import api.util
import api.util2

LineType = enum.Enum('LineType', [
    'achievement', # player earns an achievement
    'chat_action', # /me
    'chat_message',
    'gibberish', # cannot parse prefix
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
            if value is None:
                return value
            if isinstance(value, api.util2.Player):
                return str(value)
            if isinstance(value, bool):
                return value
            if isinstance(value, datetime.datetime):
                return value.strftime('%Y-%m-%d %H:%M:%S')
            if isinstance(value, pathlib.Path):
                return str(value)
            if isinstance(value, str):
                return value
            return repr(value)

        result = {'type': self.type.name}
        result.update({key: value_as_json(value) for key, value in self.data.items()})
        return result

class Log:
    def __init__(self, world=None, *, files=None, reversed=False):
        if world is None:
            world = minecraft.World()
        if isinstance(world, str):
            world = minecraft.World(world)
        if isinstance(world, minecraft.World):
            self.world = world
        else:
            raise TypeError('Invalid world type')
        self.log_files = files
        self.is_reversed = reversed

    def __iter__(self):
        def iter_file(log_file, player_uuids=None):
            if player_uuids is None:
                player_uuids = {}
            for raw_line in self.raw_lines(log_file, yield_reversed=False):
                if raw_line == '':
                    continue
                prefixes = [
                    ('full', Regexes.full_prefix),
                    ('old', Regexes.old_prefix)
                ]
                for prefix_type, prefix_string in prefixes:
                    match_prefix = '({}) {} (.*)'.format(Regexes.timestamp, prefix_string)
                    base_match = re.fullmatch(match_prefix, raw_line)
                    if not base_match:
                        continue
                    if prefix_type == 'full':
                        # has a well-formatted timestamp, origin thread and log level
                        timestamp, origin_thread, log_level, text = base_match.group(1, 2, 3, 4)
                        time = datetime.datetime.strptime(timestamp, '%Y-%m-%d %H:%M:%S').replace(tzinfo=datetime.timezone.utc)
                    elif prefix_type == 'old':
                        # has a well-formatted timestamp and log level, but no origin thread
                        timestamp, log_level, text = base_match.group(1, 2, 3)
                        origin_thread = None
                        time = datetime.datetime.strptime(timestamp, '%Y-%m-%d %H:%M:%S').replace(tzinfo=datetime.timezone.utc)
                    break
                else:
                    yield Line(LineType.gibberish, path=log_file, text=raw_line)
                    continue
                if origin_thread == 'Server thread' or origin_thread is None:
                    if log_level == 'INFO':
                        matches = {
                            'achievement': '(' + Regexes.minecraft_nick + ') has just earned the achievement \\[(.+)\\]',
                            'chat_action': '\\* (' + Regexes.minecraft_nick + ') (.*)',
                            'chat_message': '<(' + Regexes.minecraft_nick + ')> (.*)',
                            'join_leave': '(' + Regexes.minecraft_nick + ') (joined|left) the game'
                        }
                        for match_type, match_string in matches.items():
                            match = re.fullmatch(match_string, text)
                            if not match:
                                continue # not the type of message currently being tested for
                            if match.group(1) in player_uuids:
                                player = player_uuids[match.group(1)]
                            else:
                                player = player_uuids[match.group(1)] = api.util2.Player.by_minecraft_nick(match.group(1), at=time)
                            if match_type == 'achievement':
                                yield Line(LineType.achievement, time=time, player=player, achievement=match.group(2))
                            elif match_type == 'chat_action':
                                yield Line(LineType.chat_action, time=time, player=player, message=match.group(2))
                            elif match_type == 'chat_message':
                                yield Line(LineType.chat_message, time=time, player=player, message=match.group(2))
                            elif match_type == 'join_leave':
                                yield Line(LineType.join if match.group(2) == 'joined' else LineType.leave, time=time, player=player)
                            break
                        else:
                            yield Line(LineType.unknown, time=time, origin_thread=origin_thread, log_level=log_level, text=text)
                    else:
                        yield Line(LineType.unknown, time=time, origin_thread=origin_thread, log_level=log_level, text=text)
                elif origin_thread.startswith('User Authenticator'):
                    if log_level == 'INFO':
                        match = re.fullmatch('UUID of player ({}) is ({})'.format(Regexes.minecraft_nick, Regexes.uuid), text)
                        if match:
                            player_uuids[match.group(1)] = api.util2.Player(match.group(2))
                        else:
                            yield Line(LineType.unknown, time=time, origin_thread=origin_thread, log_level=log_level, text=text)
                    else:
                        yield Line(LineType.unknown, time=time, origin_thread=origin_thread, log_level=log_level, text=text)
                else:
                    yield Line(LineType.unknown, time=time, origin_thread=origin_thread, log_level=log_level, text=text)

        for log_file in self.files:
            if self.is_reversed:
                yield from reversed(list(iter_file(log_file)))
            else:
                player_uuids = {}
                yield from iter_file(log_file, player_uuids=player_uuids)

    def reversed(self):
        return self.__class__(self.world, files=reversed(self.files), reversed=not self.is_reversed)

    @property
    def files(self):
        if self.log_files is None:
            self.log_files = []
            if (self.world.path / 'server.log').exists():
                self.log_files.append(self.world.path / 'server.log')
            for log_path in sorted((self.world.path / 'logs').iterdir()):
                if log_path.name != 'latest.log':
                    self.log_files.append(log_path)
            self.log_files.append(self.world.path / 'logs' / 'latest.log')
        return self.log_files

    @classmethod
    def latest(cls, world=None):
        if world is None:
            world = minecraft.World()
        return cls(world, files=[world.path / 'logs' / 'latest.log'])

    def raw_lines(self, files=None, *, yield_reversed=None):
        if files is None:
            files = self.files
        elif isinstance(files, pathlib.Path):
            files = [files]
        if yield_reversed is None:
            yield_reversed = self.is_reversed
        for log_path in files:
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
    full_prefix = '\\[(.+?)/(.+?)\\]:?'
    timestamp = '[0-9]{4}-[0-9]{2}-[0-9]{2} [0-9]{2}:[0-9]{2}:[0-9]{2}'
    minecraft_nick = '[A-Za-z0-9_]{1,16}'
    old_prefix = '\\[(.+?)\\]:?'
    uuid = '[0-9A-Fa-f]{8}-?[0-9A-Fa-f]{4}-?[0-9A-Fa-f]{4}-?[0-9A-Fa-f]{4}-?[0-9A-Fa-f]{12}'
