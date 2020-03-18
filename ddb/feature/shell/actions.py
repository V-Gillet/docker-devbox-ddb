# -*- coding: utf-8 -*-
import base64
import json
import os

import zgitignore
from dictdiffer import diff

from .integrations import ShellIntegration
from ...action import Action
from ...config import config

_env_environ_backup = config.env_prefix + "_SHELL_ENVIRON_BACKUP"


def encode_environ_backup(environ_backup: dict) -> str:
    """
    Encode environ backup into a safe string.
    """
    return base64.b64encode(json.dumps(environ_backup).encode("utf-8")).decode("utf-8")


def decode_environ_backup(encoded_environ_backup: str) -> dict:
    """
    Decode environ backup from safe string.
    """
    return json.loads(base64.b64decode(encoded_environ_backup).decode("utf-8"))


def apply_diff_to_shell(shell: ShellIntegration, source_environment: dict, target_environment: dict, envignore=None):
    """
    Compute and apply environment diff for given shell.
    """
    variables = []

    for (action, source, dest_items) in diff(source_environment, target_environment):
        if action == 'add':
            for (key, value) in dest_items:
                variables.append((key, value))
        if action == 'change':
            variables.append((source, dest_items[1]))
        if action == 'remove':
            for (key, value) in dest_items:
                variables.append((key, None))

    envignore_helper = None
    if envignore:
        envignore_helper = zgitignore.ZgitIgnore(envignore)

    for key, value in sorted(variables, key=lambda variable: variable[0]):
        if not envignore_helper or not envignore_helper.is_ignored(key):
            if value is None:
                shell.remove_environment_variable(key)
            else:
                shell.set_environment_variable(key, value)


def add_to_system_path(shell: ShellIntegration, path: str):
    """
    Add given path to system PATH environment variable
    """
    system_path = os.environ.get('PATH', '')
    if config.data.get('shell.path.prepend'):
        system_path = path + os.pathsep + system_path
    else:
        system_path = system_path + os.pathsep + path

    shell.set_environment_variable('PATH', system_path)


class ActivateAction(Action):
    """
    Generates activation script
    """

    def __init__(self, shell: ShellIntegration):
        self.shell = shell

    @property
    def event_name(self) -> str:
        return "phase:print-activate"

    @property
    def name(self) -> str:
        return "shell:" + self.shell.name + ":activate"

    @property
    def description(self) -> str:
        return super().description + " for " + self.shell.description

    @property
    def disabled(self) -> bool:
        return config.data.get('shell.shell') != self.shell.name

    @property
    def order(self) -> int:
        return -256

    def execute(self, *args, **kwargs):
        initial_environ = dict(os.environ.items())
        config_environ = config.to_environ()

        to_encode_environ = dict(initial_environ)
        os.environ.update(config_environ)
        os.environ[_env_environ_backup] = encode_environ_backup(to_encode_environ)
        os.environ[config.env_prefix + '_PROJECT_HOME'] = config.paths.project_home

        apply_diff_to_shell(self.shell, initial_environ, os.environ, config.data.get('shell.envignore'))

        path_directories = config.data.get('shell.path.directories')
        if path_directories:
            for path_addition in path_directories:
                add_to_system_path(self.shell, os.path.normpath(os.path.join(os.getcwd(), path_addition)))


class DeactivateAction(Action):
    """
    Generations deactivation script
    """

    def __init__(self, shell: ShellIntegration):
        self.shell = shell

    @property
    def event_name(self) -> str:
        return "phase:print-deactivate"

    @property
    def name(self) -> str:
        return "shell:" + self.shell.name + ":deactivate"

    @property
    def description(self) -> str:
        return super().description + " for " + self.shell.description

    @property
    def disabled(self) -> bool:
        return config.data.get('shell.shell') != self.shell.name

    def execute(self, *args, **kwargs):
        if os.environ.get(_env_environ_backup):
            environ_backup = decode_environ_backup(os.environ[_env_environ_backup])
            apply_diff_to_shell(self.shell, os.environ, environ_backup, config.data.get('shell.envignore'))
