# new_api/urls.py
from django.urls import path
from .views import example_endpoint, evaluate_history, compare_answer, generate_tree, mark_conversation

urlpatterns = [
    path('example/', example_endpoint, name='example_endpoint'),
    path('evaluate-history/', evaluate_history, name='evaluate_history'),
    path('compare-answer/', compare_answer, name='compare_answer'),
    path('generate-decision-tree/', generate_tree, name='generate_decision_tree'),
    path('mark-conversation/', mark_conversation, name='mark_conversation'),
]
