import os

import yaml
from ddb.__main__ import main
from tests.utilstest import expect_gitignore, setup_cfssl


class TestEject:
    def test_eject1(self, project_loader, module_scoped_container_getter):
        project_loader("eject1")

        setup_cfssl(module_scoped_container_getter)

        main(["configure"])

        assert os.path.exists("docker-compose.yml")
        assert os.path.exists("docker-compose.yml.jsonnet")
        assert expect_gitignore(".gitignore", "docker-compose.yml")

        assert os.path.exists(os.path.join(".bin", "psql"))
        assert expect_gitignore(".gitignore", ".bin/psql")

        assert os.path.exists(os.path.join(".docker", "db", "Dockerfile.jinja"))
        assert expect_gitignore(".gitignore", ".docker/db/Dockerfile")

        main(["configure", "--eject"])

        assert os.path.exists("docker-compose.yml")
        assert not os.path.exists("docker-compose.yml.jsonnet")
        assert not expect_gitignore(".gitignore", "docker-compose.yml")

        assert os.path.exists(os.path.join(".bin", "psql"))
        assert expect_gitignore(".gitignore", ".bin/psql")

        assert not os.path.exists(os.path.join(".docker", "db", "Dockerfile.jinja"))
        assert not expect_gitignore(".gitignore", ".docker/db/Dockerfile")

        with open('docker-compose.yml', 'r') as dc_file:
            data = yaml.load(dc_file, yaml.SafeLoader)

        with open('../expected/docker-compose.yml', 'r') as expected_dc_file:
            expected_data = yaml.load(expected_dc_file, yaml.SafeLoader)

        assert data == expected_data

    def test_eject2(self, project_loader, module_scoped_container_getter):
        project_loader("eject2")

        setup_cfssl(module_scoped_container_getter)

        main(["configure"])

        assert os.path.exists("docker-compose.yml")
        assert os.path.exists("docker-compose.yml.jsonnet")
        assert expect_gitignore(".gitignore", "docker-compose.yml")

        assert os.path.exists(os.path.join(".bin", "psql"))
        assert expect_gitignore(".gitignore", ".bin/psql")

        assert os.path.exists(os.path.join(".docker", "db", "Dockerfile.jinja"))
        assert expect_gitignore(".gitignore", ".docker/db/Dockerfile")

        main(["configure", "--eject"])

        assert os.path.exists("docker-compose.yml")
        assert not os.path.exists("docker-compose.yml.jsonnet")
        assert not expect_gitignore(".gitignore", "docker-compose.yml")

        assert os.path.exists(os.path.join(".bin", "psql"))
        assert expect_gitignore(".gitignore", ".bin/psql")

        assert not os.path.exists(os.path.join(".docker", "db", "Dockerfile.jinja"))
        assert not expect_gitignore(".gitignore", ".docker/db/Dockerfile")

        with open('docker-compose.yml', 'r') as dc_file:
            data = yaml.load(dc_file, yaml.SafeLoader)

        with open('../expected/docker-compose.yml', 'r') as expected_dc_file:
            expected_data = yaml.load(expected_dc_file, yaml.SafeLoader)

        assert data == expected_data

    def test_eject2_with_jsonnet_disabled(self, project_loader, module_scoped_container_getter):
        project_loader("eject2")

        setup_cfssl(module_scoped_container_getter)

        main(["configure"])

        assert os.path.exists("docker-compose.yml")
        assert os.path.exists("docker-compose.yml.jsonnet")
        assert expect_gitignore(".gitignore", "docker-compose.yml")

        assert os.path.exists(os.path.join(".bin", "psql"))
        assert expect_gitignore(".gitignore", ".bin/psql")

        assert os.path.exists(os.path.join(".docker", "db", "Dockerfile.jinja"))
        assert expect_gitignore(".gitignore", ".docker/db/Dockerfile")

        os.environ['DDB_OVERRIDE_DOCKER_JSONNET_VIRTUALHOST_DISABLED'] = "1"
        os.environ['DDB_OVERRIDE_DOCKER_JSONNET_BINARY_DISABLED'] = "True"
        main(["configure", "--eject"])

        assert os.path.exists("docker-compose.yml")
        assert not os.path.exists("docker-compose.yml.jsonnet")
        assert not expect_gitignore(".gitignore", "docker-compose.yml")

        assert not os.path.exists(os.path.join(".bin", "psql"))
        assert not expect_gitignore(".gitignore", ".bin/psql")

        assert not os.path.exists(os.path.join(".docker", "db", "Dockerfile.jinja"))
        assert not expect_gitignore(".gitignore", ".docker/db/Dockerfile")

        with open('docker-compose.yml', 'r') as dc_file:
            data = yaml.load(dc_file, yaml.SafeLoader)

        with open('../expected/docker-compose.jsonnet.disabled.yml', 'r') as expected_dc_file:
            expected_data = yaml.load(expected_dc_file, yaml.SafeLoader)

        assert data == expected_data
