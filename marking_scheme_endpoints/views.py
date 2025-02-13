# new_api/views.py
import json
import os
import re
from django.http import JsonResponse
from django.views.decorators.http import require_POST
import openai

@require_POST
def evaluate_history(request):
    """
    Endpoint to evaluate a user's history response.
    Expects a JSON payload with the following keys:
      - expected_history: The ideal or expected history details.
      - time_taken: The time (in seconds) taken to complete the history.
      - questions_count: The number of questions asked.
      - user_response: The actual response provided by the user.
    """
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)
    
    # Extract parameters from the payload.
    expected_history = data.get('expected_history')
    time_taken = data.get('time_taken')
    questions_count = data.get('questions_count')
    user_response = data.get('user_response')
    
    # Validate that all required parameters are provided.
    if not all([expected_history, time_taken, questions_count, user_response]):
        return JsonResponse({'error': 'Missing one or more required parameters.'}, status=400)
    
    # Compose the prompt for ChatGPT.
    prompt = (
        f"Compare the following expected history with the user's response.\n\n"
        f"Expected History: {expected_history}\n"
        f"User's Response: {user_response}\n\n"
        f"Additional details:\n"
        f"Time taken: {time_taken} seconds\n"
        f"Number of questions asked: {questions_count}\n\n"
        "Evaluate whether the user provided all necessary information. "
        "Provide a score out of 100 and detailed feedback on what was missed or done well."
    )
    
    # Set your OpenAI API key (make sure it's set in your environment variables)
    openai.api_key = os.getenv("OPENAI_API_KEY")
    
    try:
        # Call ChatGPT using the ChatCompletion endpoint.
        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "You are an assistant that evaluates user responses to historical data."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.7,
            max_tokens=150,
        )
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)
    
    # Extract the content from the response.
    ai_message = response.choices[0].message['content']
    
    # Optionally extract a numeric score from the message (a simple approach).
    score_match = re.search(r"(\d{1,3})", ai_message)
    score = score_match.group(1) if score_match else None
    
    return JsonResponse({
        'score': score,
        'feedback': ai_message
    })

def example_endpoint(request):
    return JsonResponse({'message': 'Hello from the new API!'})
