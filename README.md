This is [Wurstmineberg](http://wurstmineberg.de/)'s Minecraft API, an API server using [bottle.py](http://bottlepy.org/) that exposes [Minecraft](http://minecraft.net/) server data via [JSON](http://www.json.org/). It is not to be confused with Minecraft's official API which is currently in development.

It can be found live on http://api.wurstmineberg.de/.

This is version 1.9.1 of the API ([semver](http://semver.org/)). A list of available endpoints along with brief documentation can be found on its index page.

Configuration
=============

[This guide](http://michael.lustfield.net/nginx/bottle-uwsgi-nginx-quickstart) describes how to set up a bottle.py application such as this API using [nginx](http://wiki.nginx.org/). Just use [`api.py`](api.py) instead of writing your own `app.py` as in the guide.

If you're using [the Apache httpd](http://httpd.apache.org/) or another web server, you're on your own for setting up the API.
