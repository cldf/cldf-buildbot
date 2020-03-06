import json
import pathlib
import platform

from buildbot.plugins import *
from buildbot.process import results


class Dataset:
    def __init__(self, org, clone_url, cldf_metadata):
        self.url = clone_url
        self.org = org
        self.name = self.url.split("/")[-1].replace(".git", "")
        self.cldf_metadata = cldf_metadata

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

    @property
    def builder(self):
        factory = util.BuildFactory()
        factory.addStep(steps.Git(repourl=self.url, mode='full', method="fresh"))
        factory.addStep(self.shell_command(
            'install dataset',
            ["pip", "install", "--upgrade", "."]))
        factory.addStep(self.shell_command(
            'install tools',
            ["pip", "install", "--upgrade", "pytest", "pytest-cldf"]))
        catalogs = [
            '--glottolog',
            str(pathlib.Path(__file__).parent.parent.joinpath('glottolog').resolve()),
        ]
        if self.org == 'lexibank':
            catalogs.extend([
                '--concepticon',
                str(pathlib.Path(__file__).parent.parent.joinpath('concepticon-data').resolve()),
                '--clts',
                str(pathlib.Path(__file__).parent.parent.joinpath('clts').resolve()),
            ])
        factory.addStep(self.shell_command(
            'makecldf',
            [
                "cldfbench",
                ('lexibank.' if self.org == 'lexibank' else '') + 'makecldf',
                self.name,
            ] + catalogs))

        # validate
        for mdpath in self.cldf_metadata:
            factory.addStep(self.shell_command(
                'validate',
                ["cldf", "validate", mdpath]))
        # run tests
        factory.addStep(self.shell_command(
            'pytest',
            ['pytest']))
        cmd_prefix = 'lexibank.' if self.org == 'lexibank' else ''
        factory.addStep(self.shell_command(
            'check',
            ["cldfbench", "--log-level", "WARN", cmd_prefix + "check", self.name],
            decodeRC={0: results.SUCCESS, 2: results.WARNINGS},
            warnOnWarnings=True,
        ))
        return factory


with pathlib.Path(__file__).parent.joinpath('reposlist.json').open(encoding='utf8') as fp:
    DATASETS = [Dataset(*args) for args in json.load(fp)]

if platform.node() == 'dlt4803010l':
    DATASETS = [ds for ds in DATASETS if ds.name in [
        'dryerorder',
        'chenhmongmien',
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
c['schedulers'] = [
    schedulers.Triggerable(name="release", builderNames=[ds.id for ds in DATASETS]),
    schedulers.ForceScheduler(name="release-force", builderNames=['release'])
]
for ds in DATASETS:
    c['schedulers'].extend(ds.schedulers)


####### BUILDERS

# The 'builders' list defines the Builders, which tell Buildbot how to perform a build:
# what steps, and which workers can execute them.  Note that any particular build will
# only take place on one worker.

release = util.BuildFactory()
release.addStep(steps.Trigger(schedulerNames=['release'], waitForFinish=False))
c['builders'] = [util.BuilderConfig(name='release', workernames=["worker"], factory=release)]

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

c['buildbotURL'] = "http://localhost:8010/"

# minimalistic config to activate new web UI
c['www'] = dict(
    port=8010,
    plugins=dict(waterfall_view={}, console_view={}, grid_view={}),
    ui_default_config={'Builders.buildFetchLimit': 200},
)

####### DB URL

c['db'] = {
    # This specifies what database buildbot uses to store its state.
    # It's easy to start with sqlite, but it's recommended to switch to a dedicated
    # database, such as PostgreSQL or MySQL, for use in production environments.
    # http://docs.buildbot.net/current/manual/configuration/global.html#database-specification
    'db_url': "sqlite:///state.sqlite",
}
