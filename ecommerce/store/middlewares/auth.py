from urllib.parse import quote

from django.http import HttpResponseRedirect


def auth_middleware(get_response):
    def middleware(request, *args, **kwargs):
        if not request.session.get('customer'):
            # Send the visitor to login, remembering where they were headed so
            # they land back there after signing in.
            return HttpResponseRedirect('/login/?return_url=' + quote(request.get_full_path()))
        return get_response(request, *args, **kwargs)

    return middleware
