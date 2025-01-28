import logging
from django.http import JsonResponse
from django.shortcuts import render
from AIHistory import fetch_patient_data, generate_patient_history_with_gpt, connect_to_db
import openai
from django.views.decorators.csrf import csrf_exempt

# Set up logging
logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.DEBUG)

# View to generate patient history
@csrf_exempt
def generate_history(request):
    logger.info("Received request to generate history.")
    if request.method == "GET":  # Render the page with the form
        logger.info("GET request received - rendering form.")
        return render(request, "history/index.html")

    if request.method == "POST":  # Handle the form submission
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
            # Fetch patient data
            patient, diagnoses, events, notes, lab_tests, prescriptions = fetch_patient_data(connection)

            # Log the fetched data for debugging
            if patient:
                logger.info(f"Patient data found: {patient}")
                logger.info("Generating patient history using ChatGPT...")
                # Generate the patient history using ChatGPT
                history = generate_patient_history_with_gpt(patient, diagnoses, events, notes, lab_tests, prescriptions)
                logger.info(f"Generated history: {history}")
                return JsonResponse({"history": history}, status=200)
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


# View to ask questions about the patient history
@csrf_exempt
def ask_question(request):
    logger.info("Received request to ask a question.")
    if request.method == "POST":
        try:
            data = json.loads(request.body)  # Parse JSON body
            question = data.get("question")
            history = data.get("history")

            logger.info(f"Received question: {question}")
            logger.info(f"Received history: {history}")

            # Ensure both question and history are provided
            if not question or not history:
                logger.warning("Missing 'question' or 'history' in the request.")
                return JsonResponse({"error": "Both question and history are required"}, status=400)

            # Build the prompt with potential follow-up questions
            prompt = f"""
            Based on the following patient history, answer the user's question:

            Patient History:
            {history}

            User's Question:
            {question}

            Additionally, provide the following details where relevant:
            - The most likely underlying cause for the condition.
            - Possible signs of deterioration or complications.
            - Recommended management or treatment plan.
            - Essential steps before discharge or long-term care recommendations.
            """

            logger.info("Sending prompt to ChatGPT...")
            # Query ChatGPT with the generated prompt
            response = openai.ChatCompletion.create(
                model="gpt-3.5-turbo",  # Or "gpt-4" if available
                messages=[
                    {"role": "system", "content": "You are a medical assistant answering questions about patient cases."},
                    {"role": "user", "content": prompt}
                ],
                max_tokens=600,
                temperature=0.7
            )
            # Extract the response from ChatGPT
            answer = response["choices"][0]["message"]["content"].strip()
            logger.info(f"ChatGPT response: {answer}")
            return JsonResponse({"answer": answer}, status=200)

        except Exception as e:
            logger.exception("An error occurred while querying ChatGPT.")
            return JsonResponse({"error": f"ChatGPT query failed: {e}"}, status=500)

    logger.warning("Invalid request method.")
    return JsonResponse({"error": "Invalid request method"}, status=400)
