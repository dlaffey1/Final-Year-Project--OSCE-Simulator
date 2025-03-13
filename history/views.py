import json
import os
import re  # Ensure this import is present!
import openai
import logging
from google.cloud import bigquery  # Import BigQuery client

from django.http import JsonResponse
from django.shortcuts import render
from django.views.decorators.csrf import csrf_exempt

# Import your fetch_patient_data (which now works with BigQuery)
from AIHistory import fetch_patient_data  # Assume this now works with BigQuery

# Set up logging
logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.DEBUG)

# Define a base path for saving raw MIMIC data.
# (In production, you might use session storage or a caching system.)
MIMIC_DATA_BASE = "/tmp"

@csrf_exempt
def generate_history(request):
    logger.info("Received request to generate history.")
    if request.method == "GET":
        logger.info("GET request received - rendering form.")
        return render(request, "history/index.html")

    if request.method == "POST":
        logger.info("POST request received - processing data.")
        try:
            # Initialize BigQuery client.
            client = bigquery.Client()
            logger.info("BigQuery client initialized successfully.")
        except Exception as e:
            logger.error("Failed to initialize BigQuery client: %s", e)
            return JsonResponse({"error": "BigQuery connection failed"}, status=500)

        try:
            logger.info("Fetching patient data from BigQuery...")
            # Adjust subject_id retrieval as needed:
            subject_id = request.POST.get("subject_id", 12345)

            # Call your updated fetch_patient_data function.
            (patient,
             diagnoses,
             admissions,
             notes,
             lab_tests,
             prescriptions,
             icu_stays,
             transfers,
             procedures,
             services,
             microbiology) = fetch_patient_data(client, subject_id=subject_id)

            if patient:
                logger.info(f"Patient data found: {patient}")
                # Build a file name specific to this subject.
                mimic_data_file = os.path.join(MIMIC_DATA_BASE, f"mimic_data_{subject_id}.json")
                # Save the raw MIMIC data so that generate_questions can later use it.
                raw_mimic_data = {
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
                }
                try:
                    with open(mimic_data_file, "w") as f:
                        json.dump(raw_mimic_data, f)
                        f.flush()            # Flush the internal buffer to disk
                        os.fsync(f.fileno()) # Force write to disk
                    logger.info(f"Saved raw MIMIC data to file: {mimic_data_file}")
                except Exception as e:
                    logger.error("Failed to save raw MIMIC data: %s", e)

                logger.info("Generating patient history using ChatGPT (JSON format)...")
                # Build a detailed prompt that instructs the model to incorporate all raw MIMIC fields.
                prompt = f"""
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
                logger.debug("Constructed prompt for generate_history: %s", prompt)

                gpt_response = openai.ChatCompletion.create(
                    model="gpt-3.5-turbo",
                    messages=[
                        {"role": "system", "content": "You are a medical assistant providing structured patient histories. Use all the provided raw MIMIC-III data to create a detailed and coherent summary."},
                        {"role": "user", "content": prompt}
                    ],
                    max_tokens=800,
                    temperature=0.7,
                )

                history_json_str = gpt_response["choices"][0]["message"]["content"].strip()
                logger.info(f"ChatGPT raw response (generate_history): {history_json_str}")

                try:
                    history_data = json.loads(history_json_str)
                except json.JSONDecodeError:
                    logger.warning("GPT returned invalid JSON; storing entire response in 'PC' only.")
                    history_data = {
                        "PC": history_json_str,
                        "HPC": "",
                        "PMHx": "",
                        "DHx": "",
                        "FHx": "",
                        "SHx": "",
                        "SR": ""
                    }

                logger.info(f"Final structured history: {history_data}")

                # Extract the right condition from diagnoses.
                # Assume diagnoses is a list of dictionaries with keys "icd_code" and "description".
                if diagnoses and isinstance(diagnoses, list) and len(diagnoses) > 0:
                    first_diag = diagnoses[0]
                    if first_diag.get("description"):
                        right_condition = first_diag["description"]
                    elif first_diag.get("icd_code"):
                        right_condition = first_diag["icd_code"]
                    else:
                        right_condition = "Unknown"
                else:
                    right_condition = "Unknown"

                logger.info(f"Extracted right condition: {right_condition}")

                return JsonResponse({"history": history_data, "right_condition": right_condition}, status=200)
            else:
                logger.warning("No patient data found in BigQuery.")
                return JsonResponse({"error": "No patient data found"}, status=404)

        except Exception as e:
            logger.exception("An error occurred while processing the request: %s", e)
            return JsonResponse({"error": f"An unexpected error occurred: {str(e)}"}, status=500)

    logger.warning("Invalid request method.")
    return JsonResponse({"error": "Invalid request method"}, status=400)

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
