"""URLconf for DjangoIntegration tests (no middleware)."""

from django.http import HttpResponse
from django.urls import path


def ok(_request):
    return HttpResponse("ok")


def boom(_request):
    raise ValueError("intentional explosion")


urlpatterns = [
    path("ok/", ok, name="ok"),
    path("boom/", boom, name="boom"),
]
