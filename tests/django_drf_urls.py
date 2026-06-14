"""URLconf for DRF DjangoIntegration tests."""

from django.urls import path
from rest_framework.response import Response
from rest_framework.views import APIView


class OkView(APIView):
    def get(self, _request):
        return Response({"status": "ok"})


class BoomView(APIView):
    def get(self, _request):
        raise ValueError("drf intentional explosion")


class BadRequestView(APIView):
    def get(self, _request):
        from rest_framework.exceptions import ValidationError

        raise ValidationError("bad input")


urlpatterns = [
    path("api/ok/", OkView.as_view(), name="api-ok"),
    path("api/boom/", BoomView.as_view(), name="api-boom"),
    path("api/bad-request/", BadRequestView.as_view(), name="api-bad-request"),
]
