import bottle

ERROR_PAGE_TEMPLATE = """
%try:
    %from bottle import HTTP_CODES, request
    <!DOCTYPE html>
    <html>
        <head>
            <title>Error: {{e.status}}</title>
            <style type="text/css">
                html {
                    background-color: #eee;
                    font-family: sans;
                }
                body {
                    background-color: #fff;
                    border: 1px solid #ddd;
                    padding: 15px;
                    margin: 15px;
                }
                pre {
                    background-color: #eee;
                    border: 1px solid #ddd;
                    padding: 5px;
                }
            </style>
        </head>
        <body>
            <h1>Error: {{e.status}}</h1>
            <p>Sorry, the requested URL <tt>{{repr(request.url)}}</tt> caused an error:</p>
            <pre>{{e.body}}</pre>
            %if e.exception:
                <h2>Exception:</h2>
                <pre>{{repr(e.exception)}}</pre>
            %end
            %if e.traceback:
                <h2>Traceback:</h2>
                <pre>{{e.traceback}}</pre>
            %end
        </body>
    </html>
%except ImportError:
    <b>ImportError:</b> Could not generate the error page. Please add bottle to
    the import path.
%end
"""

class Bottle(bottle.Bottle):
    def default_error_handler(self, res):
        return bottle.tob(bottle.template(ERROR_PAGE_TEMPLATE, e=res))
