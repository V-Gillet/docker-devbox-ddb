# -*- coding: utf-8 -*-
import json
import os
import re
import shlex
from collections import namedtuple
from stat import S_IWUSR
from typing import Iterable

import docker
from dockerfile_parse import DockerfileParser
from dotty_dict import Dotty

from ..copy.actions import copy_from_url
from ...action import Action
from ...action.action import EventBinding
from ...cache import global_cache
from ...config import config
from ...context import context
from ...event import bus

BuildServiceDef = namedtuple("BuildServiceDef", "context dockerfile")


class CustomDockerfileParser(DockerfileParser):
    """
    Custom class to implement entrypoint property with the same behavior as cmd property.
    """

    def get_last_instruction(self, instruction_type):
        """
        Determine the final instruction_type instruction, if any, in the final build stage.
        instruction_types from earlier stages are ignored.
        :return: value of final stage instruction_type instruction
        """
        last_instruction = None
        for insndesc in self.structure:
            if insndesc['instruction'] == 'FROM':  # new stage, reset
                last_instruction = None
            elif insndesc['instruction'] == instruction_type:
                last_instruction = insndesc
        return last_instruction

    @property
    def entrypoint(self):
        """
        Determine the final ENTRYPOINT instruction, if any, in the final build stage.
        ENTRYPOINTs from earlier stages are ignored.
        :return: value of final stage ENTRYPOINT instruction
        """
        last_instruction = self.get_last_instruction("ENTRYPOINT")
        return last_instruction['value'] if last_instruction else None

    @entrypoint.setter
    def entrypoint(self, value):
        """
        setter for final 'ENTRYPOINT' instruction in final build stage

        """
        entrypoint = None
        for insndesc in self.structure:
            if insndesc['instruction'] == 'FROM':  # new stage, reset
                entrypoint = None
            elif insndesc['instruction'] == 'ENTRYPOINT':
                entrypoint = insndesc

        new_entrypoint = 'ENTRYPOINT ' + value
        if entrypoint:
            self.add_lines_at(entrypoint, new_entrypoint, replace=True)
        else:
            self.add_lines(new_entrypoint)


class FixuidDockerComposeAction(Action):
    """
    Automate fixuid configuration for docker compose services where fixuid.yml configuration file is available in
    build context
    """

    def __init__(self):
        self.docker_compose_config = dict()

    @property
    def event_bindings(self):
        def file_generated_processor(source: str, target: str):
            service = self.find_fixuid_service(target)
            if service:
                return (), {"service": service}
            return None

        return (
            "docker:docker-compose-config",
            EventBinding("file:generated",
                         call=self.apply_fixuid,
                         processor=file_generated_processor)
        )

    @property
    def name(self) -> str:
        return "fixuid:docker"

    @staticmethod
    def _load_image_attrs(image):
        registry_data_id_cache_key = "docker.image.name." + image + ".registry_data"
        registry_data_id = global_cache().get(registry_data_id_cache_key)
        if not registry_data_id:
            context.log.warning("Loading registry data id for image %s...", image)
            client = docker.from_env()
            registry_data = client.images.get_registry_data(image)
            registry_data_id = registry_data.id
            global_cache().set(registry_data_id_cache_key, registry_data_id)
            context.log.success("Id retrieved for image %s (%s)", image, registry_data_id)
        else:
            context.log.notice("Id retrieved for image %s (%s) (from cache)", image, registry_data_id)

        image_attrs_cache_key = "docker.image.id." + registry_data_id + ".attrs"
        image_attrs = global_cache().get(image_attrs_cache_key)

        if not image_attrs:
            context.log.warning("Loading attributes for image %s...", image)
            pulled_image = registry_data.pull()
            image_attrs = pulled_image.attrs
            global_cache().set(image_attrs_cache_key, image_attrs)
            context.log.success("Attributes retrieved for image %s", image)
        else:
            context.log.notice("Attributes retrieved for image %s (from cache)", image)
        return image_attrs

    @staticmethod
    def _get_image_config(image):
        if image and image != 'scratch':
            attrs = FixuidDockerComposeAction._load_image_attrs(image)
            if attrs and 'Config' in attrs:
                return attrs['Config']
        return None

    @staticmethod
    def apply_fixuid(service: BuildServiceDef):
        """
        Apply fixuid to given service
        """
        dockerfile_path = os.path.join(service.context, service.dockerfile)

        dockerfile_path_stat = None
        if not os.access(dockerfile_path, os.W_OK) and os.path.isfile(dockerfile_path):
            dockerfile_path_stat = os.stat(dockerfile_path)
            os.chmod(dockerfile_path, dockerfile_path_stat.st_mode | S_IWUSR)

        try:
            with open(dockerfile_path, "ba+") as dockerfile_file:
                parser = CustomDockerfileParser(fileobj=dockerfile_file)

                if FixuidDockerComposeAction._apply_fixuid_from_parser(parser, service):
                    context.log.success("Fixuid applied to %s",
                                        os.path.relpath(dockerfile_path, config.paths.project_home))
        finally:
            if dockerfile_path_stat is not None:
                os.chmod(dockerfile_path, dockerfile_path_stat.st_mode)

    @staticmethod
    def _apply_fixuid_from_parser(parser: CustomDockerfileParser, service: BuildServiceDef):
        entrypoint = parser.entrypoint
        cmd = parser.cmd
        # if entrypoint is defined in Dockerfile, we should not grab cmd from base image
        # and reset CMD to empty value to stay consistent with docker behavior.
        # see https://github.com/docker/docker.github.io/issues/6142
        reset_cmd = False
        if entrypoint and not cmd:
            reset_cmd = True
        if not entrypoint:
            baseimage_config = FixuidDockerComposeAction._get_image_config(parser.baseimage)
            if baseimage_config and 'Entrypoint' in baseimage_config:
                entrypoint = baseimage_config['Entrypoint']
                entrypoint = json.dumps(entrypoint)
        if not cmd and not reset_cmd:
            baseimage_config = FixuidDockerComposeAction._get_image_config(parser.baseimage)
            if baseimage_config and 'Cmd' in baseimage_config:
                cmd = baseimage_config['Cmd']
                cmd = json.dumps(cmd)
        if not cmd:
            cmd = None
        if entrypoint:
            parser.entrypoint = FixuidDockerComposeAction._sanitize_entrypoint(entrypoint)
        if cmd:
            parser.cmd = cmd
        target = copy_from_url(config.data["fixuid.url"],
                               service.context,
                               "fixuid.tar.gz")
        bus.emit('file:generated', source=None, target=target)
        lines = ("ADD fixuid.tar.gz /usr/local/bin",
                 "RUN chown root:root /usr/local/bin/fixuid && "
                 "chmod 4755 /usr/local/bin/fixuid && "
                 "mkdir -p /etc/fixuid",
                 "COPY fixuid.yml /etc/fixuid/config.yml")
        if "ADD fixuid.tar.gz /usr/local/bin\n" not in parser.lines:
            last_instruction_user = parser.get_last_instruction("USER")
            last_instruction_entrypoint = parser.get_last_instruction("ENTRYPOINT")
            if last_instruction_user:
                parser.add_lines_at(last_instruction_user, *lines)
            elif last_instruction_entrypoint:
                parser.add_lines_at(last_instruction_entrypoint, *lines)
            else:
                parser.add_lines(*lines)
            return True
        return False

    def execute(self, docker_compose_config: dict):
        """
        Execute action
        """
        self.docker_compose_config = docker_compose_config

        for service in self.fixuid_services:
            self.apply_fixuid(service)

    def find_fixuid_service(self, filepath: str):
        """
        Find related fixuid service from filepath
        """
        for service in self.fixuid_services:
            if os.path.join(service.context, service.dockerfile) == os.path.abspath(filepath):
                return service
        return None

    @property
    def fixuid_services(self) -> Iterable[BuildServiceDef]:
        """
        Services where fixuid.tar.gz is available in build context.
        """
        if "services" not in self.docker_compose_config:
            return

        for _, service in self.docker_compose_config.get("services").items():
            if "build" not in service.keys():
                continue

            if isinstance(service["build"], dict):
                build_context = Dotty(service).get("build.context")
            elif isinstance(service["build"], str):
                build_context = service["build"]
            else:
                continue

            if not os.path.exists(os.path.join(build_context, "fixuid.yml")):
                continue

            dockerfile = Dotty(service).get("build.dockerfile", "Dockerfile")
            yield BuildServiceDef(build_context, dockerfile)

    @staticmethod
    def _sanitize_entrypoint(entrypoint):
        as_list = False
        start_quote = ""
        end_quote = ""

        if entrypoint.startswith("["):
            as_list = True
            entrypoint_list = json.loads(entrypoint)
        else:
            entrypoint_match = re.compile(r"^(['\"]?)(.*?)(['\"]?)$").match(entrypoint)
            start_quote = entrypoint_match.group(1)
            end_quote = entrypoint_match.group(3)
            entrypoint = entrypoint_match.group(2)
            entrypoint_list = shlex.split(entrypoint)

        entrypoint_list = ["fixuid", "-q"] + entrypoint_list
        if as_list:
            entrypoint = json.dumps(entrypoint_list)
        else:
            entrypoint = " ".join(entrypoint_list)
            entrypoint = "%s%s%s" % (start_quote, entrypoint, end_quote)

        return entrypoint
