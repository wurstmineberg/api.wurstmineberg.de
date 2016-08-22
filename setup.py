#!/usr/bin/env python

from setuptools import setup

setup(name='api.wurstmineberg.de',
      description='',
      author='Wurstmineberg',
      author_email='mail@wurstmineberg.de',
      packages=["api"],
      use_scm_version = {
            "write_to": "api/_version.py",
          },
      setup_requires=["setuptools_scm"],
      package_data={"api": ["assets/*.json"]}
     )

