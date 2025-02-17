import logging
import json
import openai

from django.http import JsonResponse
from django.shortcuts import render
from django.views.decorators.csrf import csrf_exempt
import os
from AIHistory import fetch_patient_data, connect_to_db  # Keep fetch_patient_data & connect_to_db
# Removed `generate_patient_history_with_gpt` import since we do the GPT logic inline now.

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
        connection = connect_to_db({
            "dbname": "mimiciii",
            "user": "postgres",
            "password": "123",
            "host": "localhost",
            "port": 5432,
        })

        if not connection:
            logger.error("Failed to connect to the database.")
            return JsonResponse({"error": "Database connection failed"}, status=500)

        try:
            logger.info("Fetching patient data...")
            patient, diagnoses, events, notes, lab_tests, prescriptions = fetch_patient_data(connection)

            if patient:
                logger.info(f"Patient data found: {patient}")
                logger.info("Generating patient history using ChatGPT (JSON format)...")

                # -------------------------------
                # Inline ChatGPT call for JSON
                # -------------------------------
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

                # Call OpenAI
                gpt_response = openai.ChatCompletion.create(
                    model="gpt-3.5-turbo",
                    messages=[
                        {
                            "role": "system",
                            "content": "You are a medical assistant providing structured patient histories."
                        },
                        {
                            "role": "user",
                            "content": prompt
                        }
                    ],
                    max_tokens=800,
                    temperature=0.7,
                )

                # Grab the returned text
                history_json_str = gpt_response["choices"][0]["message"]["content"].strip()
                logger.info(f"ChatGPT raw response: {history_json_str}")

                # Try parsing the JSON
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
                logger.warning("No patient data found in the database.")
                return JsonResponse({"error": "No patient data found"}, status=404)

        except Exception as e:
            logger.exception("An error occurred while processing the request.")
            return JsonResponse({"error": f"An unexpected error occurred: {str(e)}"}, status=500)

        finally:
            logger.info("Closing the database connection.")
            connection.close()

    logger.warning("Invalid request method.")
    return JsonResponse({"error": "Invalid request method"}, status=400)
@csrf_exempt
def get_conditions(request):
    logger.info("Received request to fetch condition types.")

    try:
        connection = connect_to_db({
            "dbname": "mimiciii",
            "user": "postgres",
            "password": "123",
            "host": "localhost",
            "port": 5432,
        })

        if not connection:
            logger.error("Database connection failed.")
            return JsonResponse({"error": "Database connection failed"}, status=500)

        cursor = connection.cursor()
        search_query = request.GET.get("search", "").strip()

        # Fetch only 100 results, filtering by search input
        cursor.execute("""
            SELECT DISTINCT d_icd_diagnoses.long_title
            FROM mimiciii.diagnoses_icd
            JOIN mimiciii.d_icd_diagnoses
            ON diagnoses_icd.icd9_code = d_icd_diagnoses.icd9_code
            WHERE d_icd_diagnoses.long_title ILIKE %s
            ORDER BY d_icd_diagnoses.long_title
            LIMIT 10000;
        """, (f"%{search_query}%",))

        conditions = [row[0] for row in cursor.fetchall()]
        cursor.close()
        connection.close()

        return JsonResponse({"conditions": conditions}, status=200)

    except Exception as e:
        logger.exception("Error fetching conditions.")
        return JsonResponse({"error": f"Failed to fetch conditions: {str(e)}"}, status=500)
@csrf_exempt
def get_history_categories(request):
    """
    Fetches distinct condition categories from MIMIC-III (e.g., Cardiovascular, Neurological).
    """
    logger.info("Received request to fetch history categories.")

    try:
        connection = connect_to_db({
            "dbname": "mimiciii",
            "user": "postgres",
            "password": "123",
            "host": "localhost",
            "port": 5432,
        })

        if not connection:
            logger.error("Database connection failed.")
            return JsonResponse({"error": "Database connection failed"}, status=500)

        cursor = connection.cursor()

        # Fetch distinct categories (assuming categories exist in the `d_icd_diagnoses` table)
        cursor.execute("""
            SELECT DISTINCT LEFT(d_icd_diagnoses.icd9_code, 3) AS category_prefix
            FROM mimiciii.d_icd_diagnoses
            ORDER BY category_prefix
            LIMIT 50;
        """)



        categories = [row[0] for row in cursor.fetchall()]
        cursor.close()
        connection.close()

        return JsonResponse({"categories": categories}, status=200)

    except Exception as e:
        logger.exception("Error fetching history categories.")
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

            # Ensure both question and history are provided
            if not question or not history:
                logger.warning("Missing 'question' or 'history' in the request.")
                return JsonResponse({"error": "Both question and history are required"}, status=400)

            # Updated prompt: Only answer the specific question using the provided history.
            prompt = f"""
Based on the following patient history, please answer the user's question.
Do not provide any additional details, recommendations, or case analysis beyond what is explicitly asked.

Patient History:
{history}

User's Question:
{question}
"""

            logger.info("Sending prompt to ChatGPT...")
            response = openai.ChatCompletion.create(
                model="gpt-3.5-turbo",
                messages=[
                    {
                        "role": "system",
                        "content": "You are a medical assistant. Answer only the question asked using the provided patient history, and do not provide any extra details or recommendations."
                    },
                    {
                        "role": "user",
                        "content": prompt
                    }
                ],
                max_tokens=600,
                temperature=0.7
            )
            answer = response["choices"][0]["message"]["content"].strip()
            logger.info(f"ChatGPT response: {answer}")

            return JsonResponse({"answer": answer}, status=200)

        except Exception as e:
            logger.exception("An error occurred while querying ChatGPT.")
            return JsonResponse({"error": f"ChatGPT query failed: {e}"}, status=500)

    logger.warning("Invalid request method.")
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
         { "question": "...", "answer": "..." },
         { "question": "...", "answer": "..." },
         { "question": "...", "answer": "..." },
         { "question": "...", "answer": "..." }
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
    
    # Construct prompt instructing ChatGPT to generate 4 related questions and answers.
    prompt = f"""
You are provided with the following patient history:
{history}

Generate 4 questions that are related to this patient history.
For each question, also provide a concise answer.
Return the result as a JSON object exactly in this format:
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
Make sure the JSON is valid.
"""
    openai.api_key = os.getenv("OPENAI_API_KEY")
    try:
        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "You are a medical assistant that generates relevant questions and answers based on patient history."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.7,
            max_tokens=300,
        )
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)
    
    ai_message = response.choices[0].message['content']
    try:
        result_json = json.loads(ai_message)
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Failed to parse AI response as JSON.'}, status=500)
    
    return JsonResponse(result_json)