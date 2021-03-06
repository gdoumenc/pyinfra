# pyinfra
# File: pyinfra/modules/yum.py
# Desc: manage yum packages & repositories

'''
Manage yum packages and repositories. Note that yum package names are case-sensitive.
'''

from __future__ import unicode_literals

from six import StringIO
from six.moves.urllib.parse import urlparse

from pyinfra.api import operation

from . import files
from .util.packaging import ensure_packages


@operation
def key(state, host, key):
    '''
    Add yum gpg keys with ``rpm``.

    + key: filename or URL

    Note:
        always returns one command, not state checking
    '''

    yield 'rpm --import {0}'.format(key)


@operation
def repo(
    state, host, name, baseurl,
    present=True, description=None, enabled=True, gpgcheck=True, gpgkey=None,
):
    '''
    Manage yum repositories.

    + name: filename for the repo (in ``/etc/yum/repos.d/``)
    + baseurl: the baseurl of the repo
    + present: whether the ``.repo`` file should be present
    + description: optional verbose description
    + gpgcheck: whether set ``gpgcheck=1``
    + gpgkey: the URL to the gpg key for this repo
    '''

    # Description defaults to name
    description = description or name

    filename = '/etc/yum.repos.d/{0}.repo'.format(name)

    # If we don't want the repo, just remove any existing file
    if not present:
        yield files.file(state, host, filename, present=False)
        return

    # Build the repo file from string
    repo_lines = [
        '[{0}]'.format(name),
        'name={0}'.format(description),
        'baseurl={0}'.format(baseurl),
        'enabled={0}'.format(1 if enabled else 0),
        'gpgcheck={0}'.format(1 if gpgcheck else 0),
    ]

    if gpgkey:
        repo_lines.append('gpgkey={0}'.format(gpgkey))

    repo_lines.append('')
    repo = '\n'.join(repo_lines)
    repo = StringIO(repo)

    # Ensure this is the file on the server
    yield files.put(state, host, repo, filename)


@operation
def rpm(state, host, source, present=True):
    '''
    Install/manage ``.rpm`` file packages.

    + source: filename or URL of the ``.rpm`` package
    + present: whether ore not the package should exist on the system

    URL sources with ``present=False``:
        If the ``.rpm`` file isn't downloaded, pyinfra can't remove any existing
        package as the file won't exist until mid-deploy.
    '''

    # If source is a url
    if urlparse(source).scheme:
        # Generate a temp filename (with .rpm extension to please yum)
        temp_filename = '{0}.rpm'.format(state.get_temp_filename(source))

        # Ensure it's downloaded
        yield files.download(state, host, source, temp_filename)

        # Override the source with the downloaded file
        source = temp_filename

    # Check for file .rpm information
    info = host.fact.rpm_package(source)
    exists = False

    # We have info!
    if info:
        current_packages = host.fact.rpm_packages

        if (
            info['name'] in current_packages
            and info['version'] in current_packages[info['name']]
        ):
            exists = True

    # Package does not exist and we want?
    if present and not exists:
        # If we had info, always install
        if info:
            yield 'rpm -U {0}'.format(source)

        # This happens if we download the package mid-deploy, so we have no info
        # but also don't know if it's installed. So check at runtime, otherwise
        # the install will fail.
        else:
            yield 'rpm -qa | grep `rpm -qp {0}` || rpm -U {0}'.format(source)

    # Package exists but we don't want?
    if exists and not present:
        yield 'yum remove -y {0}'.format(info['name'])


@operation
def update(state, host):
    '''
    Updates all yum packages.
    '''

    yield 'yum update -y'

_update = update  # noqa


@operation
def packages(
    state, host, packages=None,
    present=True, latest=False, update=False, clean=False,
):
    '''
    Manage yum packages & updates.

    + packages: list of packages to ensure
    + present: whether the packages should be installed
    + latest: whether to upgrade packages without a specified version
    + update: run yum update
    + clean: run yum clean
    '''

    if clean:
        yield 'yum clean all'

    if update:
        yield _update(state, host)

    yield ensure_packages(
        packages, host.fact.rpm_packages, present,
        install_command='yum install -y',
        uninstall_command='yum remove -y',
        upgrade_command='yum update -y',
        latest=latest,
    )
