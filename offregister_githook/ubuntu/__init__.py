from operator import le
from os import path

from offregister_fab_utils.misc import require_os_version
from offregister_fab_utils.ubuntu.version import ubuntu_version
from offutils import update_d, validate_conf
from pkg_resources import resource_filename

from fabric.operations import sudo, run
from fabric.contrib.files import upload_template, exists

from offregister_fab_utils.apt import apt_depends

from offregister_githook import __author__, logger


def install_hookserve0(*args, **kwargs):
    gz = 'hookserve.gz'
    base = gz.partition(path.extsep)[0]
    if not exists('/usr/local/bin/{base}'.format(base=base)):
        apt_depends('ca-certificates', 'curl')
        run('mkdir -p Downloads')
        run('curl -L https://phayes.github.io/bin/current/hookserve/linux/{gz} -o Downloads/{gz}'.format(gz=gz))
        sudo('zcat Downloads/{gz} > /usr/local/bin/{base}'.format(gz=gz, base=base))
        sudo('chmod +x /usr/local/bin/{base}'.format(base=base))


def setup_hookserve1(*args, **kwargs):
    os_version = ubuntu_version()

    default_conf = {
        'AUTHOR': __author__,
        'DESCRIPTION': 'hookserve git hook server and git pull task',
        'DAEMON': '/usr/local/bin/hookserve',
        'DAEMON_ARGS': '--port={DAEMON_PORT:d} echo',
        'DAEMON_PORT': 8888,
        'PID': '/var/run/hookserve.pid'
    }

    context = update_d(default_conf, kwargs.get('hookserve-init-context', {}))
    context['DAEMON_ARGS'] = context['DAEMON_ARGS'].format(DAEMON_PORT=context['DAEMON_PORT'])

    if os_version < 15.04:
        init_dir = kwargs.get('hookserve-init-dir', '/etc/init')
        init_name = '{}.service'.format(
            kwargs['hookserve-init-name']) if 'hookserve-init-name' in kwargs else 'hookserve.conf'
        init_local_filename = kwargs.get('hookserve-upstart-filename',
                                         resource_filename('offregister_githook',
                                                           path.join('conf', 'hookserve.upstart.conf')))
        service = init_name.partition('.')[0]

        upload_template(init_local_filename, '{init_dir}/{init_name}'.format(init_dir=init_dir, init_name=init_name),
                        context=context, use_sudo=True)

        status_cmd = 'status {service}'.format(service=service)
        if 'start/running' in run(status_cmd):
            sudo('stop {service}'.format(service=service))
        sudo('start {service}'.format(service=service))
        return run(status_cmd)
    else:
        unit_name = '{}.unit'.format(
            kwargs['hookserve-init-name']) if 'hookserve-init-name' in kwargs else 'hookserve.unit'
        unit_local_filename = kwargs.get('hookserve-upstart-filename',
                                         resource_filename('offregister_githook',
                                                           path.join('conf', 'hookserve.systemd.unit')))
        service = unit_name.partition('.')[0]
        unit_file = '/etc/systemd/system/{init_name}'.format(init_name=unit_name)

        upload_template(unit_local_filename, unit_file, context=context, use_sudo=True)
        sudo('chmod 664 {unit_file}'.format(unit_file=unit_file))
        sudo('systemctl daemon-reload')
        status_cmd = 'systemctl status {service}'.format(service=service)
        if 'start/running' in run(status_cmd):
            sudo('systemctl stop {service}'.format(service=service))
        sudo('systemctl start {service}'.format(service=service))
        return run(status_cmd)


@require_os_version(15.04, le)
def setup_git_pull_upstart2(*args, **kwargs):
    if exists('/run/systemd/system'):
        raise NotImplementedError('SystemD not implemented yet')

    apt_depends('inotify-tools')

    default_conf = {
        'AUTHOR': __author__,
        'DESCRIPTION': 'git pull (force update to whatever is on git repo)',
        'GIT_BRANCH': 'master',
        'GIT_REMOTE': 'origin',
        'HOOKSERVE_LOGFILE': '/var/log/upstart/{service}.log'.format(
            service=kwargs.get('hookserve-init-name', 'hookserve.conf').partition(path.extsep)[0]
        )
    }
    if 'SERVER_LOCATION' in kwargs.get('git_pull-init-context', {}):
        kwargs['git_pull-init-context']['GIT_DIR'] = kwargs['git_pull-init-context']['SERVER_LOCATION']

    required = (('GIT_DIR', '/var/www/somegitrepo'), ('GIT_REPO', 'https://github.com/foo/bar.git'))
    validate_conf(kwargs.get('git_pull-init-context', {}), required, logger=logger, name='git_pull-init-context')

    if not exists(kwargs['git_pull-init-context']['GIT_DIR']):
        sudo('git clone {git_repo} {to_dir}'.format(
            git_repo=kwargs['git_pull-init-context']['GIT_REPO'],
            to_dir=kwargs['git_pull-init-context']['GIT_DIR']
        ))

    init_name = kwargs.get('git_pull-init-name', 'git_pull.conf')
    init_dir = kwargs.get('git_pull-init-dir', '/etc/init')
    init_local_filename = kwargs.get('git_pull-upstart-filename',
                                     resource_filename('offregister_githook',
                                                       path.join('conf', 'git_pull.upstart.job.conf')))
    service = init_name.partition('.')[0]

    upload_template(init_local_filename, '{init_dir}/{init_name}'.format(init_dir=init_dir, init_name=init_name),
                    context=update_d(default_conf, kwargs.get('git_pull-init-context', {})), use_sudo=True)

    status_cmd = 'status {service}'.format(service=service)
    if 'start/running' in run(status_cmd):
        sudo('stop {service}'.format(service=service))

    logger.info(sudo('start {service}'.format(service=service)))
    return run(status_cmd)
