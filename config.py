import json
import pathlib
import platform
import functools
import collections

from flask import Flask
from flask import render_template

from buildbot.plugins import *
from buildbot.process import results

import settings


class Dataset:
    def __init__(self, org, clone_url, cldf_metadata, cldfbench_curator):
        self.url = clone_url
        self.org = org
        self.name = self.url.split("/")[-1].replace(".git", "")
        self.cldf_metadata = cldf_metadata
        self.cldfbench_curator = cldfbench_curator

    @property
    def id(self):
        return '{0.org}-{0.name}'.format(self)

    @property
    def schedulers(self):
        return [schedulers.ForceScheduler(name="%s-force" % self.id, builderNames=[self.id])]

    @staticmethod
    def shell_command(name, cmd, **kw):
        return steps.ShellCommand(
            command=cmd,
            workdir="build",
            env={"PYTHONPATH": "."},
            logEnviron=False,
            name=name,
            **kw)

    def venv_cmd(self, cmd):
        return './{0}/bin/{1}'.format(self.id, cmd)

    @property
    def builder(self):
        """
        The build process for a dataset.
        """
        factory = util.BuildFactory()

        factory.addStep(steps.Git(repourl=self.url, mode='full', method="fresh"))

        factory.addStep(self.shell_command(
            'virtualenv',
            ['python3', '-m', 'venv', self.id]
        ))

        if self.cldfbench_curator:  # An installable dataset!
            #
            # need shell script:
            #
            factory.addStep(self.shell_command(
                'install dataset',
                [self.venv_cmd("pip"), '--cache-dir', '../.cache', "install", "--upgrade", "."],
                haltOnFailure=True,
            ))
            factory.addStep(self.shell_command(
                'install tools',
                [self.venv_cmd("pip"), '--cache-dir', '../.cache', "install", "--upgrade", "pytest", "pytest-cldf"],
                haltOnFailure = True,
            ))
            catalogs = [
                '--glottolog',
                str(pathlib.Path(__file__).parent.parent.joinpath('glottolog').resolve()),
            ]
            if self.cldfbench_curator == 'lexibank':
                # lexibank datasets have their own makecldf command, with additional requirements:
                catalogs.extend([
                    '--concepticon',
                    str(pathlib.Path(__file__).parent.parent.joinpath('concepticon-data').resolve()),
                    '--clts',
                    str(pathlib.Path(__file__).parent.parent.joinpath('clts').resolve()),
                ])
            factory.addStep(self.shell_command(
                'makecldf',
                [
                    self.venv_cmd("cldfbench"),
                    ('lexibank.' if self.org == 'lexibank' else '') + 'makecldf',
                    self.name,
                ] + catalogs))
            # run tests
            factory.addStep(self.shell_command(
                'pytest',
                ['pytest']))

        # validate
        for mdpath in self.cldf_metadata:
            factory.addStep(self.shell_command(
                'validate',
                [self.venv_cmd("cldf"), "validate", mdpath]))

        # run checks:
        for mdpath in self.cldf_metadata:
            factory.addStep(self.shell_command(
                'cldf check',
                [self.venv_cmd("cldf"), "check", mdpath],
                decodeRC={0: results.SUCCESS, 2: results.WARNINGS},
                warnOnWarnings=True,
            ))

        if self.cldfbench_curator:
            factory.addStep(self.shell_command(
                'cldfbench check',
                [self.venv_cmd("cldfbench"), "--log-level", "WARN", "check", self.name],
                decodeRC={0: results.SUCCESS, 2: results.WARNINGS},
                warnOnWarnings=True,
            ))
            # if self.cldfbench_curator == 'lexibank':
            #    factory.addStep(self.shell_command(
            #        'lexibank check',
            #        ["cldfbench", "--log-level", "WARN", "lexibank.check", self.name],
            #        decodeRC={0: results.SUCCESS, 2: results.WARNINGS},
            #        warnOnWarnings=True,
            #    ))
        return factory


with pathlib.Path(__file__).parent.joinpath('reposlist.json').open(encoding='utf8') as fp:
    DATASETS = [Dataset(*args) for args in json.load(fp)]

if platform.node() == 'dlt4803010l':
    DATASETS = [ds for ds in DATASETS if ds.name in [
        'dryerorder',
        'chenhmongmien',
        'daakaka',
        'birchallchapacuran']]

# This is the dictionary that the buildmaster pays attention to. We also use
# a shorter alias to save typing.
c = BuildmasterConfig = {}
c['buildbotNetUsageData'] = None

####### WORKERS

# The 'workers' list defines the set of recognized workers. Each element is
# a Worker object, specifying a unique worker name and password.  The same
# worker name and password must be configured on the worker.
c['workers'] = [worker.Worker("worker", "pass")]

# 'protocols' contains information about protocols which master will use for
# communicating with workers. You must define at least 'port' option that workers
# could connect to your master with this protocol.
# 'port' must match the value configured into the workers (with their
# --master option)
c['protocols'] = {'pb': {'port': 9989}}

####### CHANGESOURCES

# the 'change_source' setting tells the buildmaster how it should find out
# about source code changes.  Here we point to the buildbot version of a python hello-world project.

c['change_source'] = []
#    changes.GitPoller(
#        repo,
#        workdir='workdir.%s' % name,
#        branch='master',
#        pollInterval=300
#   ) for name, repo in repos.items()]

####### SCHEDULERS

# Configure the Schedulers, which decide how to react to incoming changes.
c['schedulers'] = []
for org in set(ds.org for ds in DATASETS):
    c['schedulers'].extend([
        schedulers.Triggerable(
            name="release-{0}".format(org),
            builderNames=[ds.id for ds in DATASETS if ds.org == org]),
        schedulers.ForceScheduler(
            name="release-{0}-force".format(org),
            builderNames=['a-release-{0}'.format(org)])
    ])

for ds in DATASETS:
    c['schedulers'].extend(ds.schedulers)

####### BUILDERS

# The 'builders' list defines the Builders, which tell Buildbot how to perform a build:
# what steps, and which workers can execute them.  Note that any particular build will
# only take place on one worker.

c['builders'] = []
for org in set(ds.org for ds in DATASETS):
    release = util.BuildFactory()
    release.addStep(steps.Trigger(
        schedulerNames=['release-{0}'.format(org)],
        waitForFinish=False))
    c['builders'].append(util.BuilderConfig(
        name='a-release-{0}'.format(org),
        workernames=["worker"],
        factory=release))

for ds in DATASETS:
    c['builders'].append(util.BuilderConfig(name=ds.id, workernames=["worker"], factory=ds.builder))

####### BUILDBOT SERVICES

# 'services' is a list of BuildbotService items like reporter targets. The
# status of each build will be pushed to these targets. buildbot/reporters/*.py
# has a variety to choose from, like IRC bots.

c['services'] = []

####### PROJECT IDENTITY

# the 'title' string will appear at the top of this buildbot installation's
# home pages (linked to the 'titleURL').

c['title'] = "CLDF Buildbot"
c['titleURL'] = "https://github.com/cldf/cldf-buildbot"

# the 'buildbotURL' string should point to the location where the buildbot's
# internal web server is visible. This typically uses the port number set in
# the 'www' entry below, but with an externally-visible host name which the
# buildbot cannot figure out without some help.

c['buildbotURL'] = "http://{0}:8010/".format(settings.HOST)


def status_view(org, app):
    class UIDataset:
        def __init__(self, builder):
            parts = builder['name'].split('-')
            self.builder_id = builder['builderid']
            self.builder_name = builder['name']
            self.org = '-'.join(parts[:-1])
            self.name = parts[-1]
            self.github_url = 'https://github.com/{0.org}/{0.name}'.format(self)

    builders = []
    for builder in app.buildbot_api.dataGet("/builders"):
        if builder['name'].startswith('release'):
            continue
        ds = UIDataset(builder)
        if ds.org == org:
            builders.append(ds)
    return render_template('status.html', builders=builders, org=org)


dashboards = collections.OrderedDict()
for org in set(ds.org for ds in DATASETS):
    dashboards[org] = Flask(
        org,
        template_folder=str(pathlib.Path(__file__).parent.joinpath('..', 'cldf-buildbot', 'templates').resolve()))
    dashboards[org].config['TEMPLATES_AUTO_RELOAD'] = True
    dashboards[org].add_url_rule(
        '/index.html', org, functools.partial(status_view, org, dashboards[org]))


# minimalistic config to activate new web UI
c['www'] = dict(
    port=8010,
    plugins=dict(
        badges={},
        wsgi_dashboards=[  # This is a list of dashboards, you can create several
            {
                'name': '{0}-status'.format(org),
                'caption': '{0} Status'.format(org),
                'app': app,
                'order': 1,
                'icon': 'book' if org == 'dictionaria' else (
                    'clipboard' if org == 'lexibank' else 'database')
            }
            for org, app in dashboards.items()
        ]
    ),
)
####### DB URL

c['db'] = {
    # This specifies what database buildbot uses to store its state.
    # It's easy to start with sqlite, but it's recommended to switch to a dedicated
    # database, such as PostgreSQL or MySQL, for use in production environments.
    # http://docs.buildbot.net/current/manual/configuration/global.html#database-specification
    'db_url': "sqlite:///state.sqlite",
}
