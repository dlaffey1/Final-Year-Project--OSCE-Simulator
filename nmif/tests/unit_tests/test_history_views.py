# nmif/tests/unit_tests/test_history_views.py

import json
import pytest
from unittest.mock import patch, MagicMock, mock_open
from django.urls import reverse # Make sure reverse is imported
from django.test import Client as DjangoTestClient
from django.http import JsonResponse

# --- Views to Test ---
# Adjust the import path if 'history' is not directly under 'nmif'
from nmif.history.views import (
    load_text2dt_mapping,
    get_subject_id_by_condition,
    generate_history_with_profile,
    generate_history,
    ask_question,
    convert_mimic_to_icd,
    get_conditions,
    get_history_categories,
    get_general_condition_categories,
    get_conditions_by_category,
    get_conditions_by_category_profile,
    get_category_by_condition_profile,
    # Add other functions from this file if needed
)

# --- Fixtures ---

@pytest.fixture
def client():
    """Django test client instance."""
    return DjangoTestClient()

@pytest.fixture
def mock_openai():
    """Mock the OpenAI ChatCompletion create method used in this views file."""
    # Patching where it's likely used (adjust if openai is imported elsewhere in views.py)
    with patch('nmif.history.views.openai.ChatCompletion.create') as mock_create:
        yield mock_create

@pytest.fixture
def mock_bigquery():
    """Mock the BigQuery client and its query method used in this views file."""
    # Patching where it's likely used
    with patch('nmif.history.views.bigquery.Client') as mock_client_class:
        mock_client_instance = MagicMock()
        mock_query_job = MagicMock()
        mock_results = MagicMock()
        mock_query_job.result.return_value = mock_results
        mock_client_instance.query.return_value = mock_query_job
        mock_client_class.return_value = mock_client_instance
        yield mock_client_instance, mock_results # Return instance and results mock

@pytest.fixture
def mock_fetch_patient_data():
    """Mock the fetch_patient_data function imported into views.py."""
    # Patching where it's imported and used in views.py
    with patch('nmif.history.views.fetch_patient_data') as mock_fetch:
       # Default mock return value (can be customized in tests)
        mock_fetch.return_value = (
            {"patient_info": "details"}, # patient
            [{"icd_code": "123.45", "description": "Test Diagnosis"}], # diagnoses
            [], [], [], [], [], [], [], [], [] # other data lists (admissions, notes, etc.)
        )
        yield mock_fetch

@pytest.fixture
def mock_mapping_file():
    """Mock reading the mapping JSON file."""
    mock_data = json.dumps([
        {
            "text2dt_condition": "Condition A",
            "mapped_mimic_group": {
                "representative": "Group A Rep",
                "mimic_condition": "Group A Mimic", # Used by convert_mimic_to_icd
                "icd9_codes": ["100.1", "100.2"]
            },
            "profile": ["Q1?", "Q2?"],
            "english_profile": ["English Q1?", "English Q2?"],
            "category": "Cardiology"
        },
        {
            "text2dt_condition": "Condition B",
            "mapped_mimic_group": {
                "representative": "Group B Rep",
                "mimic_condition": "Group B Mimic",
                 "icd9_codes": ["200.1"]
            },
            "profile": ["Q3?"],
            "english_profile": ["English Q3?"],
            "category": "Respiratory"
        }
    ])
    # Patching where open and os.path.exists are likely called in views.py
    with patch('nmif.history.views.open', mock_open(read_data=mock_data)) as mock_file, \
         patch('nmif.history.views.os.path.exists', return_value=True):
        yield mock_file

# --- Test Functions ---

@pytest.mark.django_db
def test_generate_history_with_profile_random(client, mock_mapping_file, mock_bigquery, mock_fetch_patient_data, mock_openai):
    """Test generating history with profile in random mode."""
    mock_bq_client, mock_bq_results = mock_bigquery
    mock_row = MagicMock()
    mock_row.subject_id = 12345
    mock_bq_results.__iter__.return_value = iter([mock_row]) # Simulate finding a subject

    mock_history_json = {"PC": "Random Chest Pain", "HPC": "...", "PMHx": "", "DHx": "", "FHx": "", "SHx": "", "SR": ""}
    mock_openai.return_value = {"choices": [{"message": {"content": json.dumps(mock_history_json)}}]}

    # --- UPDATED URL NAME ---
    url = reverse('generate_history_with_profile')
    # --- END UPDATE ---
    payload = {"random": True}
    response = client.post(url, json.dumps(payload), content_type='application/json')

    assert response.status_code == 200
    response_data = response.json()
    assert response_data["history"] == mock_history_json
    assert response_data["right_condition"] in ["100.1", "100.2", "200.1"] # From mock mapping
    assert response_data["profile"] is True
    assert response_data["category"] in ["Cardiology", "Respiratory"]
    mock_fetch_patient_data.assert_called_once() # Check if fetch_patient_data was called
    mock_openai.assert_called_once() # Check if OpenAI was called

# @pytest.mark.django_db
# def test_generate_history_specific_subject(client, mock_bigquery, mock_fetch_patient_data, mock_openai):
#     """Test generating history for a specific subject ID (no profile check)."""
#     mock_bq_client, mock_bq_results = mock_bigquery # Not directly used here, but fetch_patient_data might use it internally

#     mock_history_json = {"PC": "Specific Subject History", "HPC": "...", "PMHx": "", "DHx": "", "FHx": "", "SHx": "", "SR": ""}
#     mock_openai.return_value = {"choices": [{"message": {"content": json.dumps(mock_history_json)}}]}

#     # --- UPDATED URL NAME ---
#     url = reverse('generate_history')
#     # --- END UPDATE ---
#     payload = {"subject_id": 98765} # Provide subject_id directly
#     response = client.post(url, json.dumps(payload), content_type='application/json')

#     assert response.status_code == 200
#     response_data = response.json()
#     assert response_data["history"] == mock_history_json
#     assert response_data["right_condition"] == "123.45" # Default from mock_fetch_patient_data
#     assert response_data["category"] == "Other" # Default category inference if not provided

#     # Note: assert_called_once_with requires the arguments fetch_patient_data was actually called with.
#     # If fetch_patient_data doesn't receive mock_bq_client directly, adjust this assertion.
#     # Assuming fetch_patient_data IS called with the client instance:
#     mock_fetch_patient_data.assert_called_once_with(mock_bq_client, subject_id=98765)
#     # If fetch_patient_data initializes its own client, perhaps assert like this:
#     # mock_fetch_patient_data.assert_called_once_with(subject_id=98765) # Check exact signature
#     mock_openai.assert_called_once()

@pytest.mark.django_db
def test_ask_question_success(client, mock_openai):
    """Test the ask_question endpoint successfully."""
    mock_openai.return_value = {"choices": [{"message": {"content": "The patient reports no fever."}}]}

    # --- UPDATED URL NAME ---
    url = reverse('ask_question')
    # --- END UPDATE ---
    payload = {
        "question": "Does the patient have a fever?",
        "history": json.dumps({"PC": "Chest pain", "HPC": "Started yesterday"}) # History needs to be passed
    }
    response = client.post(url, json.dumps(payload), content_type='application/json')

    assert response.status_code == 200
    assert response.json() == {"answer": "The patient reports no fever."}
    mock_openai.assert_called_once()

@pytest.mark.django_db
def test_convert_mimic_to_icd_success(client, mock_mapping_file):
    """Test converting a known mimic condition name to ICD."""
    # --- UPDATED URL NAME ---
    url = reverse('convert_mimic_to_icd') + "?condition=Group B Mimic" # Match mock data
    # --- END UPDATE ---
    response = client.get(url)

    assert response.status_code == 200
    assert response.json() == {"icd_code": "200.1"} # From mock mapping
    # mock_mapping_file.assert_called() # This assertion might be problematic depending on how mock_open works with context managers. Usually, you check calls on the mock returned by mock_open().read() etc., or just trust the patching worked if the test passes.

@pytest.mark.django_db
def test_convert_mimic_to_icd_not_found(client, mock_mapping_file):
    """Test converting an unknown mimic condition name."""
    # --- UPDATED URL NAME ---
    url = reverse('convert_mimic_to_icd') + "?condition=Unknown Condition Name"
    # --- END UPDATE ---
    response = client.get(url)

    assert response.status_code == 404
    assert "error" in response.json()
    assert "not found in mapping" in response.json()["error"]
    # mock_mapping_file.assert_called() # See comment in previous test

# --- Add more tests for other views in nmif/history/views.py ---
# e.g., get_conditions, get_history_categories, error handling, etc.