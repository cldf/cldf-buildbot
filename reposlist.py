"""
Refresh the repository list.

Usage:
    python reposlist.py GITHUB_ACCESS_TOKEN

We may want to replace this with or call this from a fab task.
"""
import json
import pathlib

from github import Github, GithubException

ORGS = ['lexibank', 'cldf-datasets']


def iter_repos(gh):
    for org in ORGS:
        for repo in gh.get_organization(org).get_repos():
            if repo.private:
                continue
            try:
                yield (
                    org,
                    repo.clone_url,
                    [f.path for f in repo.get_contents('cldf') if f.name.endswith('metadata.json')])
            except GithubException:
                continue


def main(gh):
    with pathlib.Path('reposlist.json').open('w', encoding='utf8') as fp:
        json.dump(
            [repo for repo in sorted(iter_repos(gh), key=lambda t: (t[0], t[1])) if repo[2]],
            fp,
            indent=4)


if __name__ == '__main__':
    import sys

    main(Github(sys.argv[1]))
