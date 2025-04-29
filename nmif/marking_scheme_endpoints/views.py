import json
import os
import re
import uuid
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
import openai
import logging
import time
from dotenv import load_dotenv
load_dotenv()
import hashlib
def generate_user_uuid(email: str) -> str:
    """
    Generate a consistent UUID based on the provided email address.
    Uses MD5 hashing to produce a consistent UUID.
    """
    email_normalized = email.lower().strip()
    hash_digest = hashlib.md5(email_normalized.encode("utf-8")).hexdigest()
    return str(uuid.UUID(hash_digest))

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.DEBUG)
from supabase import create_client, Client

SUPABASE_URL = os.getenv("NEXT_PUBLIC_SUPABASE_URL")
SUPABASE_KEY = os.getenv("NEXT_PUBLIC_SUPABASE_ANON_KEY")
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

def get_user_id(data):
    """
    Ensure that a valid UUID is returned.
    - If the user_id field is provided and valid, return it.
    - Otherwise, if an email is provided, generate a consistent UUID from it.
    - If neither is provided, generate a new random UUID.
    """
    user_id = data.get("user_id")
    if user_id:
        try:
            return str(uuid.UUID(user_id))
        except Exception as e:
            logger.error("Invalid UUID provided: %s", e)
    email = data.get("email")
    if email:
        return generate_user_uuid(email)
    return str(uuid.uuid4())

def save_marking_result(result_json, data):
    # The basic history_entries table includes overall_score.
    response = supabase.table("history_entries").insert({
        "user_id": get_user_id(data),
        "expected_history": data.get("expected_history"),
        "user_response": data.get("user_response"),
        "conversation_logs": data.get("conversation_logs"),
        "guessed_condition": data.get("guessed_condition"),
        "right_disease": data.get("right_disease"),
        "time_taken": data.get("time_taken"),
        "questions_count": data.get("questions_count"),
        "overall_score": result_json.get("overall_score"),
        "overall_feedback": result_json.get("overall_feedback"),
        "section_scores": result_json.get("section_scores"),
        "section_feedback": result_json.get("section_feedback"),
        "category": data.get("category")
    }).execute()
    logger.info("Supabase insert response (history_entries): %s", response)
    return response

def save_history_taking_details(feedback_json, data, overall_score):
    """
    Save the detailed history-taking feedback (including score, feedback, and profile questions)
    into a separate table named history_entries_with_profiles.
    Now also records overall_score.
    """
    payload = {
        "user_id": get_user_id(data),
        "expected_history": data.get("expected_history"),
        "user_response": data.get("user_response"),
        "conversation_logs": data.get("conversation_logs"),
        "guessed_condition": data.get("guessed_condition"),
        "right_disease": data.get("right_disease"),
        "time_taken": data.get("time_taken"),
        "questions_count": data.get("questions_count"),
        "overall_score": overall_score,
        "history_taking_feedback": feedback_json.get("feedback"),
        "history_taking_score": feedback_json.get("score"),
        "profile_questions": feedback_json.get("profile_questions"),
        "category": data.get("category")
    }
    response = supabase.table("history_entries_with_profiles").insert(payload).execute()
    logger.info("Supabase insert response (history_entries_with_profiles): %s", response)
    return response

def profile_exists_for_condition(mimic_icd_code):
    """
    Checks if an associated profile exists for the given mimic ICD code.
    Returns True if a matching record is found in the mapping file.
    """
    mapping_file = "text2dt_mimic_mapping_english-full-profile.json"
    if not os.path.exists(mapping_file):
        logger.error("Mapping file not found in profile_exists_for_condition.")
        return False
    try:
        with open(mapping_file, "r", encoding="utf-8") as f:
            text2dt_mapping = json.load(f)
    except Exception as e:
        logger.error("Error reading mapping file in profile_exists_for_condition: %s", e)
        return False
    normalized = mimic_icd_code.replace(".", "").lstrip("0")
    matched = next(
        (
            record for record in text2dt_mapping
            if normalized in [code.replace(".", "").lstrip("0") for code in record.get("mapped_mimic_group", {}).get("icd9_codes", [])]
        ),
        None
    )
    return bool(matched)

@csrf_exempt
def evaluate_history(request):
    logger.info("evaluate_history: Received a request.")
    print("evaluate_history: Received a request.")

    print("Incoming request body:", request.body)
    logger.debug("Incoming request body: %s", request.body)

    try:
        data = json.loads(request.body)
        logger.info("Request JSON parsed successfully.")
    except json.JSONDecodeError as e:
        logger.error("Invalid JSON received: %s", e)
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    expected_history = data.get('expected_history')
    time_taken = data.get('time_taken')
    questions_count = data.get('questions_count')
    user_response = data.get('user_response')
    conversation_logs = data.get('conversation_logs')
    guessed_condition = data.get('guessed_condition')
    right_disease = data.get('right_disease')
    # user_id is handled in get_user_id()

    logger.info("Extracted parameters: expected_history length=%s, time_taken=%s, questions_count=%s, user_response length=%s, conversation_logs=%s, guessed_condition=%s, right_disease=%s",
                len(expected_history) if expected_history else 0,
                time_taken,
                questions_count,
                len(user_response) if user_response else 0,
                conversation_logs,
                guessed_condition,
                right_disease)

    if expected_history is None or time_taken is None or questions_count is None or user_response is None:
        logger.error("Missing one or more required parameters.")
        return JsonResponse({'error': 'Missing one or more required parameters.'}, status=400)

    prompt = f"""
You are provided with the expected patient history and a user's response.
Expected History: {expected_history}
User's Response: {user_response}
Additional details:
Time taken: {time_taken} seconds
Number of questions asked: {questions_count}

Evaluate the user's response for each of the following sections:
- Presenting Complaint (PC)
- History of Presenting Complaint (HPC)
- Past Medical History (PMHx)
- Drug History (DHx)
- Family History (FHx)
- Social History (SHx)
- Systems Review (SR)

Return a JSON object exactly in this format:
{{
  "overall_score": "<overall percentage score out of 100>",
  "overall_feedback": "<detailed overall feedback>",
  "section_scores": {{
      "PC": "<percentage score for Presenting Complaint>",
      "HPC": "<percentage score for History of Presenting Complaint>",
      "PMHx": "<percentage score for Past Medical History>",
      "DHx": "<percentage score for Drug History>",
      "FHx": "<percentage score for Family History>",
      "SHx": "<percentage score for Social History>",
      "SR": "<percentage score for Systems Review>"
  }},
  "section_feedback": {{
      "PC": "<feedback for Presenting Complaint>",
      "HPC": "<feedback for History of Presenting Complaint>",
      "PMHx": "<feedback for Past Medical History>",
      "DHx": "<feedback for Drug History>",
      "FHx": "<feedback for Family History>",
      "SHx": "<feedback for Social History>",
      "SR": "<feedback for Systems Review>"
  }}
}}
Make sure the JSON is valid.
"""
    logger.debug("Constructed prompt: %s", prompt)

    openai.api_key = os.getenv("NEXT_PUBLIC_OPENAI_API_KEY") or os.getenv("OPENAI_API_KEY")

    try:
        logger.info("Sending prompt to OpenAI...")
        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "You are an assistant that evaluates user responses to historical data."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.7,
            max_tokens=250,
        )
        logger.info("Received response from OpenAI.")
    except Exception as e:
        logger.error("Error during OpenAI request: %s", e)
        return JsonResponse({'error': str(e)}, status=500)

    ai_message = response.choices[0].message['content']
    logger.debug("Raw AI message: %s", ai_message)

    try:
        result_json = json.loads(ai_message)
        logger.info("AI response parsed successfully as JSON.")
    except json.JSONDecodeError as e:
        logger.error("Failed to parse AI response as JSON: %s", e)
        score_match = re.search(r"(\d{1,3})", ai_message)
        overall_score = score_match.group(1) if score_match else "0"
        result_json = {
            "overall_score": overall_score,
            "overall_feedback": ai_message,
            "section_scores": {},
            "section_feedback": {}
        }

    # Only trigger detailed history-taking if conversation logs, guessed condition, and right disease exist
    # AND if an associated profile is found for the mimic condition.
    if conversation_logs and guessed_condition and right_disease and profile_exists_for_condition(right_disease):
        logger.info("Associated profile found for the mimic condition; calling assess_history_taking for detailed history-taking feedback...")
        history_taking_payload = {
            "conversation_logs": conversation_logs,
            "mimic_icd_code": right_disease,
            "expected_history": expected_history,
            "user_response": user_response,
            "questions_count": questions_count,
            "time_taken": time_taken,
            "user_id": get_user_id(data),
            "guessed_condition": guessed_condition,
            "right_disease": right_disease
        }
        assess_response = assess_history_taking(history_taking_payload)
        if assess_response.status_code == 200:
            try:
                history_taking_data = json.loads(assess_response.content)
            except Exception as e:
                logger.error("Error parsing history-taking feedback: %s", e)
                history_taking_data = {}
        else:
            history_taking_data = {
                "feedback": "Could not retrieve history-taking feedback.",
                "score": "0",
                "profile_questions": []
            }
        # Save the detailed feedback in the separate table.
        save_history_taking_details(history_taking_data, data, result_json.get("overall_score"))
        # Merge the detailed fields into the result JSON so they are returned to the client.
        result_json["history_taking_feedback"] = history_taking_data.get("feedback", "")
        result_json["history_taking_score"] = history_taking_data.get("score", "0")
        result_json["profile_questions"] = history_taking_data.get("profile_questions", [])

    try:
        save_marking_result(result_json, data)
    except Exception as e:
        logger.error("Error saving marking result: %s", e)

    logger.info("Returning result: %s", result_json)
    return JsonResponse(result_json)

@csrf_exempt
def assess_history_taking(data):
    logger.info("assess_history_taking: Function activated.")
    print("assess_history_taking: Function activated.")

    logger.debug(f"Received data: {json.dumps(data, ensure_ascii=False, indent=2)}")
    print(f"Received data: {json.dumps(data, ensure_ascii=False, indent=2)}")

    conversation_logs = data.get("conversation_logs")
    mimic_icd_code = data.get("mimic_icd_code")

    if not conversation_logs or not mimic_icd_code:
        logger.error("assess_history_taking: Missing required parameters.")
        return JsonResponse({'error': 'Missing required parameters.'}, status=400)

    mapping_file = "text2dt_mimic_mapping_english-full-profile.json"
    if not os.path.exists(mapping_file):
        logger.error(f"assess_history_taking: Mapping file {mapping_file} not found.")
        return JsonResponse({'error': 'Mapping file not found.'}, status=500)

    try:
        with open(mapping_file, "r", encoding="utf-8") as f:
            text2dt_mapping = json.load(f)
        logger.info(f"assess_history_taking: Successfully loaded {mapping_file}.")
    except Exception as e:
        logger.error(f"assess_history_taking: Error reading {mapping_file}: {e}")
        return JsonResponse({'error': 'Error reading mapping file.'}, status=500)

    normalized_mimic_icd = mimic_icd_code.replace(".", "").lstrip("0")

    available_icd9_codes = [
        code.replace(".", "").lstrip("0") for record in text2dt_mapping
        for code in record.get("mapped_mimic_group", {}).get("icd9_codes", [])
    ]
    logger.debug(f"Available ICD-9 codes in JSON file (normalized): {json.dumps(available_icd9_codes, indent=2)}")
    print(f"Available ICD-9 codes in JSON file (normalized): {json.dumps(available_icd9_codes, indent=2)}")

    matched_condition = next(
        (
            record for record in text2dt_mapping
            if normalized_mimic_icd in [code.replace(".", "").lstrip("0") for code in record.get("mapped_mimic_group", {}).get("icd9_codes", [])]
        ),
        None
    )

    if not matched_condition:
        logger.warning(f"No match found for ICD-9 code: {mimic_icd_code} (normalized: {normalized_mimic_icd})")
        return JsonResponse({'error': f'No profile available for condition {mimic_icd_code}.'}, status=404)

    text2dt_condition = matched_condition.get("text2dt_condition", "Unknown Condition")
    expected_profile = matched_condition.get("english_profile", [])
    logger.info(f"Found profile for condition '{text2dt_condition}'.")
    print(f"Found profile for condition '{text2dt_condition}'.")

    prompt = f"""
The user conducted a patient interview and provided the following conversation logs:

Conversation Logs:
{conversation_logs}

The expected structured questioning profile for this condition '{text2dt_condition}' is:
{json.dumps(expected_profile, indent=2)}
Note: The provided profile includes logical decision nodes (denoted by "D node:") that encapsulate additional decision-making logic. Please incorporate these details into your evaluation to provide more comprehensive feedback.

Please translate the above profile questions from Chinese to English, and ensure that the detailed feedback you provide is entirely in English (do not include any Chinese).
Then, compare the user's conversation logs to the translated profile and provide detailed feedback on the history-taking performance.

Return a JSON object exactly in this format:
{{
  "feedback": "<detailed feedback for history-taking in English>",
  "score": "<percentage score (0-100)>",
  "profile_questions": <translated profile questions as an array>
}}

Ensure the JSON is valid and contains no additional text.
"""
    logger.debug(f"Constructed AI prompt:\n{prompt}")

    openai.api_key = os.getenv("NEXT_PUBLIC_OPENAI_API_KEY") or os.getenv("OPENAI_API_KEY")

    try:
        logger.info("Sending prompt to OpenAI for evaluation...")
        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.7,
            max_tokens=400,
        )
        logger.info("Received response from OpenAI for assessment.")
        feedback_json = json.loads(response.choices[0].message["content"])
        logger.info("Successfully parsed AI response for assessment.")
    except Exception as e:
        logger.error(f"Error during OpenAI request: {e}")
        return JsonResponse({'error': str(e)}, status=500)

    logger.info("Returning feedback response from assess_history_taking.")
    return JsonResponse(feedback_json)

@csrf_exempt
def generate_tree(request):
    tree_file = "decision_tree.json"
    
    if os.path.exists(tree_file):
        logger.info("Decision tree file found. Loading tree from file.")
        try:
            with open(tree_file, "r") as f:
                decision_tree = json.load(f)
            return JsonResponse(decision_tree)
        except Exception as e:
            logger.error("Error reading decision tree file: %s", e)
            return JsonResponse({'error': 'Error reading decision tree file.'}, status=500)
    else:
        prompt = (
            "Generate a decision tree for clinical history taking for a condition. "
            "The decision tree should include at least one example condition with a corresponding MIMIC ICD code. "
            "Show the perfect navigation of its logic question tree. "
            "Return the tree in valid JSON format with keys for each decision node."
        )
        openai.api_key = os.getenv("NEXT_PUBLIC_OPENAI_API_KEY") or os.getenv("OPENAI_API_KEY")
        try:
            logger.info("No decision tree file found. Requesting tree generation from OpenAI...")
            response = openai.ChatCompletion.create(
                model="gpt-3.5-turbo",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.7,
                max_tokens=500,
            )
            tree_message = response.choices[0].message['content']
            decision_tree = json.loads(tree_message)
            with open(tree_file, "w") as f:
                json.dump(decision_tree, f, indent=4)
            return JsonResponse(decision_tree)
        except Exception as e:
            logger.error("Error generating decision tree: %s", e)
            return JsonResponse({'error': 'Error generating decision tree.'}, status=500)

@csrf_exempt
def mark_conversation(request):
    logger.info("mark_conversation: Received a request.")
    try:
        data = json.loads(request.body)
        logger.info("mark_conversation: Request JSON parsed successfully.")
    except json.JSONDecodeError as e:
        logger.error("mark_conversation: Invalid JSON received: %s", e)
        return JsonResponse({'error': 'Invalid JSON'}, status=400)
    
    guessed_disease = data.get('guessed_disease')
    right_disease = data.get('right_disease')
    conversation_logs = data.get('conversation_logs')
    decision_tree = data.get('decision_tree')
    
    if not all([guessed_disease, right_disease, conversation_logs, decision_tree]):
        logger.error("mark_conversation: Missing one or more required parameters.")
        return JsonResponse({'error': 'Missing one or more required parameters.'}, status=400)
    
    prompt = (
        f"Using the following decision tree:\n{json.dumps(decision_tree, indent=2)}\n\n"
        f"Evaluate the following conversation logs in which the user navigated a clinical history taking session. "
        f"The user guessed the disease as '{guessed_disease}', but the correct disease is '{right_disease}'.\n\n"
        f"Conversation Logs:\n{conversation_logs}\n\n"
        "Provide detailed feedback on where the user can improve their history taking abilities according to the decision tree logic. "
        "Return the feedback in valid JSON format with at least the key 'feedback'."
    )
    
    openai.api_key = os.getenv("NEXT_PUBLIC_OPENAI_API_KEY") or os.getenv("OPENAI_API_KEY")
    try:
        logger.info("mark_conversation: Sending prompt to OpenAI for feedback generation...")
        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.7,
            max_tokens=300,
        )
        feedback_message = response.choices[0].message['content']
        feedback_json = json.loads(feedback_message)
        return JsonResponse(feedback_json)
    except Exception as e:
        logger.error("mark_conversation: Error during OpenAI request: %s", e)
        return JsonResponse({'error': 'Error generating feedback.'}, status=500)


@csrf_exempt
def compare_answer(request):
    logger.info("Received request to compare answer.")
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON"}, status=400)
    
    question = data.get("question")
    expected_answer = data.get("expected_answer")
    user_answer = data.get("user_answer")
    
    if not question or expected_answer is None or user_answer is None:
        logger.error("Missing required parameters in compare_answer.")
        return JsonResponse({"error": "Missing required parameters."}, status=400)
    
    prompt = f"""
Compare the user's answer to the perfect answer for the following question:
Question: {question}
Perfect Answer: {expected_answer}
User's Answer: {user_answer}

Please provide a detailed evaluation of the user's answer. In your response, please:
- Assign a percentage score (from 0 to 100) indicating how closely the user's answer matches the perfect answer.
- Provide very in-depth feedback explaining what the user answered correctly, what important information was missed, and any inaccuracies or errors in the user's answer.
- Be as specific as possible, noting any key phrases or details that are missing or incorrect.

Return ONLY a JSON object exactly in this format:
{{
  "score": "<percentage score>",
  "feedback": "<very in-depth feedback>"
}}

Ensure the JSON is valid.
"""
    logger.debug("Constructed prompt for compare_answer: %s", prompt)
    openai.api_key = os.getenv("NEXT_PUBLIC_OPENAI_API_KEY") or os.getenv("OPENAI_API_KEY")
    
    try:
        logger.info("Sending prompt to OpenAI for compare_answer...")
        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "You are an assistant that compares answers and provides very in-depth feedback."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.7,
            max_tokens=300,
        )
        logger.info("Received response from OpenAI for compare_answer.")
    except Exception as e:
        logger.error("Error during OpenAI request in compare_answer: %s", e)
        return JsonResponse({'error': str(e)}, status=500)
    
    ai_message = response.choices[0].message["content"]
    logger.debug("Raw AI message for compare_answer: %s", ai_message)
    
    try:
        result_json = json.loads(ai_message)
    except json.JSONDecodeError as e:
        logger.error("Failed to parse AI response as JSON in compare_answer: %s", e)
        json_match = re.search(r"\{.*\}", ai_message, re.DOTALL)
        if json_match:
            try:
                result_json = json.loads(json_match.group(0))
                logger.info("Extracted JSON via regex fallback in compare_answer.")
            except json.JSONDecodeError as e2:
                logger.error("Fallback JSON extraction failed in compare_answer: %s", e2)
                return JsonResponse({'error': 'Failed to parse AI response as JSON.'}, status=500)
        else:
            return JsonResponse({'error': 'Failed to parse AI response as JSON.'}, status=500)
    
    logger.info("Returning compare_answer result: %s", result_json)
    return JsonResponse(result_json)
@csrf_exempt
def example_endpoint(request):
    return JsonResponse({'message': 'Hello from the new API!'})