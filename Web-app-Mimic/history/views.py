import logging
import json
import openai

from django.http import JsonResponse
from django.shortcuts import render
from django.views.decorators.csrf import csrf_exempt

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
