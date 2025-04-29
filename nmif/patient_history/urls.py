from django.contrib import admin
from django.urls import include, path
# Corrected history view imports (already done)
from nmif.history.views import (
    generate_history, ask_question, get_history_categories, get_conditions,
    generate_questions, get_general_condition_categories, get_conditions_by_category,
    get_conditions_by_category_profile, generate_history_with_profile,
    get_category_by_condition_profile, convert_mimic_to_icd # Added convert_mimic_to_icd here assuming it's in history.views
)
# Removed redundant 'from nmif.history import views'
from django.conf import settings
from django.conf.urls.static import static

urlpatterns = [
    path("admin/", admin.site.urls),
    # --- Corrected Includes ---
    path('api/', include('nmif.marking_scheme_endpoints.urls')),
    path('realtime-endpoints/', include('nmif.realtime_endpoints.urls')), # Verify 'realtime_endpoints' is inside 'nmif'
    # --- End Correction ---

    # --- Direct paths to history views (These define the URL names) ---
    path("generate-history/", generate_history, name="generate_history"),
    path("ask-question/", ask_question, name="ask_question"),
    path("get-history-categories/", get_history_categories, name="get_history_categories"),
    path("get-conditions/", get_conditions, name="get_conditions"),
    path('generate-questions/', generate_questions, name='generate_questions'),
    path('get_general_condition_categories/', get_general_condition_categories, name = 'get_general_condition_categories'),
    path('get_conditions_by_category/', get_conditions_by_category, name = 'get_conditions_by_category'),
    path('get_conditions_by_category_profile/', get_conditions_by_category_profile, name='get_conditions_by_category_profile'),
    path("generate-history-with-profile/", generate_history_with_profile, name="generate_history_with_profile"),
    path('get-category-by-condition-profile/', get_category_by_condition_profile, name='get_category_by_condition_profile'), # Note: Name was different before, adjusted for consistency, verify if intended.
    # --- MISSING URL for convert_mimic_to_icd ---
    # You need to add a path for the convert_mimic_to_icd view if you want to test it via reverse()
    path('convert-mimic-to-icd/', convert_mimic_to_icd, name='convert_mimic_to_icd'), # Example path and name

] + static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)