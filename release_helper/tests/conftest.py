# Copyright (c) Jupyter Development Team.
# Distributed under the terms of the Modified BSD License.
import json
import os
import traceback
from pathlib import Path
from urllib.request import OpenerDirector

from click.testing import CliRunner
from pytest import fixture

from release_helper import changelog
from release_helper import cli
from release_helper import util
from release_helper.tests import util as testutil
from release_helper.util import run


CHANGELOG_TEMPLATE = f"""# Changelog

{changelog.START_MARKER}

{changelog.END_MARKER}

## 0.0.1

Initial commit
"""


@fixture(autouse=True)
def mock_env_vars(mocker):
    """Clear any GitHub related environment variables"""
    env = os.environ.copy()
    for key in list(env.keys()):
        if key.startswith("GITHUB_"):
            del env[key]
    mocker.patch.dict(os.environ, env, clear=True)
    yield


@fixture
def git_repo(tmp_path):
    prev_dir = os.getcwd()
    os.chdir(tmp_path)

    run("git init")
    run("git config user.name snuffy")
    run("git config user.email snuffy@sesame.com")

    run("git checkout -b foo")
    gitignore = tmp_path / ".gitignore"
    gitignore.write_text("dist/*\nbuild/*\n", encoding="utf-8")

    changelog = tmp_path / "CHANGELOG.md"
    changelog.write_text(CHANGELOG_TEMPLATE, encoding="utf-8")

    readme = tmp_path / "README.md"
    readme.write_text("Hello from foo project\n", encoding="utf-8")

    run("git add .")
    run('git commit -m "foo"')
    run("git tag v0.0.1")
    run(f"git remote add upstream {util.normalize_path(tmp_path)}")
    run("git checkout -b bar foo")
    run("git fetch upstream")
    yield tmp_path
    os.chdir(prev_dir)


@fixture
def py_package(git_repo):
    return testutil.create_python_package(git_repo)


@fixture
def npm_package(git_repo):
    return testutil.create_npm_package(git_repo)


@fixture
def workspace_package(npm_package):
    pkg_file = npm_package / "package.json"
    data = json.loads(pkg_file.read_text(encoding="utf-8"))
    data["workspaces"] = dict(packages=["packages/*"])
    data["private"] = True
    pkg_file.write_text(json.dumps(data), encoding="utf-8")

    prev_dir = Path(os.getcwd())
    for name in ["foo", "bar", "baz"]:
        new_dir = prev_dir / "packages" / name
        os.makedirs(new_dir)
        os.chdir(new_dir)
        run("npm init -y")
        index = new_dir / "index.js"
        index.write_text('console.log("hello")', encoding="utf-8")
        if name == "foo":
            pkg_json = new_dir / "package.json"
            sub_data = json.loads(pkg_json.read_text(encoding="utf-8"))
            sub_data["dependencies"] = dict(bar="*")
            pkg_json.write_text(json.dumps(sub_data), encoding="utf-8")
        elif name == "baz":
            pkg_json = new_dir / "package.json"
            sub_data = json.loads(pkg_json.read_text(encoding="utf-8"))
            sub_data["dependencies"] = dict(foo="*")
            pkg_json.write_text(json.dumps(sub_data), encoding="utf-8")
    os.chdir(prev_dir)
    return npm_package


@fixture
def py_dist(py_package, runner, mocker):
    changelog_entry = testutil.mock_changelog_entry(py_package, runner, mocker)

    # Create the dist files
    run("python -m build .")

    # Finalize the release
    runner(["tag-release"])

    return py_package


@fixture
def npm_dist(workspace_package, runner, mocker):
    changelog_entry = testutil.mock_changelog_entry(workspace_package, runner, mocker)

    # Create the dist files
    runner(["build-npm"])

    # Finalize the release
    runner(["tag-release"])

    return workspace_package


@fixture()
def runner():
    cli_runner = CliRunner()

    def run(*args, **kwargs):
        result = cli_runner.invoke(cli.main, *args, **kwargs)
        assert result.exit_code == 0, traceback.print_exception(*result.exc_info)
        return result

    return run


@fixture
def open_mock(mocker):
    open_mock = mocker.patch.object(OpenerDirector, "open", autospec=True)
    open_mock.return_value = testutil.MockHTTPResponse()
    yield open_mock
