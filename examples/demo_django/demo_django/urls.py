from django.urls import path

from demoapp import views

urlpatterns = [
    path("", views.home, name="home"),
    path("boom/", views.boom, name="boom"),
    path("notice/", views.notice, name="notice"),
]
