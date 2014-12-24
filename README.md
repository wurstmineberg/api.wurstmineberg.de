This is [Wurstmineberg](http://wurstmineberg.de/)'s Minecraft API, an API server using [bottle.py](http://bottlepy.org/) that exposes [Minecraft](http://minecraft.net/) server data via [JSON](http://www.json.org/). It is not to be confused with [Minecraft's official API](http://minecraft.gamepedia.com/Plugin_API) which is currently in development.

It can be found live on http://api.wurstmineberg.de/.

This is version 1.16.1 of the API ([semver](http://semver.org/)). A list of available endpoints along with brief documentation can be found on its index page.

Requirements
============

*   [Python](http://python.org/) 3.2
*   [Pillow](http://pypi.python.org/pypi/Pillow) 2.5 (required for image-producing endpoints only)
*   [bottle](http://bottlepy.org/) 0.12
*   [nbt](https://pypi.python.org/pypi/NBT) 1.4

Configuration
=============

[This guide](http://michael.lustfield.net/nginx/bottle-uwsgi-nginx-quickstart) describes how to set up a bottle.py application such as this API using [nginx](http://wiki.nginx.org/). Just use [`api.py`](api.py) instead of writing your own `app.py` as in the guide.

If you're using [the Apache httpd](http://httpd.apache.org/) or another web server, you're on your own for setting up the API.

Some endpoints use logs generated by [wurstminebot](https://github.com/wurstmineberg/wurstminebot). If you don't run a wurstminebot on your server, you will have to provide logs in a compatible format in order to use these endpoints.

Some endpoints require the presence of a [People file](http://wiki.wurstmineberg.de/People_file) in order to function. This file can easily be created manually for whitelisted servers (and in fact wurstminebot will maintain it for you).

You can provide a configuration file in `/opt/wurstmineberg/config/api.json` to customize some behavior. Here are the default values:

```json
{
    "jlogPath": "/opt/wurstmineberg/jlog",
    "logPath": "/opt/wurstmineberg/log",
    "peopleFile": "/opt/wurstmineberg/config/people.json",
    "serverDir": "/opt/wurstmineberg/server",
    "webAssets": "/opt/hub/wurstmineberg/assets.wurstmineberg.de/json",
    "worldName": "wurstmineberg"
}
```
