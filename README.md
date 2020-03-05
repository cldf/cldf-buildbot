# cldf-buildbot

[Buildbot](http://buildbot.net/) configuration to provide CI for 
[cldfbench](https://github.com/cldf/cldfbench) curated datasets.


## Install and deploy

```shell script
python -m venv env
source ./env/bin/activate
git clone https://github.com/cldf/cldf-buildbot.git
pip install -r cldf-buildbot/requirements.txt
```


### Setup master

```shell script
buildbot create-master -c config.py cldf-buildbot
buildbot start cldf-buildbot
````

### Setup a worker

```shell script
buildbot-worker create-worker worker localhost worker pass
buildbot-worker start worker
```


## Usage

The UI of Buildbot is served at http://localhost:8010

### Building one repository

* click on "builds -> builders" in left menu.
* select a repository
* click "force" button on top right
* start build

### Building all

* select "release" builder
* click "force" button on top right
* will trigger builds of all other repos


## TODO:

* parsing of errors/warnings?
