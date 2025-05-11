"""patient_history URL Configuration

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/3.2/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import include, path
from django.contrib import admin
from history.views import generate_history, ask_question, get_history_categories, get_conditions, generate_questions, get_general_condition_categories, get_conditions_by_category, get_conditions_by_category_profile, generate_history_with_profile, get_category_by_condition_profile, convert_mimic_to_icd, convert_icd_to_condition
from history import views
from django.conf import settings
from django.conf.urls.static import static
urlpatterns = [
    path("admin/", admin.site.urls),
    path('api/', include('marking_scheme_endpoints.urls')),
    path('realtime-endpoints/', include('realtime_endpoints.urls')),
    path("generate-history/", generate_history, name="generate_history"),
    path("ask-question/", ask_question, name="ask_question"),
    path("get-history-categories/", get_history_categories, name="get_history_categories"),
    path("get-conditions/", get_conditions, name="get_conditions"),
    path("convert_mimic_to_icd/", convert_mimic_to_icd, name="convert_mimic_to_icd"),
    path("convert_icd_to_condition/", convert_icd_to_condition, name="convert_icd_to_condition"),
    path('generate-questions/', generate_questions, name='generate_questions'),
    path('get_general_condition_categories/', get_general_condition_categories, name = 'get_general_condition_categories'),
    path('get_conditions_by_category/', get_conditions_by_category, name = 'get_conditions_by_category'),
    path('get_conditions_by_category_profile/', get_conditions_by_category_profile, name='get_conditions_by_category_profile'),
    path("generate-history-with-profile/", generate_history_with_profile, name="generate_history_with_profile"),
    path('get-category-by-condition-profile/', get_category_by_condition_profile, name='get_marking_results_by_category'),
] + static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)


