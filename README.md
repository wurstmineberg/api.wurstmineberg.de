This is [Wurstmineberg](http://wurstmineberg.de/)'s Minecraft API, an API server using [bottle.py](http://bottlepy.org/) that exposes [Minecraft](http://minecraft.net/) server data via [JSON](http://www.json.org/). It is not to be confused with [Minecraft's official API](http://minecraft.gamepedia.com/Plugin_API) which is currently in development.

It can be found live on http://api.wurstmineberg.de/.

This is version 2.0.0 of the API ([semver](http://semver.org/)). A list of available endpoints along with brief documentation can be found on its index page.

Requirements
============

*   [Python](http://python.org/) 3.4
*   [Pillow](http://pypi.python.org/pypi/Pillow) 3.0 (required for image-producing endpoints only)
*   [anvil](https://github.com/wurstmineberg/anvil) (required for chunk endpoints only)
*   [bottle](http://bottlepy.org/) 0.12
*   [mcstatus](https://github.com/Dinnerbone/mcstatus) 2.1 (required for world status endpoints only)
*   [minecraft-backuproll](https://github.com/wurstmineberg/minecraft-backuproll) 0.1 (required for world backup endpoints only)
*   [more-itertools](https://pypi.python.org/pypi/more-itertools/) 2.2
*   [nbt](https://pypi.python.org/pypi/NBT) 1.4
*   [people](https://github.com/wurstmineberg/people) (required for people.json features only)
*   [playerhead](https://github.com/wurstmineberg/playerhead) 3.0 (required for skin rendering endpoints only)
*   [requests](http://python-requests.org/) 2.7
*   [systemd-minecraft](https://github.com/wurstmineberg/systemd-minecraft)

Configuration
=============

[This guide](http://michael.lustfield.net/nginx/bottle-uwsgi-nginx-quickstart) describes how to set up a bottle.py application such as this API using [nginx](http://wiki.nginx.org/). Just use [`api.py`](api.py) instead of writing your own `app.py` as in the guide.

If you're using [the Apache httpd](http://httpd.apache.org/) or another web server, you're on your own for setting up the API.

Some endpoints use logs generated by [wurstminebot](https://github.com/wurstmineberg/wurstminebot). If you don't run a wurstminebot on your server, you will have to provide logs in a compatible format in order to use these endpoints.

You can provide a configuration file in `/opt/wurstmineberg/config/api.json` to customize some behavior. Here are the default values:

```json
{
    "cache": "/opt/wurstmineberg/api-cache",
    "host": "wurstmineberg.de",
    "isDev": false,
    "jlogPath": "/opt/wurstmineberg/jlog",
    "logPath": "/opt/wurstmineberg/log",
    "moneysFile": "/opt/wurstmineberg/moneys/moneys.json",
    "webAssets": "/opt/git/github.com/wurstmineberg/assets.wurstmineberg.de/master",
    "worldHost": "wurstmineberg.de"
}
```
