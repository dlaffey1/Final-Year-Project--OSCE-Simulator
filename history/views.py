import json
import os
import re  # Ensure this import is present!
import openai
import logging
from google.cloud import bigquery  # Import BigQuery client

from django.http import JsonResponse
from django.shortcuts import render
from django.views.decorators.csrf import csrf_exempt

# If you have updated your fetch_patient_data to work with BigQuery, import it.
from AIHistory import fetch_patient_data  # Assume this now works with BigQuery

# Set up logging
logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.DEBUG)

@csrf_exempt
def generate_history(request):
    logger.info("Received request to generate history.")
    if request.method == "GET":
        logger.info("GET request received - rendering form.")
        return render(request, "history/index.html")

    if request.method == "POST":
        logger.info("POST request received - processing data.")
        try:
            # Initialize BigQuery client instead of a local Postgres connection.
            client = bigquery.Client()
            logger.info("BigQuery client initialized successfully.")
        except Exception as e:
            logger.error("Failed to initialize BigQuery client: %s", e)
            return JsonResponse({"error": "BigQuery connection failed"}, status=500)

        try:
            logger.info("Fetching patient data from BigQuery...")
            # Call your updated fetch_patient_data function, passing the BigQuery client.
            patient, diagnoses, events, notes, lab_tests, prescriptions = fetch_patient_data(client)

            if patient:
                logger.info(f"Patient data found: {patient}")
                logger.info("Generating patient history using ChatGPT (JSON format)...")

                prompt = f"""
You are provided with the following patient data:
Patient Info: {patient}
Diagnoses: {diagnoses}
Events: {events}
Notes: {notes}
Lab tests: {lab_tests}
Prescriptions: {prescriptions}

Please generate a structured patient history under these headings:
1) Presenting complaint (PC)
2) History of presenting complaint (HPC)
3) Past medical history (PMHx)
4) Drug history (DHx)
5) Family history (FHx)
6) Social history (SHx)
7) Systems review (SR)

Return the entire result as valid JSON with each heading as a field, like:
{{
  "PC": "...",
  "HPC": "...",
  "PMHx": "...",
  "DHx": "...",
  "FHx": "...",
  "SHx": "...",
  "SR": "..."
}}

Make sure the JSON is valid and includes each heading, even if empty.
"""
                logger.debug("Constructed prompt for generate_history: %s", prompt)

                gpt_response = openai.ChatCompletion.create(
                    model="gpt-3.5-turbo",
                    messages=[
                        {"role": "system", "content": "You are a medical assistant providing structured patient histories."},
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
                return JsonResponse({"history": history_data}, status=200)
            else:
                logger.warning("No patient data found in BigQuery.")
                return JsonResponse({"error": "No patient data found"}, status=404)
        except Exception as e:
            logger.exception("An error occurred while processing the request: %s", e)
            return JsonResponse({"error": f"An unexpected error occurred: {str(e)}"}, status=500)
    logger.warning("Invalid request method.")
    return JsonResponse({"error": "Invalid request method"}, status=400)

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


@csrf_exempt
def generate_questions(request):
    """
    New route that takes a patient history as input and returns 4 related questions along with their answers.
    Expects a JSON payload with the key:
      - history: The patient's history (a structured string or JSON).
    Returns a JSON object with the following format:
    {
      "questions": [
         { "question": "<first question>", "answer": "<answer to first question>" },
         { "question": "<second question>", "answer": "<answer to second question>" },
         { "question": "<third question>", "answer": "<answer to third question>" },
         { "question": "<fourth question>", "answer": "<answer to fourth question>" }
      ]
    }
    """
    logger.info("Received request to generate questions from history.")
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)
    
    history = data.get("history")
    if history is None:
        return JsonResponse({'error': 'Missing history parameter.'}, status=400)
    
    prompt = f"""
You are provided with the following patient history:
{history}

Generate 4 questions that are related to this patient history.
For each question, also provide a concise answer.
Return ONLY a JSON object exactly in this format (do not include any additional text or explanation):

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

Ensure the JSON is valid.
"""
    logger.debug("Constructed prompt for generate_questions: %s", prompt)

    openai.api_key = os.getenv("OPENAI_API_KEY")
    
    try:
        logger.info("Sending prompt to OpenAI for generate_questions...")
        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "You are a medical assistant that generates relevant questions and answers based on patient history. Output ONLY valid JSON."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.7,
            max_tokens=300,
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


def example_endpoint(request):
    return JsonResponse({'message': 'Hello from the new API!'})
