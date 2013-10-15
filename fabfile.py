import os
import re
import time
import shutil
import jinja2

from fabric.api import run, execute, task, abort, warn, local
from fabric.colors import yellow, blue, red

SCRIPTS_JS = "js"
STYLESHEETS_CSS = "css"
STYLESHEETS_SCSS = "scss"

OUTPUT_DIR = "gen"
TEMPLATES_DIR = "templates"
RESOURCES_DIR = "resources"
MEDIAS_DIR = "medias"
STYLESHEETS_DIR = "stylesheets"
SCRIPTS_DIR = "scripts"
PROTECTED_DIRS = [MEDIAS_DIR, RESOURCES_DIR, STYLESHEETS_DIR, SCRIPTS_DIR, STYLESHEETS_CSS, SCRIPTS_JS, TEMPLATES_DIR]
STATICS_DIR = "statics"

ABS_ROOT_PATH = os.path.dirname(os.path.abspath(__file__))
ABS_OUTPUT_PATH = os.path.join(ABS_ROOT_PATH, OUTPUT_DIR)


@task
def clean():
    """Clean up generated files."""
    if os.path.exists(ABS_OUTPUT_PATH):
        __print_remove(OUTPUT_DIR)
        shutil.rmtree(ABS_OUTPUT_PATH)


@task
def generate():
    """Generate website locally."""

    # clean first...
    execute(clean)

    # generate medias, stylesheets, scripts
    execute(generate_medias)
    execute(generate_stylesheets)
    execute(generate_scripts)

    # collect bower listed dependencies
    execute(bower_install)

    # generate templates
    env = jinja2.Environment(loader=jinja2.FileSystemLoader(searchpath=TEMPLATES_DIR))
    for root, dirs, files in os.walk(TEMPLATES_DIR):
        for dir in dirs:
            if dir in PROTECTED_DIRS:
                abort(red("you cannot use restricted names (i.e. {}) for naming your directories.".format(
                    ','.join(PROTECTED_DIRS))))
            __print_create(os.path.join(OUTPUT_DIR, dir))
            os.makedirs(os.path.join(ABS_OUTPUT_PATH, dir))
        for file in files:
            name, ext = os.path.splitext(file)
            if not name.startswith("_") and ext == ".html":
                __print_build(root, file)
                template = env.get_template(file)
                file_output_dir = re.sub(r"^({})".format(TEMPLATES_DIR), OUTPUT_DIR, root)
                with open(os.path.join(file_output_dir, file), "wb") as fh:
                    fh.write(template.render())

    # finally generate resources
    execute(generate_resources)


def generate_medias():
    """Generate medias"""

    if os.path.exists(MEDIAS_DIR):
        __print_copy(MEDIAS_DIR, os.path.join(OUTPUT_DIR, STATICS_DIR, MEDIAS_DIR))
        shutil.copytree(MEDIAS_DIR, os.path.join(OUTPUT_DIR, STATICS_DIR, MEDIAS_DIR))


def generate_stylesheets():
    """Generate stylesheets. Only CSS is exported."""

    if os.path.exists(STYLESHEETS_DIR):
        if os.path.exists(os.path.join(STYLESHEETS_DIR, STYLESHEETS_CSS)):
            __print_copy(os.path.join(STYLESHEETS_DIR, STYLESHEETS_CSS), os.path.join(OUTPUT_DIR, STATICS_DIR, STYLESHEETS_CSS))
            shutil.copytree(os.path.join(STYLESHEETS_DIR, STYLESHEETS_CSS), os.path.join(OUTPUT_DIR, STATICS_DIR, STYLESHEETS_CSS))
        if os.path.exists(os.path.join(STYLESHEETS_DIR, STYLESHEETS_SCSS)):
            local("scss --update {0}:{1}".format(os.path.join(STYLESHEETS_DIR, STYLESHEETS_SCSS), os.path.join(OUTPUT_DIR, STATICS_DIR, STYLESHEETS_CSS)))



def generate_scripts():
    """Generate scripts. Only JavaScript is exported"""

    if os.path.exists(os.path.join(SCRIPTS_DIR, SCRIPTS_JS)):
        __print_copy(os.path.join(SCRIPTS_DIR, SCRIPTS_JS), os.path.join(OUTPUT_DIR, STATICS_DIR, SCRIPTS_JS))
        shutil.copytree(os.path.join(SCRIPTS_DIR, SCRIPTS_JS), os.path.join(OUTPUT_DIR, STATICS_DIR, SCRIPTS_JS))


def generate_resources():
    """Generate resources (directory are ignored)."""

    for root, dirs, files in os.walk(RESOURCES_DIR):
        for f in files:
            if os.path.exists(os.path.join(OUTPUT_DIR, f)):
                warn(red("File {} is in conflict - it will be skipped."))
                continue
            else:
                __print_copy(os.path.join(root, f), os.path.join(OUTPUT_DIR, f))
                shutil.copyfile(os.path.join(root, f), os.path.join(OUTPUT_DIR, f))


@task()
def bower_install():
    """Install bower dependencies."""

    local("bower install --config.directory={0}/assets".format(OUTPUT_DIR))


@task
def publish(from_branch="devel", to_branch="devel-gh-pages"):
    local("git branch -D {0}".format(to_branch))
    local("git checkout --orphan {0}".format(to_branch))
    local("git rm --cached $(git ls-files)")
    execute(generate)
    execute(bower_install)
    local("git clean -xdf -e {0}".format(OUTPUT_DIR))
    local("mv gen/* .")
    local("rm -r {0}".format(OUTPUT_DIR))
    local("git add .")
    local("git commit -m \"updating at {0}\"".format(time.strftime("%d %b %Y %H:%M%S", time.localtime())))
    local("git push origin {0} --force".format(to_branch))
    local("git checkout {0}".format(from_branch))


# --- stupid output functions ---


def __print_create(path):
    print(yellow("creating ") + blue(os.path.join(path)))


def __print_copy(src, dst):
    print(yellow("copying ") + blue(src) + " to " + blue(dst))


def __print_remove(path):
    print(yellow("removing ") + blue(path))


def __print_build(root, file):
    print(yellow("building ") + blue(os.path.join(root, file)))