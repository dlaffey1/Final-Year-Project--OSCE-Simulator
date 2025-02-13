import json
import os
import re
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
import openai

@csrf_exempt
def evaluate_history(request):
    """
    Endpoint to evaluate a user's history response.
    Expects a JSON payload with the following keys:
      - expected_history: The ideal or expected history details.
      - time_taken: The time (in seconds) taken to complete the history.
      - questions_count: The number of questions asked.
      - user_response: The actual response provided by the user.
    """
    print("Incoming request body:", request.body)
    
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)
    
    expected_history = data.get('expected_history')
    time_taken = data.get('time_taken')
    questions_count = data.get('questions_count')
    user_response = data.get('user_response')
    
    # Validate parameters (allow 0 for questions_count)
    if expected_history is None or time_taken is None or questions_count is None or user_response is None:
        return JsonResponse({'error': 'Missing one or more required parameters.'}, status=400)
    
    # Updated prompt: Instruct ChatGPT to return a JSON object with overall score,
    # overall feedback, and per-section scores and feedback.
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
    
    # Set your OpenAI API key.
    openai.api_key = os.getenv("OPENAI_API_KEY")
    
    try:
        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "You are an assistant that evaluates user responses to historical data."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.7,
            max_tokens=250,
        )
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)
    
    ai_message = response.choices[0].message['content']
    
    try:
        result_json = json.loads(ai_message)
    except json.JSONDecodeError:
        # Fallback: if JSON parsing fails, return an overall score extracted from the text.
        score_match = re.search(r"(\d{1,3})", ai_message)
        overall_score = score_match.group(1) if score_match else "0"
        result_json = {
            "overall_score": overall_score,
            "overall_feedback": ai_message,
            "section_scores": {},
            "section_feedback": {}
        }
    
    return JsonResponse(result_json)

def example_endpoint(request):
    return JsonResponse({'message': 'Hello from the new API!'})
