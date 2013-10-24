import os
import re
import time
import shutil
import jinja2
import posixpath
import urllib
import markdown
from distutils.filelist import FileList

from fabric.api import env, execute, task, local, settings
from fabric.api import warn as fabric_warn
from fabric.api import abort as fabric_abort
from fabric.context_managers import lcd, cd
from fabric.colors import yellow, blue, red, green

try:
    import SimpleHTTPServer as srv
except ImportError:
    import http.server as srv

try:
    import SocketServer as socketserver
except ImportError:
    import socketserver

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


########################################################################################################################
#
# Tasks
#
########################################################################################################################


@task
def clean():
    """Clean up generated files."""
    if os.path.exists(ABS_OUTPUT_PATH):
        remove_tree(OUTPUT_DIR)
    else:
        notify(msg="{} directory not found - everything is already clean !".format(OUTPUT_DIR))


@task
def generate():
    """Generate website locally."""

    # clean first...
    execute(clean)

    # process medias, stylesheets, scripts
    execute(process_medias)
    execute(process_assets)
    execute(process_stylesheets)
    execute(process_scripts)

    # process pages
    jinja_env = jinja2.Environment(loader=jinja2.FileSystemLoader(searchpath=TEMPLATES_DIR))
    jinja_context = {}
    jinja_pages = []
    for root, dirs, files in os.walk(TEMPLATES_DIR):
        for d in dirs:
            if d in PROTECTED_DIRS:
                abort("You cannot use restricted names (i.e. {}) for naming your directories.".format(
                    ','.join(PROTECTED_DIRS)))
            if d.startswith('_'):
                jinja_context[os.path.relpath(root, TEMPLATES_DIR)] = {}
            else:
                notify(action='create', path=os.path.join(OUTPUT_DIR, d))
                os.makedirs(os.path.join(ABS_OUTPUT_PATH, d))
        for f in files:
            name, ext = os.path.splitext(f)
            basename = os.path.basename(root)
            relative_root = os.path.relpath(root, TEMPLATES_DIR)
            if name.startswith('_'):
                continue
            elif basename.startswith('_'):
                if ext == ".md":
                    data = markdown.Markdown(extensions=['meta'])
                    with open(os.path.join(root, f), "r") as fh:
                        html = data.convert(fh.read())
                        meta = data.Meta
                        if not jinja_context[os.path.dirname(relative_root)].has_key(basename[1:]):
                            jinja_context[os.path.dirname(relative_root)][basename[1:]] = []
                        jinja_context[os.path.dirname(relative_root)][basename[1:]].append({
                            'html': html,
                            'meta': meta
                        })
            elif ext == ".html":
                jinja_pages.append(os.path.join(relative_root, f))
            else:
                notify('ignore', src=os.path.join(relative_root, f))

    for page in jinja_pages:
        template = jinja_env.get_template(page)
        with open(os.path.join(OUTPUT_DIR, page), "wb") as fh:
            notify('build', src=page)
            breadcrumb = os.path.dirname(page).split(os.sep) if os.path.dirname(page) is not '.' else []
            fh.write(template.render(breadcrumb=breadcrumb, **jinja_context))

    # finally generate resources
    execute(process_resources)


@task
def bower(action, force=True):
    """Wrap bower tasks."""
    if action == 'install' and (not os.path.exists(ASSETS_DIR) or force):
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


@task
def serve():
    with cd(os.path.join(os.getcwd(), OUTPUT_DIR)):
        with settings(warn_only=True):
            execute(run_server)


########################################################################################################################
#
# Sub tasks
#
########################################################################################################################


def process_medias():
    """Process medias"""

    if os.path.exists(MEDIAS_DIR):
        copy_tree(src=MEDIAS_DIR, dst=os.path.join(OUTPUT_DIR, STATICS_DIR, MEDIAS_DIR))
    else:
        warn("{} directory not found.".format(MEDIAS_DIR))


def process_assets():
    """Process assets"""

    # check bower assets
    if not os.path.exists(ASSETS_DIR):
        abort("{} directory not found - please run > fab bower:install".format(ASSETS_DIR))

    if not os.path.exists('assets.in'):
        abort("Please specify an assets.in file.")

    # load assets filter
    filelist = FileList()
    with open('assets.in', "r") as fh:
        for line in fh:
            filelist.process_template_line(line)

    # copy assets
    if os.path.exists(ASSETS_DIR):
        for f in filelist.files:
            copy_file(src=f, dst=os.path.join(OUTPUT_DIR, f), create_dir_if_not_exist=True)


def process_stylesheets():
    """Generate stylesheets. Only CSS is exported."""

    if os.path.exists(STYLESHEETS_DIR):
        if os.path.exists(os.path.join(STYLESHEETS_DIR, STYLESHEETS_CSS)):
            copy_tree(src=os.path.join(STYLESHEETS_DIR, STYLESHEETS_CSS), dst=os.path.join(OUTPUT_DIR, STATICS_DIR, STYLESHEETS_CSS))
        if os.path.exists(os.path.join(STYLESHEETS_DIR, STYLESHEETS_SCSS)):
            local("scss --update {0}:{1} --load-path {2}".format(
                os.path.join(STYLESHEETS_DIR, STYLESHEETS_SCSS),
                os.path.join(OUTPUT_DIR, STATICS_DIR, STYLESHEETS_CSS),
                ASSETS_DIR))


def process_scripts():
    """Generate scripts. Only JavaScript is exported"""

    if os.path.exists(os.path.join(SCRIPTS_DIR, SCRIPTS_JS)):
        copy_tree(src=os.path.join(SCRIPTS_DIR, SCRIPTS_JS), dst=os.path.join(OUTPUT_DIR, STATICS_DIR, SCRIPTS_JS))


def process_resources():
    """Generate resources (directory are ignored)."""

    for root, dirs, files in os.walk(RESOURCES_DIR):
        for f in files:
            if os.path.exists(os.path.join(OUTPUT_DIR, f)):
                warn("File {} is in conflict - it will be skipped.".format(f))
                continue
            else:
                copy_file(src=os.path.join(root, f), dst=os.path.join(OUTPUT_DIR, f))


def run_server():
    Handler = FabricHTTPRequestHandler

    try:
        httpd = socketserver.TCPServer(('', SERVER_PORT), Handler)
        notify(action="serving", msg="at port %s" % SERVER_PORT)
    except OSError as e:
        abort("Could not listen on post {}".format(SERVER_PORT))

    try:
        httpd.serve_forever()
    except KeyboardInterrupt as e:
        abort("Shutting down server")
        httpd.socket.close()


########################################################################################################################
#
# Utilities
#
########################################################################################################################


def copy_tree(src, dst):
    notify('copy', src=src, dst=dst)
    shutil.copytree(src, dst)


def remove_tree(path):
    notify('remove', path=path)
    shutil.rmtree(path)


def copy_file(src, dst, create_dir_if_not_exist=False):
    if create_dir_if_not_exist and not os.path.exists(os.path.dirname(dst)):
        output_dir = os.path.dirname(dst)
        notify('create', path=output_dir)
        os.makedirs(output_dir)
    notify('copy', src=src, dst=dst)
    shutil.copyfile(src, dst)


def warn(msg):
    fabric_warn(red(msg))


def abort(msg):
    fabric_abort(red(msg))

def notify(action=None, **kwargs):
    if action == "create":
        print(yellow("creating ") + blue(kwargs['path']))
    elif action == "copy":
        print(yellow("copying ") + blue(kwargs['src']) + " to " + blue(kwargs['dst']))
    elif action == 'build':
        print(yellow("building ") + blue(kwargs['src']))
    elif action == 'ignore':
        print(green("ignoring ") + blue(kwargs['src']))
    elif action == 'remove':
        print(yellow("removing ") + blue(kwargs['path']))
    elif action is not None:
        print("{action} {msg}".format(action=action, msg=kwargs['msg']))
    else:
        print(kwargs['msg'])