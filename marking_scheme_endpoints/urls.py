# new_api/urls.py
from django.urls import path
from .views import example_endpoint, evaluate_history, compare_answer

urlpatterns = [
    path('example/', example_endpoint, name='example_endpoint'),
    path('evaluate-history/', evaluate_history, name='evaluate_history'),
    path('compare-answer/', compare_answer, name='compare_answer'),
]
