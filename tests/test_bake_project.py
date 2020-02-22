import datetime
import importlib
import os
import shlex
import subprocess
import sys
from contextlib import contextmanager
from pathlib import Path

import pytest
import yaml
from click.testing import CliRunner
from cookiecutter.utils import rmtree


@contextmanager
def inside_dir(dirpath):
    """
    Execute code from inside the given directory
    :param dirpath: String, path of the directory the command is being run.
    """
    old_path = os.getcwd()
    try:
        os.chdir(dirpath)
        yield
    finally:
        os.chdir(old_path)


@contextmanager
def bake_in_temp_dir(cookies, *args, **kwargs):
    """
    Delete the temporal directory that is created when executing the tests
    :param cookies: pytest_cookies.Cookies,
        cookie to be baked and its temporal files will be removed
    """
    current_path = Path(".").parent.absolute()
    template_path = current_path.parent.absolute()
    result = cookies.bake(*args, template=str(template_path), **kwargs)
    try:
        yield result
    finally:
        rmtree(str(result.project))


def run_inside_dir(command, dirpath):
    """
    Run a command from inside a given directory, returning the exit status
    :param command: Command that will be executed
    :param dirpath: String, path of the directory the command is being run.
    """
    with inside_dir(dirpath):
        return subprocess.check_call(shlex.split(command))


def check_output_inside_dir(command, dirpath):
    "Run a command from inside a given directory, returning the command output"
    with inside_dir(dirpath):
        return subprocess.check_output(shlex.split(command))


def project_info(result):
    """Get toplevel dir, project_slug, and project dir from baked cookies"""
    project_path = str(result.project)
    project_slug = os.path.split(project_path)[-1]
    project_dir = os.path.join(project_path, project_slug)
    return project_path, project_slug, project_dir


# region Default output tests


def test_bake_with_defaults(cookies):
    with bake_in_temp_dir(cookies) as result:
        assert result.project.isdir()
        assert result.exit_code == 0
        assert result.exception is None

        found_toplevel_files = [f.basename for f in result.project.listdir()]
        assert "pyproject.toml" in found_toplevel_files
        assert "python_boilerplate" in found_toplevel_files
        assert "tox.ini" in found_toplevel_files
        assert "tests" in found_toplevel_files
        assert "docs" in found_toplevel_files
        assert ".bumpversion.cfg" in found_toplevel_files
        assert ".editorconfig" in found_toplevel_files
        assert ".gitignore" in found_toplevel_files
        assert "AUTHORS.rst" in found_toplevel_files
        assert "HISTORY.rst" in found_toplevel_files
        assert "LICENSE" in found_toplevel_files
        assert "README.rst" in found_toplevel_files

        assert "licenses" not in found_toplevel_files


def test_year_compute_in_license_file(cookies):
    with bake_in_temp_dir(cookies) as result:
        license_file_path = result.project.join("LICENSE")
        now = datetime.datetime.now()
        assert str(now.year) in license_file_path.read()


# endregion

# region pytest


def test_bake_and_run_tests(cookies):
    with bake_in_temp_dir(cookies) as result:
        assert result.project.isdir()
        assert run_inside_dir("pytest", str(result.project)) == 0
        print("test_bake_and_run_tests path", str(result.project))


def test_using_pytest(cookies):
    with bake_in_temp_dir(cookies, extra_context={"use_pytest": "y"}) as result:
        assert result.project.isdir()
        test_file_path = result.project.join("tests/test_python_boilerplate.py")
        lines = test_file_path.readlines()
        assert "import pytest" in "".join(lines)
        # Test the new pytest target
        assert run_inside_dir("pytest", str(result.project)) == 0


# endregion


# region special characters


def test_bake_with_apostrophe(cookies):
    """Ensure that a `full_name` with apostrophes does not break setup.py"""
    with bake_in_temp_dir(cookies, extra_context={"full_name": "O'connor"}) as result:
        assert result.project.isdir()
        assert run_inside_dir("poetry check", str(result.project)) == 0


# endregion


def test_bake_without_travis_pypi_setup(cookies):
    with bake_in_temp_dir(
        cookies, extra_context={"use_pypi_deployment_with_travis": "n"}
    ) as result:
        result_travis_config = yaml.load(
            result.project.join(".travis.yml").open(), Loader=yaml.FullLoader
        )
        assert "deploy" not in result_travis_config
        assert "python" == result_travis_config["language"]
        # found_toplevel_files = [f.basename for f in result.project.listdir()]


# region Excluding files


def test_bake_without_author_file(cookies):
    with bake_in_temp_dir(cookies, extra_context={"create_author_file": "n"}) as result:
        found_toplevel_files = [f.basename for f in result.project.listdir()]
        assert "AUTHORS.rst" not in found_toplevel_files
        doc_files = [f.basename for f in result.project.join("docs").listdir()]
        assert "authors.rst" not in doc_files

        # Assert there are no spaces in the toc tree
        docs_index_path = result.project.join("docs/index.rst")
        with open(str(docs_index_path)) as index_file:
            assert "contributing\n   history" in index_file.read()


# endregion


def test_make_help(cookies):
    with bake_in_temp_dir(cookies) as result:
        # The supplied Makefile does not support win32
        if sys.platform != "win32":
            output = check_output_inside_dir("make help", str(result.project))
            assert b"check code coverage quickly with the default Python" in output


# region License


@pytest.mark.parametrize(
    "full_name,identifier,file_starts_with",
    [
        ("MIT license", "MIT", "MIT License"),
        ("Apache Software License 2.0", "Apache-2.0", "Apache License"),
        ("GNU General Public License v3.0", "GPL-3.0-only", "GNU GENERAL PUBLIC LICENSE"),
        ("GNU General Public License v2.0", "GPL-2.0-only", "GNU GENERAL PUBLIC LICENSE"),
        ("BSD 3-Clause 'New' or 'Revised' License", "BSD-3-Clause", f"Copyright (c) {datetime.date.today().year} Johan Vergeer"),
        ("GNU Lesser General Public License v2.1", "LGPL-2.1-only", "GNU LESSER GENERAL PUBLIC LICENSE"),
        ("BSD 2-Clause 'Simplified' License", "BSD-2-Clause", f"Copyright (c) {datetime.date.today().year} Johan Vergeer"),
    ],
)
def test_bake_selecting_license(cookies, full_name, identifier, file_starts_with):
    with bake_in_temp_dir(
        cookies, extra_context={"open_source_license": full_name}
    ) as result:
        assert file_starts_with.lower() in result.project.join("LICENSE").read().lower()
        assert f"license = \"{identifier}\"" in result.project.join("pyproject.toml").read()


def test_bake_not_open_source(cookies):
    with bake_in_temp_dir(
        cookies, extra_context={"open_source_license": "Not open source"}
    ) as result:
        found_toplevel_files = [f.basename for f in result.project.listdir()]
        assert "pyproject.toml" in found_toplevel_files
        assert f"license = " not in result.project.join("pyproject.toml").read()
        assert "LICENSE" not in found_toplevel_files
        assert "License" not in result.project.join("README.rst").read()


# endregion

# def test_project_with_hyphen_in_module_name(cookies):
#     result = cookies.bake(
#         extra_context={'project_name': 'something-with-a-dash'}
#     )
#     assert result.project is not None
#     project_path = str(result.project)
#
#     # when:
#     travis_setup_cmd = ('python travis_pypi_setup.py'
#                         ' --repo audreyr/cookiecutter-pypackage'
#                         ' --password invalidpass')
#     run_inside_dir(travis_setup_cmd, project_path)
#
#     # then:
#     result_travis_config = yaml.load(
#         open(os.path.join(project_path, ".travis.yml"))
#     )
#     assert "secure" in result_travis_config["deploy"]["password"],\
#         "missing password config in .travis.yml"


@pytest.mark.xfail
def test_bake_with_no_console_script(cookies):
    context = {"command_line_interface": "No command-line interface"}
    result = cookies.bake(extra_context=context)
    project_path, project_slug, project_dir = project_info(result)
    found_project_files = os.listdir(project_dir)
    assert "cli.py" not in found_project_files

    setup_path = os.path.join(project_path, "setup.py")
    with open(setup_path, "r") as setup_file:
        assert "entry_points" not in setup_file.read()


@pytest.mark.xfail
def test_bake_with_console_script_files(cookies):
    context = {"command_line_interface": "click"}
    result = cookies.bake(extra_context=context)
    project_path, project_slug, project_dir = project_info(result)
    found_project_files = os.listdir(project_dir)
    assert "cli.py" in found_project_files

    setup_path = os.path.join(project_path, "setup.py")
    with open(setup_path, "r") as setup_file:
        assert "entry_points" in setup_file.read()


@pytest.mark.xfail
def test_bake_with_argparse_console_script_files(cookies):
    context = {"command_line_interface": "argparse"}
    result = cookies.bake(extra_context=context)
    project_path, project_slug, project_dir = project_info(result)
    found_project_files = os.listdir(project_dir)
    assert "cli.py" in found_project_files

    setup_path = os.path.join(project_path, "setup.py")
    with open(setup_path, "r") as setup_file:
        assert "entry_points" in setup_file.read()


@pytest.mark.xfail
def test_bake_with_console_script_cli(cookies):
    context = {"command_line_interface": "click"}
    result = cookies.bake(extra_context=context)
    project_path, project_slug, project_dir = project_info(result)
    module_path = os.path.join(project_dir, "cli.py")
    module_name = ".".join([project_slug, "cli"])
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    cli = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(cli)
    runner = CliRunner()
    noarg_result = runner.invoke(cli.main)
    assert noarg_result.exit_code == 0
    noarg_output = " ".join(
        ["Replace this message by putting your code into", project_slug]
    )
    assert noarg_output in noarg_result.output
    help_result = runner.invoke(cli.main, ["--help"])
    assert help_result.exit_code == 0
    assert "Show this message" in help_result.output


@pytest.mark.xfail
def test_bake_with_argparse_console_script_cli(cookies):
    context = {"command_line_interface": "argparse"}
    result = cookies.bake(extra_context=context)
    project_path, project_slug, project_dir = project_info(result)
    module_path = os.path.join(project_dir, "cli.py")
    module_name = ".".join([project_slug, "cli"])
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    cli = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(cli)
    runner = CliRunner()
    noarg_result = runner.invoke(cli.main)
    assert noarg_result.exit_code == 0
    noarg_output = " ".join(
        ["Replace this message by putting your code into", project_slug]
    )
    assert noarg_output in noarg_result.output
    help_result = runner.invoke(cli.main, ["--help"])
    assert help_result.exit_code == 0
    assert "Show this message" in help_result.output
