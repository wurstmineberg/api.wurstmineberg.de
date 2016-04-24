#!/usr/bin/env python

from distutils.core import setup

setup(name='api.wurstmineberg.de',
      version='1.0',
      description='',
      author='Wurstmineberg',
      author_email='mail@wurstmineberg.de',
      packages=["api"],
      package_data={"api": ["assets/*.json"]}
     )

