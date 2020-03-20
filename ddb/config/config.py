# -*- coding: utf-8 -*-
import os
from collections import namedtuple
from os.path import exists
from pathlib import Path
from typing import Callable, Any, Union

import yaml
from deepmerge import always_merger
from dotty_dict import dotty, Dotty
from marshmallow import Schema

ConfigPaths = namedtuple('ConfigPaths', ['ddb_home', 'home', 'project_home'])


def get_default_config_paths(env_prefix) -> ConfigPaths:
    """
    Get configuration paths
    """
    project_home = os.environ.get(env_prefix + '_PROJECT_HOME', os.getcwd())
    home = os.environ.get(env_prefix + '_HOME', os.path.join(str(Path.home()), '.docker-devbox'))
    ddb_home = os.environ.get(env_prefix + '_DDB_HOME', os.path.join(home, 'ddb'))

    return ConfigPaths(ddb_home=ddb_home, home=home, project_home=project_home)


class Config:
    """
    Configuration
    """

    def __init__(self,
                 paths: Union[ConfigPaths, None] = None,
                 env_prefix='DDB',
                 env_override_prefix='DDB_OVERRIDE',
                 filenames=('ddb', 'ddb.local'),
                 extensions=('yml', 'yaml')):
        self.env_prefix = env_prefix
        self.env_override_prefix = env_override_prefix
        self.filenames = filenames
        self.extensions = extensions
        self.data = dotty()
        self.paths = paths if paths else get_default_config_paths(env_prefix)

    def reset(self, *args, **kwargs):
        """
        Reset the configuration object.
        """
        self.__init__(*args, **kwargs)

    def clear(self):
        """
        Remove all configuration data.
        """
        self.data.clear()

    def load(self, env_key='env'):
        """
        Load configuration data. Variable in 'env_key' key will be placed loaded as environment variables.
        """
        loaded_data = {}

        for path in self.paths:
            if not path:
                continue
            for basename in self.filenames:
                for ext in self.extensions:
                    file = os.path.join(path, basename + '.' + ext)
                    if exists(file):
                        with open(file, 'rb') as stream:
                            file_data = yaml.load(stream, Loader=yaml.FullLoader)
                            if file_data:
                                loaded_data = always_merger.merge(loaded_data, file_data)

        if env_key in loaded_data:
            env = loaded_data.pop(env_key)
            if env:
                for (name, value) in env.items():
                    os.environ[name] = value

        loaded_data = self.apply_environ_overrides(loaded_data)
        self.data = dotty(always_merger.merge(self.data, loaded_data))

    def to_environ(self) -> dict:
        """
        Export configuration to environment dict.
        """
        return self.flatten(self.env_prefix, "_", "_%s_", str.upper, str)

    def flatten(self, prefix=None, sep=".", array_index_format="[%s]",
                key_transformer=None, value_transformer=None,
                stop_for=(), data=None, output=None) -> dict:
        """
        Export configuration to a flat dict.
        """
        if output is None:
            output = dict()

        if data is None:
            data = dict(self.data)
        if prefix is None:
            prefix = ""
        if key_transformer is None:
            key_transformer = lambda x: x
        if value_transformer is None:
            value_transformer = lambda x: x

        stop_recursion = False
        if prefix in stop_for:
            stop_recursion = True

        if not stop_recursion and isinstance(data, dict):
            for (name, value) in data.items():
                key_prefix = (prefix + sep if prefix else "") + key_transformer(name)
                key_prefix = key_transformer(key_prefix)

                self.flatten(key_prefix, sep, array_index_format,
                             key_transformer, value_transformer,
                             stop_for, value, output)

        elif not stop_recursion and isinstance(data, list):
            i = 0
            for value in data:
                replace_prefix = (prefix if prefix else "") + (array_index_format % str(i))
                replace_prefix = key_transformer(replace_prefix)

                self.flatten(replace_prefix, sep, array_index_format,
                             key_transformer, value_transformer,
                             stop_for, value, output)

                i += 1
        else:
            output[prefix] = value_transformer(data)

        return output

    def sanitize_and_validate(self, schema: Schema, key: str, auto_configure: Callable[[Dotty], Any] = None):
        """
        Sanitize and validate using given schema part of the configuration given by configuration key.
        """

        raw_feature_config = self.data.get(key)

        if not raw_feature_config:
            raw_feature_config = {}
        feature_config = schema.dump(raw_feature_config)

        feature_config = self.apply_environ_overrides(feature_config, self.env_override_prefix + "_" + key)
        feature_config = schema.dump(feature_config)

        if auto_configure:
            auto_configure(dotty(feature_config))

        feature_config = schema.load(feature_config)
        self.data[key] = feature_config

    def apply_environ_overrides(self, data, prefix=None):
        """
        Apply environment variables to configuration.
        """
        if not prefix:
            prefix = self.env_override_prefix
        prefix = prefix.upper()

        environ_value = os.environ.get(prefix)
        if environ_value:
            return environ_value

        if isinstance(data, dict):
            for (name, value) in data.items():
                key_prefix = prefix + "_" + name
                key_prefix = key_prefix.upper()

                data[name] = self.apply_environ_overrides(value, key_prefix)
        if isinstance(data, list):
            i = 0
            for value in data:
                replace_prefix = prefix + "[" + str(i) + "]"
                replace_prefix = replace_prefix.upper()

                environ_value = os.environ.get(replace_prefix)
                if environ_value:
                    data[i] = self.apply_environ_overrides(value, replace_prefix)

                i += 1

        return data
