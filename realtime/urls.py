# realtime/urls.py
from django.urls import path
from . import views

urlpatterns = [
    path('', views.index, name='realtime_index'),
    path("chat/", views.realtime_chat, name="realtime_chat"),
    # Add more endpoints as needed.
]
