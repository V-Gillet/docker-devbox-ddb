import os

import docker
import pytest
import yaml

from ddb.__main__ import load_registered_features, register_default_caches
from ddb.feature import features
from ddb.feature.core import CoreFeature
from ddb.feature.fixuid import FixuidFeature, FixuidDockerComposeAction


class TestFixuidFeature:
    def test_empty_project_without_core(self, project_loader):
        project_loader("empty")

        features.register(FixuidFeature())
        load_registered_features()

        action = FixuidDockerComposeAction()
        action.execute(config={})

    def test_empty_project_with_core(self, project_loader):
        project_loader("empty")

        features.register(CoreFeature())
        features.register(FixuidFeature())
        load_registered_features()

        action = FixuidDockerComposeAction()
        action.execute(config={})

    @pytest.mark.parametrize("project", [
        "from-scratch-empty",
        "from-scratch-with-entrypoint",
        "from-scratch-with-entrypoint-multiple-line",
        "from-scratch-with-entrypoint-string",
        "from-scratch-with-entrypoint-string-no-quotes",
        "from-php-missing-configuration",
        "from-php-empty",
        "from-php-with-entrypoint-only",
        "from-php-with-entrypoint-and-cmd",
        "from-php-user"
    ])
    def test_fixuid(self, project_loader, project):
        project_loader(project)
        register_default_caches()

        features.register(FixuidFeature())
        load_registered_features()

        with open('docker-compose.yml', 'r') as config_file:
            config = yaml.load(config_file, yaml.SafeLoader)

        action = FixuidDockerComposeAction()
        action.execute(config=config)

        with open(os.path.join("docker", "Dockerfile.expected"), "r") as f:
            expected = f.read()
        with open(os.path.join("docker", "Dockerfile"), "r") as f:
            content = f.read()
        assert content == expected

        if project in ["from-php-missing-configuration"]:
            assert not os.path.exists(os.path.join("docker", "fixuid.tar.gz"))
        else:
            assert os.path.exists(os.path.join("docker", "fixuid.tar.gz"))

        if "scratch" not in project:
            client = docker.from_env()
            image = client.images.build(path="docker")
            assert image
