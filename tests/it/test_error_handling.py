import os

from _pytest.logging import LogCaptureFixture

from ddb.__main__ import main


class TestErrorHandling:
    def test_invalid_jsonnet(self, project_loader, caplog: LogCaptureFixture):
        project_loader("invalid-jsonnet")

        exceptions = main(["configure"])
        assert len(exceptions) == 1

        assert len(caplog.records) == 1
        record = caplog.records[0]

        assert record.message == \
               'An unexpected error has occured ' + \
               '[phase:configure => FileWalkAction.execute(), ' + \
               'file:found => JsonnetAction.render_jsonnet(target=invalid, template=invalid.jsonnet)]: ' + \
               'STATIC ERROR: invalid.jsonnet:1:1-9: Unknown variable: trololol'
