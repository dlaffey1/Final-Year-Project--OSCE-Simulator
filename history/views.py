import json
import os
import re  # Ensure this import is present!
import openai
import logging
from google.cloud import bigquery  # Import BigQuery client
import uuid
from django.http import JsonResponse
from django.shortcuts import render
from django.views.decorators.csrf import csrf_exempt
import random

# Import your fetch_patient_data (which now works with BigQuery)
from AIHistory import fetch_patient_data  # Assume this now works with BigQuery
from dotenv import load_dotenv

load_dotenv()
# Set up logging
logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.DEBUG)

# Define a base path for saving raw MIMIC data.
# (In production, you might use session storage or a caching system.)
MIMIC_DATA_BASE = "/tmp"
# Load condition mapping from JSON file
@csrf_exempt
def load_text2dt_mapping():
    mapping_file = "text2dt_mimic_mapping_english-full-profile.json"
    if not os.path.exists(mapping_file):
        logger.error(f"Mapping file {mapping_file} not found.")
        return None
    try:
        with open(mapping_file, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"Error reading mapping file: {e}")
        return None

# NEW: Helper function to automatically get a subject_id based on condition ICD code.
def get_subject_id_by_condition(condition_icd):
    """
    Query BigQuery to find a patient (subject_id) that has a diagnosis with the given ICD code.
    Since the table stores ICD codes without a decimal point, both the stored value and the 
    provided ICD code are compared after removing any dots.
    Returns the subject_id if found; otherwise, returns None.
    """
    try:
        client = bigquery.Client()
        query = """
            SELECT DISTINCT subject_id 
            FROM `fyp-project-451413.mimic_iii_local.DIAGNOSES_ICD`
            WHERE REPLACE(TRIM(ICD9_CODE), '.', '') = REPLACE(@icd, '.', '')
            LIMIT 1
        """
        job_config = bigquery.QueryJobConfig(
            query_parameters=[
                bigquery.ScalarQueryParameter("icd", "STRING", condition_icd)
            ]
        )
        query_job = client.query(query, job_config=job_config)
        results = query_job.result()
        for row in results:
            logger.info(f"Found subject_id {row.subject_id} for ICD code {condition_icd}")
            return row.subject_id
        logger.warning(f"No subject found with ICD code {condition_icd}")
        return None
    except Exception as e:
        logger.error("Error querying subject id: %s", e)
        return None

@csrf_exempt
def generate_history_with_profile(request):
    """
    Generates a structured patient history for a condition that exists in the
    `text2dt_mimic_mapping_english-full-profile.json` mapping file.

    The `category` is dynamically extracted from the chosen mapping entry.

    Expected JSON payload (optional):
    {
        "condition": "<mimic_condition_or_icd9_code>",
        "random": true
    }

    Returns:
    {
        "history": { ... },
        "right_condition": "<mimic_icd_code>",
        "profile": true,
        "category": "<category>"
    }
    """
    logger.info("Received request to generate history with profile.")

    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON"}, status=400)

    mapping_data = load_text2dt_mapping()
    if mapping_data is None:
        return JsonResponse({"error": "Mapping file not found or could not be loaded."}, status=500)

    def extract_icd_code(entry):
        group = entry.get("mapped_mimic_group", {})
        icd_codes = group.get("icd9_codes")
        if icd_codes and isinstance(icd_codes, list) and len(icd_codes) > 0:
            return icd_codes[0]
        return group.get("mimic_condition_number", group.get("mimic_condition", "Unknown"))

    chosen_entry = None
    condition_icd = None
    category = "other"

    # Random selection mode
    if data.get("random", False):
        chosen_entry = random.choice(mapping_data)
        condition_icd = extract_icd_code(chosen_entry)
        logger.info(f"Random condition selected: ICD = {condition_icd}")
    
    # Specific condition mode
    else:
        condition = str(data.get("condition", "")).strip()
        if not condition:
            chosen_entry = random.choice(mapping_data)
            condition_icd = extract_icd_code(chosen_entry)
            logger.info(f"No condition provided. Randomly selected ICD: {condition_icd}")
        elif condition.replace(".", "", 1).isdigit():
            condition_icd = condition
            chosen_entry = next(
                (entry for entry in mapping_data
                 if condition_icd in [code.replace(".", "").lstrip("0") for code in entry.get("mapped_mimic_group", {}).get("icd9_codes", [])]),
                None
            )
            logger.info(f"Numeric condition received. Matched entry: {bool(chosen_entry)}")
        else:
            # Word-based condition matching
            chosen_entry = next(
                (entry for entry in mapping_data
                 if entry.get("mapped_mimic_group", {}).get("mimic_condition") == condition),
                None
            )
            if not chosen_entry:
                logger.warning(f"Condition '{condition}' not found in mapping.")
                return JsonResponse({"error": f"Condition '{condition}' is not in the mapping."}, status=404)
            icd_codes = chosen_entry.get("mapped_mimic_group", {}).get("icd9_codes", [])
            if not icd_codes:
                return JsonResponse({"error": f"No ICD code found for condition '{condition}'."}, status=404)
            condition_icd = icd_codes[0]
            logger.info(f"Condition '{condition}' resolved to ICD: {condition_icd}")

    if not chosen_entry:
        return JsonResponse({"error": f"No matching entry found for condition '{condition_icd}'."}, status=404)

    # Extract category from the chosen profile-mapped entry
    category = chosen_entry.get("category", "other")
    logger.info(f"Extracted category: {category}")

    # Fetch a subject ID from BigQuery using the ICD code
    subject_id = get_subject_id_by_condition(condition_icd)
    if subject_id is None:
        return JsonResponse({"error": f"No patient found with condition ICD code {condition_icd}."}, status=404)

    # Build request for /generate-history/
    new_request_body = {
        "condition": condition_icd,
        "subject_id": subject_id,
        "category": category  # Pass category along
    }

    request._body = json.dumps(new_request_body).encode("utf-8")

    # Call downstream generator
    response = generate_history(request)

    try:
        response_data = json.loads(response.content)
    except Exception as e:
        logger.error("Error parsing response from generate_history: %s", e)
        return JsonResponse({"error": "Internal server error"}, status=500)

    response_data["right_condition"] = condition_icd
    response_data["profile"] = True
    response_data["category"] = category

    return JsonResponse(response_data)




@csrf_exempt
def convert_mimic_to_icd(request):
    """
    Given a mimic condition name (e.g. "Hypertrophic cardiomyopathy"),
    this endpoint searches the mapping JSON file for an entry where the mimic_condition
    matches the provided value, then returns the first ICD‑9 code from its icd9_codes list.
    
    Example request:
      GET /convert_mimic_to_icd/?condition=Hypertrophic%20cardiomyopathy
      
    Response:
      {
          "icd_code": "425.1"
      }
    """
    logger.info("Received request to convert mimic condition to ICD code.")
    condition = request.GET.get("condition", "").strip()
    if not condition:
        return JsonResponse({"error": "Condition parameter is required."}, status=400)
    
    mapping_data = load_text2dt_mapping()
    if mapping_data is None:
        return JsonResponse({"error": "Mapping file not found or could not be loaded."}, status=500)
    
    # Look for an entry where the mimic_condition matches the provided condition.
    matched_entry = next(
        (entry for entry in mapping_data 
         if entry.get("mapped_mimic_group", {}).get("mimic_condition") == condition),
        None
    )
    
    if not matched_entry:
        logger.warning(f"Condition '{condition}' not found in mapping file.")
        return JsonResponse({"error": f"Condition '{condition}' not found in mapping."}, status=404)
    
    # Extract the first ICD-9 code.
    icd_codes = matched_entry.get("mapped_mimic_group", {}).get("icd9_codes", [])
    if not icd_codes:
        logger.warning(f"No ICD code found for condition '{condition}'.")
        return JsonResponse({"error": f"No ICD code found for condition '{condition}'."}, status=404)
    
    icd_code = icd_codes[0]
    logger.info(f"Found ICD code for condition '{condition}': {icd_code}")
    return JsonResponse({"icd_code": icd_code}, status=200)

@csrf_exempt
def generate_history(request):
    logger.info("Received request to generate history.")

    if request.method == "GET":
        return render(request, "history/index.html")

    if request.method != "POST":
        return JsonResponse({"error": "Invalid request method"}, status=400)

    try:
        data = json.loads(request.body)
    except json.JSONDecodeError as e:
        logger.error("Invalid JSON: %s", e)
        return JsonResponse({"error": "Invalid JSON"}, status=400)

    try:
        client = bigquery.Client()
    except Exception as e:
        logger.error("Failed to initialize BigQuery client: %s", e)
        return JsonResponse({"error": "BigQuery connection failed"}, status=500)

    fallback_condition_name = None
    try:
        if data.get("random"):
            condition, subject_id, condition_name = select_random_condition_and_subject(client)
            if not condition or not subject_id:
                return JsonResponse({"error": "Failed to select random condition or subject"}, status=500)
            data["condition"] = condition
            data["subject_id"] = subject_id
            fallback_condition_name = condition_name
        else:
            subject_id = data.get("subject_id")
            condition = data.get("condition", "").strip()

            if not subject_id:
                if not condition:
                    return JsonResponse({"error": "Condition or subject_id is required"}, status=400)
                if not condition.replace(".", "", 1).isdigit():
                    condition = convert_condition_by_bigquery(condition)
                    if not condition:
                        return JsonResponse({"error": f"Condition '{condition}' not found in mimic database."}, status=404)
                subject_id = get_subject_id_by_condition(condition)
                if not subject_id:
                    return JsonResponse({"error": f"No patient found with condition ICD code {condition}."}, status=404)
                data["condition"] = condition
                data["subject_id"] = subject_id

        subject_id = data["subject_id"]
        condition = data["condition"]
        logger.info(f"Final condition: {condition}, subject_id: {subject_id}")

        (patient, diagnoses, admissions, notes, lab_tests, prescriptions, icu_stays, transfers, procedures, services, microbiology) = fetch_patient_data(client, subject_id=subject_id)
        if not patient:
            return JsonResponse({"error": "No patient data found"}, status=404)

        save_raw_mimic_data(subject_id, patient, admissions, diagnoses, procedures, icu_stays, transfers, services, lab_tests, prescriptions, microbiology, notes)

        prompt = build_prompt(subject_id, patient, admissions, diagnoses, procedures, icu_stays, transfers, services, lab_tests, prescriptions, microbiology, notes)
        gpt_response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "You are a medical assistant providing structured patient histories. Use all the provided raw MIMIC-III data to create a detailed and coherent summary."},
                {"role": "user", "content": prompt}
            ],
            max_tokens=800,
            temperature=0.7,
        )
        history_str = gpt_response["choices"][0]["message"]["content"].strip()

        # === SAFER HISTORY PARSING ===
        try:
            history_data = json.loads(history_str)
        except json.JSONDecodeError:
            logger.warning("Initial JSON parse failed. Attempting to extract embedded JSON.")
            match = re.search(r'```json\s*(\{.*\})\s*```', history_str, re.DOTALL)
            if match:
                try:
                    history_data = json.loads(match.group(1))
                    logger.info("Successfully parsed nested JSON from GPT response.")
                except json.JSONDecodeError:
                    logger.error("Nested JSON still invalid. Returning fallback history.")
                    history_data = {
                        "PC": history_str,
                        "HPC": "", "PMHx": "", "DHx": "", "FHx": "", "SHx": "", "SR": ""
                    }
            else:
                logger.warning("No JSON block found in GPT response. Storing full as PC.")
                history_data = {
                    "PC": history_str,
                    "HPC": "", "PMHx": "", "DHx": "", "FHx": "", "SHx": "", "SR": ""
                }

        # Extract right_condition and fallback to condition_name if needed
        right_condition = extract_right_condition(diagnoses, fallback_condition_name)

        # Try infer category if not given
        category = data.get("category")
        if not category or category.lower() == "other":
            icd_code = None
            for diag in diagnoses:
                if diag.get("icd_code"):
                    icd_code = diag["icd_code"]
                    break
            if icd_code:
                logger.info(f"Attempting to infer category from ICD code: {icd_code}")
                category = get_category_from_icd(client, icd_code)
            else:
                logger.warning("No usable ICD code found to derive category.")
            category = category or "Other"

        return JsonResponse({
            "history": history_data,
            "right_condition": right_condition,
            "category": category
        })

    except Exception as e:
        logger.exception("Unexpected error in generate_history: %s", e)
        return JsonResponse({"error": f"Unexpected error: {str(e)}"}, status=500)

# ========== HELPER FUNCTIONS ==========
def select_random_condition_and_subject(client, max_retries=5):
    logger.info("Selecting random ICD code with matching subject_id...")

    for attempt in range(max_retries):
        logger.debug(f"Attempt #{attempt + 1} to fetch random ICD and subject")

        query = """
            SELECT DISTINCT d.ICD9_CODE AS icd_code, dd.LONG_TITLE AS long_title
            FROM `fyp-project-451413.mimic_iii_local.DIAGNOSES_ICD` d
            JOIN `fyp-project-451413.mimic_iii_local.D_ICD_DIAGNOSES` dd
              ON d.ICD9_CODE = dd.ICD9_CODE
            ORDER BY RAND()
            LIMIT 1
        """

        try:
            results = client.query(query).result()
            row = list(results)[0]
            icd_code = row.icd_code
            condition_name = row.long_title
            logger.info(f"Random ICD: {icd_code} ({condition_name})")

            subject_id = get_subject_id_by_condition(icd_code)
            if subject_id:
                logger.info(f"Found matching subject_id: {subject_id}")
                return icd_code, subject_id, condition_name
            else:
                logger.warning(f"No subject_id found for ICD code: {icd_code}")
        except Exception as e:
            logger.error(f"BigQuery error on attempt #{attempt + 1}: {e}")

    logger.error("Exhausted attempts to select random condition and subject.")
    return None, None, None



def extract_right_condition(diagnoses, fallback_condition_name=None):
    if diagnoses and isinstance(diagnoses, list):
        for diag in diagnoses:
            if diag.get("description"):
                return diag["description"]
            if diag.get("icd_code"):
                return diag["icd_code"]
    if fallback_condition_name:
        return fallback_condition_name
    return "Unknown"


def infer_category_from_diagnoses(client, diagnoses):
    for diag in diagnoses:
        icd = diag.get("icd_code")
        if icd:
            try:
                return get_category_from_icd(client, icd)
            except Exception as e:
                logger.warning("Failed to derive category from ICD: %s", e)
    return None


def save_raw_mimic_data(subject_id, patient, admissions, diagnoses, procedures, icu_stays, transfers, services, lab_tests, prescriptions, microbiology, notes):
    try:
        mimic_data_file = os.path.join(MIMIC_DATA_BASE, f"mimic_data_{subject_id}.json")
        with open(mimic_data_file, "w") as f:
            json.dump({
                "patient": patient,
                "admissions": admissions,
                "diagnoses": diagnoses,
                "procedures": procedures,
                "icu_stays": icu_stays,
                "transfers": transfers,
                "services": services,
                "lab_tests": lab_tests,
                "prescriptions": prescriptions,
                "microbiology": microbiology,
                "notes": notes,
            }, f, indent=2)
        logger.info(f"Saved raw MIMIC data to {mimic_data_file}")
    except Exception as e:
        logger.error(f"Failed to save MIMIC data: {e}")

def build_prompt(subject_id, patient, admissions, diagnoses, procedures, icu_stays, transfers, services, lab_tests, prescriptions, microbiology, notes):
    return f"""
You are provided with detailed MIMIC-III patient data (subject_id={subject_id}). Please analyze the data below and generate a structured patient history with the following headings:
1) Presenting complaint (PC)
2) History of presenting complaint (HPC)
3) Past medical history (PMHx)
4) Drug history (DHx)
5) Family history (FHx)
6) Social history (SHx)
7) Systems review (SR)

Include as many relevant details as possible from the following data sources:

Patient Info (PATIENTS):
{patient}

Admissions (ADMISSIONS):
{admissions}

Diagnoses (DIAGNOSES_ICD + D_ICD_DIAGNOSES):
{diagnoses}

Procedures (PROCEDURES_ICD + D_ICD_PROCEDURES):
{procedures}

ICU Stays (ICUSTAYS):
{icu_stays}

Transfers (TRANSFERS):
{transfers}

Services (SERVICES):
{services}

Lab Tests (LABEVENTS + D_LABITEMS):
{lab_tests}

Prescriptions (PRESCRIPTIONS):
{prescriptions}

Microbiology (MICROBIOLOGYEVENTS):
{microbiology}

Clinical Notes (NOTEEVENTS):
{notes}

Return the entire result as valid JSON with exactly these fields:
{{
  "PC": "...",
  "HPC": "...",
  "PMHx": "...",
  "DHx": "...",
  "FHx": "...",
  "SHx": "...",
  "SR": "..."
}}

Ensure that even if a section is empty, the field is present.
"""


@csrf_exempt
def generate_questions(request):
    """
    This route takes either the original raw MIMIC-III patient data or the generated history details
    as input and returns 4 related questions with their answers.
    
    Expected JSON payload may include:
      - mimic_data: An object containing the raw MIMIC fields.
      - history: An object containing the generated patient history details (fallback).
      - subject_id: A patient identifier to load a saved file if mimic_data isn't provided.
    
    If neither mimic_data nor history is provided, it will try to load from a file using subject_id.
    Returns a JSON object in the following format:
    {
      "questions": [
         { "question": "<first question>", "answer": "<answer to first question>" },
         { "question": "<second question>", "answer": "<answer to second question>" },
         { "question": "<third question>", "answer": "<answer to third question>" },
         { "question": "<fourth question>", "answer": "<answer to fourth question>" }
      ]
    }
    """
    logger.info("Received request to generate questions from MIMIC data or generated history.")
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)
    
    mimic_data = data.get("mimic_data")
    # First, try to use generated history if provided.
    if mimic_data is None and "history" in data:
        mimic_data = data["history"]
        logger.info("Using generated history from payload as fallback since mimic_data was not provided.")
    
    # If still not provided, attempt to load from a saved file using subject_id.
    if mimic_data is None:
        subject_id = data.get("subject_id")
        if subject_id is None:
            logger.error("No mimic_data or history provided and no subject_id available in request.")
            return JsonResponse({'error': 'Missing mimic_data or history parameter and subject_id.'}, status=400)
        mimic_data_file = os.path.join(MIMIC_DATA_BASE, f"mimic_data_{subject_id}.json")
        if not os.path.exists(mimic_data_file):
            logger.error("MIMIC data file does not exist for subject_id %s.", subject_id)
            return JsonResponse({'error': 'No saved MIMIC data available.'}, status=400)
        else:
            try:
                with open(mimic_data_file, "r") as f:
                    file_contents = f.read().strip()
                    logger.debug("Raw MIMIC data file contents: %s", file_contents)
                    if not file_contents:
                        raise ValueError("MIMIC data file is empty.")
                    mimic_data = json.loads(file_contents)
                logger.info("Loaded raw MIMIC data from saved file.")
            except Exception as e:
                logger.error("Failed to load saved MIMIC data: %s", e)
                return JsonResponse({'error': f'Failed to load saved MIMIC data: {str(e)}'}, status=400)
    
    # Determine if we have full raw MIMIC data or just generated history details.
    if isinstance(mimic_data, dict) and "patient" in mimic_data:
        # Build a detailed prompt using all raw MIMIC-III fields.
        prompt = f"""
You are provided with detailed raw MIMIC-III patient data. Use all the details below to generate 4 clinically relevant questions and their concise answers.
Do not include any extra explanation or commentary—return ONLY valid JSON in the following format:

{{
  "questions": [
    {{
      "question": "<first question>",
      "answer": "<answer to first question>"
    }},
    {{
      "question": "<second question>",
      "answer": "<answer to second question>"
    }},
    {{
      "question": "<third question>",
      "answer": "<answer to third question>"
    }},
    {{
      "question": "<fourth question>",
      "answer": "<answer to fourth question>"
    }}
  ]
}}

Patient Info (PATIENTS): {mimic_data.get("patient", "")}
Admissions (ADMISSIONS): {mimic_data.get("admissions", "")}
Diagnoses (DIAGNOSES_ICD + D_ICD_DIAGNOSES): {mimic_data.get("diagnoses", "")}
Procedures (PROCEDURES_ICD + D_ICD_PROCEDURES): {mimic_data.get("procedures", "")}
ICU Stays (ICUSTAYS): {mimic_data.get("icu_stays", "")}
Transfers (TRANSFERS): {mimic_data.get("transfers", "")}
Services (SERVICES): {mimic_data.get("services", "")}
Lab Tests (LABEVENTS + D_LABITEMS): {mimic_data.get("lab_tests", "")}
Prescriptions (PRESCRIPTIONS): {mimic_data.get("prescriptions", "")}
Microbiology (MICROBIOLOGYEVENTS): {mimic_data.get("microbiology", "")}
Clinical Notes (NOTEEVENTS): {mimic_data.get("notes", "")}
"""
    else:
        # Fallback prompt using generated history details.
        fallback_details = json.dumps(mimic_data) if isinstance(mimic_data, dict) else mimic_data
        prompt = f"""
You are provided with a patient history with the following fields (PC, HPC, PMHx, DHx, FHx, SHx, SR).
Use these details to generate 4 clinically relevant questions and their concise answers.
Do not include any extra explanation or commentary—return ONLY valid JSON in the following format:

{{
  "questions": [
    {{
      "question": "<first question>",
      "answer": "<answer to first question>"
    }},
    {{
      "question": "<second question>",
      "answer": "<answer to second question>"
    }},
    {{
      "question": "<third question>",
      "answer": "<answer to third question>"
    }},
    {{
      "question": "<fourth question>",
      "answer": "<answer to fourth question>"
    }}
  ]
}}

Here is the patient history:
{fallback_details}
"""
    logger.debug("Constructed prompt for generate_questions: %s", prompt)

    try:
        openai.api_key = os.getenv("OPENAI_API_KEY")
        logger.info("Sending prompt to OpenAI for generate_questions...")
        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "You are a medical assistant that generates relevant clinical questions and answers based on detailed patient data. Output ONLY valid JSON."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.7,
            max_tokens=500,
        )
        logger.info("Received response from OpenAI for generate_questions.")
    except Exception as e:
        logger.error("Error during OpenAI request for generate_questions: %s", e)
        return JsonResponse({'error': str(e)}, status=500)
    
    ai_message = response.choices[0].message['content']
    logger.debug("Raw AI message for generate_questions: %s", ai_message)
    
    try:
        result_json = json.loads(ai_message)
    except json.JSONDecodeError as e:
        logger.error("Failed to parse AI response as JSON in generate_questions: %s", e)
        json_match = re.search(r"\{.*\}", ai_message, re.DOTALL)
        if json_match:
            try:
                result_json = json.loads(json_match.group(0))
                logger.info("Extracted JSON via regex fallback in generate_questions.")
            except json.JSONDecodeError as e2:
                logger.error("Fallback JSON extraction failed in generate_questions: %s", e2)
                return JsonResponse({'error': 'Failed to parse AI response as JSON.'}, status=500)
        else:
            return JsonResponse({'error': 'Failed to parse AI response as JSON.'}, status=500)
    
    logger.info("Returning result from generate_questions: %s", result_json)
    return JsonResponse(result_json)

@csrf_exempt
def get_conditions(request):
    logger.info("Received request to fetch condition types.")
    try:
        client = bigquery.Client()
        logger.info("BigQuery client initialized for get_conditions.")

        search_query = request.GET.get("search", "").strip()
        # Updated query joining the two tables:
        query = """
            SELECT DISTINCT d.long_title
            FROM `fyp-project-451413.mimic_iii_local.DIAGNOSES_ICD` AS i
            JOIN `fyp-project-451413.mimic_iii_local.D_ICD_DIAGNOSES` AS d
              ON i.ICD9_CODE = d.icd9_code
            WHERE LOWER(d.long_title) LIKE LOWER(@search)
            ORDER BY d.long_title
            LIMIT 10000;
        """
        job_config = bigquery.QueryJobConfig(
            query_parameters=[
                bigquery.ScalarQueryParameter("search", "STRING", f"%{search_query}%")
            ]
        )
        query_job = client.query(query, job_config=job_config)
        results = query_job.result()
        # Use lowercase field name
        conditions = [row.long_title for row in results]
        logger.info("Fetched conditions from BigQuery.")
        return JsonResponse({"conditions": conditions}, status=200)
    except Exception as e:
        logger.exception("Error fetching conditions: %s", e)
        return JsonResponse({"error": f"Failed to fetch conditions: {str(e)}"}, status=500)

@csrf_exempt
def get_history_categories(request):
    logger.info("Received request to fetch history categories.")
    try:
        client = bigquery.Client()
        logger.info("BigQuery client initialized for get_history_categories.")

        query = """
            SELECT DISTINCT SUBSTR(icd9_code, 1, 3) AS category_prefix
            FROM `fyp-project-451413.mimic_iii_local.DIAGNOSES_ICD`            ORDER BY category_prefix
            LIMIT 50;
        """
        query_job = client.query(query)
        results = query_job.result()
        categories = [row.category_prefix for row in results]
        logger.info("Fetched history categories from BigQuery.")
        return JsonResponse({"categories": categories}, status=200)
    except Exception as e:
        logger.exception("Error fetching history categories: %s", e)
        return JsonResponse({"error": f"Failed to fetch categories: {str(e)}"}, status=500)

@csrf_exempt
def ask_question(request):
    logger.info("Received request to ask a question.")
    if request.method == "POST":
        try:
            data = json.loads(request.body)
            question = data.get("question")
            history = data.get("history")

            logger.info(f"Received question: {question}")
            logger.info(f"Received history: {history}")

            if not question or not history:
                logger.warning("Missing 'question' or 'history' in the request.")
                return JsonResponse({"error": "Both question and history are required"}, status=400)

            prompt = f"""
Based on the following patient history, please answer the user's question.
Do not provide any additional details, recommendations, or case analysis beyond what is explicitly asked.

Patient History:
{history}

User's Question:
{question}
"""
            logger.info("Sending prompt to OpenAI for ask_question...")
            response = openai.ChatCompletion.create(
                model="gpt-3.5-turbo",
                messages=[
                    {"role": "system", "content": "You are a medical assistant. Answer only the question asked using the provided patient history, and do not provide any extra details or recommendations."},
                    {"role": "user", "content": prompt}
                ],
                max_tokens=600,
                temperature=0.7
            )
            answer = response["choices"][0]["message"]["content"].strip()
            logger.info(f"ChatGPT response (ask_question): {answer}")

            return JsonResponse({"answer": answer}, status=200)
        except Exception as e:
            logger.exception("An error occurred while querying ChatGPT for ask_question: %s", e)
            return JsonResponse({"error": f"ChatGPT query failed: {e}"}, status=500)
    logger.warning("Invalid request method for ask_question.")
    return JsonResponse({"error": "Invalid request method"}, status=400)




def example_endpoint(request):
    return JsonResponse({'message': 'Hello from the new API!'})
@csrf_exempt
def get_general_condition_categories(request):
    logger.info("Received request to fetch general condition categories.")
    try:
        client = bigquery.Client()
        logger.info("BigQuery client initialized for get_general_condition_categories.")

        # This query groups ICD-9 codes into general disease categories.
        # Note: Adjust the ranges below based on your specific mapping.
        query = """
        SELECT
        CASE
            WHEN icd9_code LIKE 'V%' THEN 'Supplementary Conditions'
            WHEN icd9_code LIKE 'E%' THEN 'External Causes'
            WHEN SAFE_CAST(SUBSTR(icd9_code, 1, 2) AS INT64) BETWEEN 1 AND 19 THEN 'Infectious & Parasitic Diseases'
            WHEN SAFE_CAST(SUBSTR(icd9_code, 1, 2) AS INT64) BETWEEN 20 AND 39 THEN 'Neoplasms'
            WHEN SAFE_CAST(SUBSTR(icd9_code, 1, 2) AS INT64) BETWEEN 40 AND 49 THEN 'Endocrine & Metabolic'
            WHEN SAFE_CAST(SUBSTR(icd9_code, 1, 2) AS INT64) BETWEEN 50 AND 59 THEN 'Blood Disorders'
            WHEN SAFE_CAST(SUBSTR(icd9_code, 1, 2) AS INT64) BETWEEN 60 AND 69 THEN 'Mental Disorders'
            WHEN SAFE_CAST(SUBSTR(icd9_code, 1, 2) AS INT64) BETWEEN 70 AND 79 THEN 'Nervous System'
            WHEN SAFE_CAST(SUBSTR(icd9_code, 1, 2) AS INT64) BETWEEN 80 AND 89 THEN 'Sense Organs'
            WHEN SAFE_CAST(SUBSTR(icd9_code, 1, 2) AS INT64) BETWEEN 90 AND 99 THEN 'Circulatory System'
            WHEN SAFE_CAST(SUBSTR(icd9_code, 1, 2) AS INT64) BETWEEN 100 AND 109 THEN 'Respiratory System'
            WHEN SAFE_CAST(SUBSTR(icd9_code, 1, 2) AS INT64) BETWEEN 110 AND 119 THEN 'Digestive System'
            WHEN SAFE_CAST(SUBSTR(icd9_code, 1, 2) AS INT64) BETWEEN 120 AND 129 THEN 'Genitourinary System'
            WHEN SAFE_CAST(SUBSTR(icd9_code, 1, 2) AS INT64) BETWEEN 130 AND 139 THEN 'Pregnancy/Childbirth'
            WHEN SAFE_CAST(SUBSTR(icd9_code, 1, 2) AS INT64) BETWEEN 140 AND 149 THEN 'Skin Disorders'
            WHEN SAFE_CAST(SUBSTR(icd9_code, 1, 2) AS INT64) BETWEEN 150 AND 159 THEN 'Musculoskeletal'
            ELSE 'Other'
        END AS disease_category,
        COUNT(*) AS count
        FROM `fyp-project-451413.mimic_iii_local.DIAGNOSES_ICD`
        GROUP BY disease_category
        ORDER BY disease_category
        LIMIT 50;
        """
        query_job = client.query(query)
        results = query_job.result()
        categories = [row.disease_category for row in results]
        logger.info("Fetched general condition categories from BigQuery.")
        return JsonResponse({"categories": categories}, status=200)
    except Exception as e:
        logger.exception("Error fetching general condition categories: %s", e)
        return JsonResponse({"error": f"Failed to fetch categories: {str(e)}"}, status=500)


@csrf_exempt
def get_conditions_by_category(request):
    logger.info("Received request to fetch conditions by category.")
    try:
        client = bigquery.Client()
        logger.info("BigQuery client initialized for get_conditions_by_category.")
        
        category = request.GET.get("category", "").strip()
        if not category:
            return JsonResponse({"error": "Category parameter is required."}, status=400)
        
        query = """
            SELECT DISTINCT d.LONG_TITLE AS long_title
            FROM `fyp-project-451413.mimic_iii_local.DIAGNOSES_ICD` AS i
            JOIN `fyp-project-451413.mimic_iii_local.D_ICD_DIAGNOSES` AS d
              ON i.ICD9_CODE = d.icd9_code
            WHERE
              CASE
                WHEN i.icd9_code LIKE 'V%' THEN 'Supplementary Conditions'
                WHEN i.icd9_code LIKE 'E%' THEN 'External Causes'
                WHEN SAFE_CAST(SUBSTR(i.icd9_code, 1, 2) AS INT64) BETWEEN 1 AND 19 THEN 'Infectious & Parasitic Diseases'
                WHEN SAFE_CAST(SUBSTR(i.icd9_code, 1, 2) AS INT64) BETWEEN 20 AND 39 THEN 'Neoplasms'
                WHEN SAFE_CAST(SUBSTR(i.icd9_code, 1, 2) AS INT64) BETWEEN 40 AND 49 THEN 'Endocrine & Metabolic'
                WHEN SAFE_CAST(SUBSTR(i.icd9_code, 1, 2) AS INT64) BETWEEN 50 AND 59 THEN 'Blood Disorders'
                WHEN SAFE_CAST(SUBSTR(i.icd9_code, 1, 2) AS INT64) BETWEEN 60 AND 69 THEN 'Mental Disorders'
                WHEN SAFE_CAST(SUBSTR(i.icd9_code, 1, 2) AS INT64) BETWEEN 70 AND 79 THEN 'Nervous System'
                WHEN SAFE_CAST(SUBSTR(i.icd9_code, 1, 2) AS INT64) BETWEEN 80 AND 89 THEN 'Sense Organs'
                WHEN SAFE_CAST(SUBSTR(i.icd9_code, 1, 2) AS INT64) BETWEEN 90 AND 99 THEN 'Circulatory System'
                WHEN SAFE_CAST(SUBSTR(i.icd9_code, 1, 2) AS INT64) BETWEEN 100 AND 109 THEN 'Respiratory System'
                WHEN SAFE_CAST(SUBSTR(i.icd9_code, 1, 2) AS INT64) BETWEEN 110 AND 119 THEN 'Digestive System'
                WHEN SAFE_CAST(SUBSTR(i.icd9_code, 1, 2) AS INT64) BETWEEN 120 AND 129 THEN 'Genitourinary System'
                WHEN SAFE_CAST(SUBSTR(i.icd9_code, 1, 2) AS INT64) BETWEEN 130 AND 139 THEN 'Pregnancy/Childbirth'
                WHEN SAFE_CAST(SUBSTR(i.icd9_code, 1, 2) AS INT64) BETWEEN 140 AND 149 THEN 'Skin Disorders'
                WHEN SAFE_CAST(SUBSTR(i.icd9_code, 1, 2) AS INT64) BETWEEN 150 AND 159 THEN 'Musculoskeletal'
                ELSE 'Other'
              END = @category
            ORDER BY d.LONG_TITLE
            LIMIT 100;
        """
        job_config = bigquery.QueryJobConfig(
            query_parameters=[
                bigquery.ScalarQueryParameter("category", "STRING", category)
            ]
        )
        query_job = client.query(query, job_config=job_config)
        results = query_job.result()
        conditions = [row.long_title for row in results]
        logger.info("Fetched conditions for category '%s' from BigQuery.", category)
        return JsonResponse({"conditions": conditions}, status=200)
    except Exception as e:
        logger.exception("Error fetching conditions by category: %s", e)
        return JsonResponse({"error": f"Failed to fetch conditions: {str(e)}"}, status=500)
    

# ✅ Fetch conditions based on selected category
@csrf_exempt
def get_conditions_by_category_profile(request):
    """
    Fetches all conditions under a specific category from `text2dt_mimic_mapping_english-full-profile.json`,
    returning only the English `mimic_condition` names.
    """
    logger.info("Received request to fetch conditions by category (profile version).")
    
    category = request.GET.get("category", "").strip()
    if not category:
        return JsonResponse({"error": "Category parameter is required."}, status=400)
    
    text2dt_mapping = load_text2dt_mapping()
    if text2dt_mapping is None:
        return JsonResponse({"error": "Mapping file not found or could not be loaded."}, status=500)
    
    # Filter and deduplicate conditions based on category
    conditions = list(set(
        entry["mapped_mimic_group"]["mimic_condition"]
        for entry in text2dt_mapping
        if entry.get("category") == category and "mapped_mimic_group" in entry
    ))

    if not conditions:
        return JsonResponse({"error": f"No conditions found for category '{category}'"}, status=404)

    return JsonResponse({"conditions": sorted(conditions)}, status=200)

@csrf_exempt
def get_category_by_condition_profile(request):
    """
    Fetches the category for a given condition from `text2dt_mimic_mapping_english-full-profile.json`.
    Expects a query parameter "condition" representing the mimic condition.
    Returns a JSON object with the category.
    """
    logger.info("Received request to fetch category by condition (profile version).")
    
    condition = request.GET.get("condition", "").strip()
    if not condition:
        return JsonResponse({"error": "Condition parameter is required."}, status=400)
    
    text2dt_mapping = load_text2dt_mapping()
    if text2dt_mapping is None:
        return JsonResponse({"error": "Mapping file not found or could not be loaded."}, status=500)
    
    # Find the first entry that matches the given condition.
    matched_entry = next(
        (entry for entry in text2dt_mapping 
         if condition in entry.get("mapped_mimic_group", {}).get("icd9_codes", [])),
        None
    )
    
    if not matched_entry:
        return JsonResponse({"error": f"No category found for condition '{condition}'"}, status=404)
    
    category = matched_entry.get("category", "Unknown")
    return JsonResponse({"category": category}, status=200)

logger = logging.getLogger(__name__)

# Function to load the MIMIC mapping JSON
def load_text2dt_mapping():
    mapping_file = "text2dt_mimic_mapping_english-full-profile.json"
    if not os.path.exists(mapping_file):
        logger.error(f"Mapping file {mapping_file} not found.")
        return None
    try:
        with open(mapping_file, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"Error reading mapping file: {e}")
        return None

def convert_mimic_to_icd_internal(condition):
    """
    Helper to translate an English mimic condition name into its ICD‑9 code using the mapping file.
    Returns the ICD code if found; otherwise, returns None.
    """
    mapping_data = load_text2dt_mapping()
    if mapping_data is None:
        logger.error("Mapping file not found in convert_mimic_to_icd_internal.")
        return None
    matched_entry = next(
        (entry for entry in mapping_data 
         if entry.get("mapped_mimic_group", {}).get("mimic_condition") == condition),
        None
    )
    if not matched_entry:
        logger.warning(f"Condition '{condition}' not found via internal conversion.")
        return None
    icd_codes = matched_entry.get("mapped_mimic_group", {}).get("icd9_codes", [])
    if not icd_codes:
        logger.warning(f"No ICD code found for condition '{condition}' via internal conversion.")
        return None
    return icd_codes[0]

def convert_condition_by_bigquery(condition):
    """
    Given a mimic condition name, query the BigQuery MIMIC database (D_ICD_DIAGNOSES)
    to obtain the corresponding ICD‑9 code.
    Returns the ICD‑9 code if found; otherwise, returns None.
    """
    try:
        client = bigquery.Client()
        query = """
            SELECT icd9_code
            FROM `fyp-project-451413.mimic_iii_local.D_ICD_DIAGNOSES`
            WHERE LOWER(long_title) = LOWER(@cond)
            LIMIT 1
        """
        job_config = bigquery.QueryJobConfig(
            query_parameters=[bigquery.ScalarQueryParameter("cond", "STRING", condition)]
        )
        query_job = client.query(query, job_config=job_config)
        results = query_job.result()
        for row in results:
            logger.info(f"BigQuery conversion: Found ICD code {row.icd9_code} for condition '{condition}'")
            return row.icd9_code
        logger.warning(f"BigQuery conversion: No ICD code found for condition '{condition}'")
        return None
    except Exception as e:
        logger.error("Error converting condition via BigQuery: %s", e)
        return None


def get_category_from_icd(client, icd_code: str) -> str:
    try:
        icd_code_clean = icd_code.replace(".", "").lstrip("0")
        logger.info(f"Looking up category for ICD: {icd_code} → normalized to {icd_code_clean}")

        query = """
        SELECT
        CASE
            WHEN icd9_code LIKE 'V%' THEN 'Supplementary Conditions'
            WHEN icd9_code LIKE 'E%' THEN 'External Causes'
            WHEN SAFE_CAST(SUBSTR(icd9_code, 1, 3) AS INT64) BETWEEN 1 AND 139 THEN 'Infectious & Parasitic Diseases'
            WHEN SAFE_CAST(SUBSTR(icd9_code, 1, 3) AS INT64) BETWEEN 140 AND 239 THEN 'Neoplasms'
            WHEN SAFE_CAST(SUBSTR(icd9_code, 1, 3) AS INT64) BETWEEN 240 AND 279 THEN 'Endocrine & Metabolic'
            WHEN SAFE_CAST(SUBSTR(icd9_code, 1, 3) AS INT64) BETWEEN 280 AND 289 THEN 'Blood Disorders'
            WHEN SAFE_CAST(SUBSTR(icd9_code, 1, 3) AS INT64) BETWEEN 290 AND 319 THEN 'Mental Disorders'
            WHEN SAFE_CAST(SUBSTR(icd9_code, 1, 3) AS INT64) BETWEEN 320 AND 389 THEN 'Nervous System'
            WHEN SAFE_CAST(SUBSTR(icd9_code, 1, 3) AS INT64) BETWEEN 390 AND 459 THEN 'Circulatory System'
            WHEN SAFE_CAST(SUBSTR(icd9_code, 1, 3) AS INT64) BETWEEN 460 AND 519 THEN 'Respiratory System'
            WHEN SAFE_CAST(SUBSTR(icd9_code, 1, 3) AS INT64) BETWEEN 520 AND 579 THEN 'Digestive System'
            WHEN SAFE_CAST(SUBSTR(icd9_code, 1, 3) AS INT64) BETWEEN 580 AND 629 THEN 'Genitourinary System'
            WHEN SAFE_CAST(SUBSTR(icd9_code, 1, 3) AS INT64) BETWEEN 630 AND 679 THEN 'Pregnancy/Childbirth'
            WHEN SAFE_CAST(SUBSTR(icd9_code, 1, 3) AS INT64) BETWEEN 680 AND 709 THEN 'Skin Disorders'
            WHEN SAFE_CAST(SUBSTR(icd9_code, 1, 3) AS INT64) BETWEEN 710 AND 739 THEN 'Musculoskeletal'
            WHEN SAFE_CAST(SUBSTR(icd9_code, 1, 3) AS INT64) BETWEEN 740 AND 759 THEN 'Congenital Anomalies'
            WHEN SAFE_CAST(SUBSTR(icd9_code, 1, 3) AS INT64) BETWEEN 760 AND 779 THEN 'Perinatal Conditions'
            WHEN SAFE_CAST(SUBSTR(icd9_code, 1, 3) AS INT64) BETWEEN 780 AND 799 THEN 'Symptoms & Ill-defined Conditions'
            WHEN SAFE_CAST(SUBSTR(icd9_code, 1, 3) AS INT64) BETWEEN 800 AND 999 THEN 'Injury & Poisoning'
            ELSE 'Other'
        END AS disease_category
        FROM `fyp-project-451413.mimic_iii_local.DIAGNOSES_ICD`
        WHERE REPLACE(icd9_code, ".", "") = @icd_code
        LIMIT 1
        """

        job_config = bigquery.QueryJobConfig(
            query_parameters=[
                bigquery.ScalarQueryParameter("icd_code", "STRING", icd_code_clean)
            ]
        )

        results = client.query(query, job_config=job_config).result()
        row = next(results, None)
        if row:
            return row.disease_category
    except Exception as e:
        logger.warning(f"BigQuery category lookup failed: {e}")
    return "Other"
