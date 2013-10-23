import os
import re
import time
import shutil
import jinja2
import posixpath
import urllib
import markdown

from fabric.api import env, execute, task, abort, warn, local, settings
from fabric.context_managers import lcd, cd
from fabric.colors import yellow, blue, red, green


SCRIPTS_JS = "js"
STYLESHEETS_CSS = "css"
STYLESHEETS_SCSS = "scss"

OUTPUT_DIR = "gen"
TEMPLATES_DIR = "templates"
RESOURCES_DIR = "resources"
MEDIAS_DIR = "medias"
STYLESHEETS_DIR = "stylesheets"
SCRIPTS_DIR = "scripts"
ASSETS_DIR = "assets"
PROTECTED_DIRS = [MEDIAS_DIR, RESOURCES_DIR, STYLESHEETS_DIR, SCRIPTS_DIR, STYLESHEETS_CSS, SCRIPTS_JS, TEMPLATES_DIR]
STATICS_DIR = "statics"

ABS_ROOT_PATH = os.path.dirname(os.path.abspath(__file__))
ABS_OUTPUT_PATH = os.path.join(ABS_ROOT_PATH, OUTPUT_DIR)

SERVER_PORT = 8000
SERVER_SUFFIXES = ['','.html','index.html']


try:
    import SimpleHTTPServer as srv
except ImportError:
    import http.server as srv

try:
    import SocketServer as socketserver
except ImportError:
    import socketserver


class FabricHTTPRequestHandler(srv.SimpleHTTPRequestHandler):
    """Adaptation of the standard srv.SimpleHTTPRequestHandler for Fabric"""

    def translate_path(self, path):
        """Translate a /-separated PATH to the local filename syntax.

        - Components that mean special things to the local file system
        (e.g. drive or directory names) are ignored.  (XXX They should
        probably be diagnosed.).

        - Components such as query are ignored.
        """
        path = posixpath.normpath(urllib.splitquery(urllib.unquote(path))[0])
        words = path.split('/')
        words = filter(None, words)
        path = env.cwd # here is the small trick...
        for word in words:
            drive, word = os.path.splitdrive(word)
            head, word = os.path.split(word)
            if word in (os.curdir, os.pardir): continue
            path = os.path.join(path, word)
        return path


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
    execute(generate_assets)
    execute(generate_stylesheets)
    execute(generate_scripts)

    # collect bower listed dependencies
    execute(bower_install)

    # generate pages
    jinja_env = jinja2.Environment(loader=jinja2.FileSystemLoader(searchpath=TEMPLATES_DIR))
    jinja_context = {}
    jinja_pages = []
    for root, dirs, files in os.walk(TEMPLATES_DIR):
        for dir in dirs:
            if dir in PROTECTED_DIRS:
                abort(red("you cannot use restricted names (i.e. {}) for naming your directories.".format(
                    ','.join(PROTECTED_DIRS))))

            if dir.startswith('_'):
                jinja_context[os.path.relpath(root, TEMPLATES_DIR)] = {}
            else:
                __print_create(os.path.join(OUTPUT_DIR, dir))
                os.makedirs(os.path.join(ABS_OUTPUT_PATH, dir))
        for file in files:
            name, ext = os.path.splitext(file)
            basename = os.path.basename(root)
            relative_root = os.path.relpath(root, TEMPLATES_DIR)
            if name.startswith('_'):
                continue
            elif basename.startswith('_'):
                if ext == ".md":
                    data = markdown.Markdown(extensions=['meta'])
                    with open(os.path.join(root, file), "r") as fh:
                        html = data.convert(fh.read())
                        meta = data.Meta
                        if not jinja_context[os.path.dirname(relative_root)].has_key(basename[1:]):
                            jinja_context[os.path.dirname(relative_root)][basename[1:]] = []
                        jinja_context[os.path.dirname(relative_root)][basename[1:]].append({
                            'html': html,
                            'meta': meta
                        })
            elif ext == ".html":
                jinja_pages.append(os.path.join(relative_root, file))
            else:
                __print_ignore(os.path.join(relative_root, file))

    for page in jinja_pages:
        template = jinja_env.get_template(page)
        with open(os.path.join(OUTPUT_DIR, page), "wb") as fh:
            __print_build(*os.path.split(page))
            breadcrumb = os.path.dirname(page).split(os.sep) if os.path.dirname(page) is not '.' else []
            fh.write(template.render(breadcrumb=breadcrumb, **jinja_context))

    # finally generate resources
    execute(generate_resources)


def generate_assets():
    """Generate assets"""

    execute(bower_install, force=False)

    if os.path.exists(ASSETS_DIR):
        __print_copy(ASSETS_DIR, os.path.join(OUTPUT_DIR, ASSETS_DIR))
        shutil.copytree(ASSETS_DIR, os.path.join(OUTPUT_DIR, ASSETS_DIR))


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
            local("scss --update {0}:{1} --load-path {2}".format(
                os.path.join(STYLESHEETS_DIR, STYLESHEETS_SCSS),
                os.path.join(OUTPUT_DIR, STATICS_DIR, STYLESHEETS_CSS),
                ASSETS_DIR))


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
def bower_install(force=True):
    """Install bower dependencies."""
    if not os.path.exists(ASSETS_DIR) or force:
        local("bower install --config.directory={}".format(ASSETS_DIR))


@task
def publish(from_branch="devel", to_branch="devel-gh-pages"):
    local("git branch -D {0}".format(to_branch))
    local("git checkout --orphan {0}".format(to_branch))
    local("git rm --cached $(git ls-files)")
    execute(generate)
    local("git clean -xdf -e {0}".format(OUTPUT_DIR))
    local("mv gen/* .")
    local("rm -r {0}".format(OUTPUT_DIR))
    local("git add .")
    local("git commit -m \"updating at {0}\"".format(time.strftime("%d %b %Y %H:%M%S", time.localtime())))
    local("git push origin {0} --force".format(to_branch))
    local("git checkout {0}".format(from_branch))


def run_server():
    Handler = FabricHTTPRequestHandler

    try:
        httpd = socketserver.TCPServer(('', SERVER_PORT), Handler)
    except OSError as e:
        abort(red("Could not listen on post %s") % SERVER_PORT)

    print("Serving at port %s" % SERVER_PORT)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt as e:
        abort("Shutting down server")
        httpd.socket.close()


@task
def serve():
    with cd(os.path.join(os.getcwd(), OUTPUT_DIR)):
        with settings(warn_only=True):
            execute(run_server)


# --- stupid output functions ---


def __print_create(path):
    print(yellow("creating ") + blue(os.path.join(path)))


def __print_copy(src, dst):
    print(yellow("copying ") + blue(src) + " to " + blue(dst))


def __print_remove(path):
    print(yellow("removing ") + blue(path))


def __print_build(root, file):
    print(yellow("building ") + blue(os.path.join(root, file)))

def __print_ignore(file):
    print(green("ignoring ") + blue(file))