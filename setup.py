#!/usr/bin/env python

import setuptools

setuptools.setup(
    name='api.wurstmineberg.de',
    description='',
    author='Wurstmineberg',
    author_email='mail@wurstmineberg.de',
    packages=["api"],
    package_data={"api": ["assets/*.json"]},
    use_scm_version = {
        "write_to": "api/_version.py"
    },
    setup_requires=["setuptools_scm"],
    install_requires=[
        'NBT',
        'Pillow',
        'anvil',
        'bottle',
        'minecraft',
        'mcstatus',
        'more-itertools',
        'people',
        'playerhead',
        'requests',
        'setuptools-scm'
    ],
    dependency_links=[
        'git+https://github.com/wurstmineberg/python-anvil.git#egg=anvil',
        'git+https://github.com/wurstmineberg/systemd-minecraft.git#egg=minecraft',
        'git+https://github.com/wurstmineberg/people.git#egg=people',
        'git+https://github.com/wurstmineberg/playerhead.git#egg=playerhead'
    ]
)
