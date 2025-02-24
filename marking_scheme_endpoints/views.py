import json
import os
import re
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
import openai
import logging

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.DEBUG)

@csrf_exempt
def evaluate_history(request):
    logger.info("evaluate_history: Received a request.")
    print("evaluate_history: Received a request.")

    # Log the raw request body.
    print("Incoming request body:", request.body)
    logger.debug("Incoming request body: %s", request.body)
    
    try:
        data = json.loads(request.body)
        logger.info("Request JSON parsed successfully.")
    except json.JSONDecodeError as e:
        logger.error("Invalid JSON received: %s", e)
        print("Invalid JSON received:", e)
        return JsonResponse({'error': 'Invalid JSON'}, status=400)
    
    # Extract parameters.
    expected_history = data.get('expected_history')
    time_taken = data.get('time_taken')
    questions_count = data.get('questions_count')
    user_response = data.get('user_response')
    
    logger.info("Extracted parameters: expected_history length=%s, time_taken=%s, questions_count=%s, user_response length=%s",
                len(expected_history) if expected_history else 0,
                time_taken,
                questions_count,
                len(user_response) if user_response else 0)
    
    # Validate parameters (allow 0 for questions_count).
    if expected_history is None or time_taken is None or questions_count is None or user_response is None:
        logger.error("Missing one or more required parameters.")
        return JsonResponse({'error': 'Missing one or more required parameters.'}, status=400)
    
    # Build the prompt.
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

    # Set your OpenAI API key.
    openai.api_key = os.getenv("OPENAI_API_KEY")
    
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
        # Fallback: if JSON parsing fails, extract an overall score from the text.
        score_match = re.search(r"(\d{1,3})", ai_message)
        overall_score = score_match.group(1) if score_match else "0"
        result_json = {
            "overall_score": overall_score,
            "overall_feedback": ai_message,
            "section_scores": {},
            "section_feedback": {}
        }
    
    logger.info("Returning result: %s", result_json)
    return JsonResponse(result_json)

@csrf_exempt
def compare_answer(request):
    """
    New route that accepts a question, the expected (perfect) answer, and the user's answer.
    It compares the user's answer to the expected answer and returns a percentage score and very in-depth feedback.
    Expects a JSON payload:
    {
      "question": "<question text>",
      "expected_answer": "<perfect answer>",
      "user_answer": "<user's answer>"
    }
    Returns a JSON object:
    {
      "score": "<percentage score>",
      "feedback": "<very in-depth feedback>"
    }
    """
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
    
    # Updated prompt with instructions for very in-depth feedback.
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
    openai.api_key = os.getenv("OPENAI_API_KEY")
    
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
