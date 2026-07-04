from django.http import HttpResponseRedirect


def auth_middleware(get_response):
    def middleware(request, *args, **kwargs):
        if not request.session.get('customer'):
            return HttpResponseRedirect('/login')
        return get_response(request, *args, **kwargs)

    return middleware
