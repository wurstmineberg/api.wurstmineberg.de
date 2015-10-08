import datetime
import enum
import gzip
import minecraft
import pathlib
import re

import api.util2

class Regexes:
    full_prefix = '\\[(.+?)/(.+?)\\]:?'
    timestamp = '[0-9]{4}-[0-9]{2}-[0-9]{2} [0-9]{2}:[0-9]{2}:[0-9]{2}'
    minecraft_nick = '[A-Za-z0-9_]{1,16}'
    old_prefix = '\\[(.+?)\\]:?'
    uuid = '[0-9A-Fa-f]{8}-?[0-9A-Fa-f]{4}-?[0-9A-Fa-f]{4}-?[0-9A-Fa-f]{4}-?[0-9A-Fa-f]{12}'

death_messages = (
    'blew up',
    'burned to death',
    'drowned',
    'drowned whilst trying to escape .*',
    'fell from a high place',
    'fell from a high place and fell out of the world',
    'fell into a patch of cacti',
    'fell into a patch of fire',
    'fell off a ladder',
    'fell off some vines',
    'fell out of the water',
    'fell out of the world',
    'got finished off by .*',
    'got finished off by .* using .*',
    'hit the ground too hard',
    'starved to death',
    'suffocated in a wall',
    'tried to swim in lava',
    'tried to swim in lava while trying to escape .*',
    'walked into a cactus while trying to escape .*',
    'walked into a fire whilst fighting .*',
    'was blown from a high place by .*',
    'was blown up by .*',
    'was burnt to a crisp whilst fighting .*',
    'was doomed to fall by .*',
    'was fireballed by .*',
    'was killed by .* using magic',
    'was killed by magic',
    'was killed while trying to hurt .*',
    'was pricked to death',
    'was pummeled by .*',
    'was shot by .*',
    'was shot off a ladder by .*',
    'was shot off some vines by .*',
    'was slain by .*',
    'was slain by .* using .*',
    'was squashed by a falling anvil',
    'was squashed by a falling block',
    'was struck by lightning',
    'went up in flames',
    'withered away'
) # http://minecraft.gamepedia.com/Health#Death_messages

LineType = enum.Enum('LineType', [
    'achievement', # player earns an achievement
    'chat_action', # /me
    'chat_message',
    'death', # known type of death message
    'gibberish', # cannot parse prefix
    'join', # player joins the game
    'leave', # player leaves the game
    'start', # server start
    'stop', # server stop
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

    def __getitem__(self, key):
        if not isinstance(key, slice):
            raise TypeError('Invalid key: expected a slice, got {!r}'.format(key))
        if key.step is not None:
            raise ValueError('Step not supported')
        files = []
        for log_path in self.files:
            try:
                date = datetime.date(*map(int, log_path.stem[:len('9999-99-99')].split('-')))
            except ValueError:
                date = None
            if date is None:
                if log_path.stem == 'server':
                    # server.log
                    if key.start is not None:
                        continue
                else:
                    # latest.log
                    if key.stop is not None:
                        continue
            else:
                if key.start is not None and key.start > date:
                    continue
                if key.stop is not None and key.stop <= date:
                    continue
            files.append(log_path)
        return self.__class__(self.world, files=files, reversed=self.is_reversed)

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
                            'join_leave': '(' + Regexes.minecraft_nick + ') (joined|left) the game',
                            'start': 'Starting minecraft server version (.*)',
                            'stop': 'Stopping the server'
                        }
                        for match_type, match_string in matches.items():
                            match = re.fullmatch(match_string, text)
                            if not match:
                                continue # not the type of message currently being tested for
                            if match_type in ('achievement', 'chat_action', 'chat_message', 'join_leave'):
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
                            elif match_type == 'start':
                                yield Line(LineType.start, time=time, version=match.group(1))
                            elif match_type == 'stop':
                                yield Line(LineType.stop, time=time)
                            break
                        else:
                            for death_regex in death_messages:
                                match = re.fullmatch('(' + Regexes.minecraft_nick + ') (' + death_regex + ')', text)
                                if match:
                                    if match.group(1) in player_uuids:
                                        player = player_uuids[match.group(1)]
                                    else:
                                        player = player_uuids[match.group(1)] = api.util2.Player.by_minecraft_nick(match.group(1), at=time)
                                    yield Line(LineType.death, time=time, player=player, cause=match.group(2))
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
            if (self.world.path / 'logs').exists():
                for log_path in sorted((self.world.path / 'logs').iterdir()):
                    if log_path.name != 'latest.log':
                        self.log_files.append(log_path)
                if (self.world.path / 'logs' / 'latest.log').exists():
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
