# -*- coding: utf-8 -*-

# TODO
# add an override_config method
# better exception in __getitem__

import ConfigParser
import json
import os
import yaml


class ConfigurationError(RuntimeError):
    pass


class Config(dict):
    """
    A Config is a subclass of dict whose values are simple python objects (strings, integers, booleans or floats),
    or lists, or recursively dicts whose values are simple python objects or lists, or ...
    Keys are strings, and can be expressed as chains of keys separated by dots,
    eg c.get('section.subsection.option') is roughly the same as c.get('section').get('subsection').get('option')
    salted with appropriate exception handling and default value management.
    For Yaml formatted files, non leaf elements are always dicts, only leaf elements can be lists.
    """
    _boolean_states = {'yes': True, 'true': True, 'on': True,
                       'no': False, 'false': False, 'off': False}

    @classmethod
    def add_bool_literals(cls, true, false):
        cls._boolean_states[true] = True
        cls._boolean_states[false] = False

    def __getitem__(self, key):
        r = self
        for k in key.split('.'):
            r = dict.__getitem__(r, k)
        return r

    def get(self, k, d=None):
        try:
            return self[k]
        except KeyError:
            return d

    def get_int(self, k, d=0):
        try:
            return int(self.get(k, d))
        except TypeError:
            if d == 'raise':
                raise ValueError('Not a leaf or not an integer: %s' % k)
            return d

    def get_float(self, k, d=0.0):
        try:
            return float(self.get(k, d))
        except TypeError:
            if d == 'raise':
                raise ValueError('Not a leaf or not a float: %s' % k)
            return d

    def get_boolean(self, k, d=False):
        v = self.get(k, d)
        if isinstance(v, bool):
            return v
        try:
            return self._boolean_states[v.lower()]
        except (KeyError, AttributeError):
            if d == 'raise':
                raise ValueError('Not a leaf or not a boolean: %s' % k)
            return d
    get_bool = get_boolean

    def get_json(self, k, d='[]'):
        """ use only to get a list from an ini config file
            use syntax: ["a","b"] (double quotes mandatory)
        """
        try:
            return json.loads(self.get(k, d))
        except ValueError:
            return json.loads(d)


def yaml_parser(file):
    with open(file, 'r') as f:
        return Config(yaml.safe_load(f))


def ini_parser(file):
    # don't need OrderedDict
    cp = ConfigParser.RawConfigParser(dict_type=dict)
    with open(file, 'r') as f:
        cp._read(f, file)
    # remove some stuff
    for s in cp._sections.itervalues():
        del s['__name__']
    return Config(cp._sections)


def json_parser(file):
    with open(file, 'r') as f:
        return Config(json.loads(f))

parsers_dict = dict(
    yaml=yaml_parser,
    ini=ini_parser,
    conf=ini_parser,
    json=json_parser
)

parsers_set = {yaml_parser, ini_parser, json_parser}


class CachedConfigReader(object):
    """
    Implements configuration reading with features:
    - configurable parser. By order of priority:
      1- explicitly specified in read_config(),
      2- use file extension,
      3- specified in first comment line of config file,
      4- instance default parser,
      5- class default parser
    - two levels instance caching:
      CachedConfigReader.get_instance(dir) returns a config reader instance for the specified directory,
      (one directory == one instance).
      read_config(config_file) reads and cache the specified config file as a mapping object.
    """
    dir_cache = {}
    default_parser = yaml_parser

    def __init__(self, config_dir, parser):
        self.config_dir = config_dir
        self.default_parser = self.get_parser(parser)
        self.cache = {}

    @classmethod
    def get_instance(cls, config_dir, parser=None):
        path = os.path.abspath(config_dir)
        if path not in cls.dir_cache:
            cls.dir_cache[path] = CachedConfigReader(path, parser)
        return cls.dir_cache[path]

    def get_parser(self, parser):
        if parser is None:
            return self.default_parser
        if parser in parsers_set:
            return parser
        return parsers_dict[parser]

    def get_parser_from_file(self, path):
        parser = self.default_parser
        try:
            # try to get parser from file extension
            parser = parsers_dict[path.rsplit('.', 1)[1]]
        except (KeyError, IndexError):
            # else try to guess parser from first comment line
            with open(path, 'r') as f:
                first_line = f.readline().lower()
            if first_line.startswith('#'):
                for k, v in parsers_dict.iteritems():
                    if k in first_line:
                        parser = v
                        break
        return parser

    def read_config(self, config, parser=None, default={}):
        """ reads and parse the config file, or get the cached configuration if available
            you can specify default='raise' to raise an exception on missing fileparser
        """
        if config not in self.cache:
            path = os.path.join(self.config_dir, config)
            try:
                if parser:
                    parser = self.get_parser(parser)
                else:
                    parser = self.get_parser_from_file(path)
                self.cache[config] = parser(path)
            except IOError:
                if default == 'raise':
                    raise ConfigurationError("Configuration file not found: %s", path)
                self.cache[config] = Config(default)

        return self.cache[config]

    def reload(self, config=None):
        if config:
            del self.cache[config]
        else:
            self.cache = {}
    reset = clear = reload