import json
import os
import openai
import logging
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.DEBUG)

def index(request):
    return JsonResponse({"message": "Realtime API endpoint working!"})

@csrf_exempt
def realtime_chat(request):
    """
    Expects a JSON payload with:
      - "messages": a list of conversation messages (each with 'role' and 'content')
      - "history": a dictionary containing patient history fields:
            PC, HPC, PMHx, DHx, FHx, SHx, SR

    This endpoint builds a system prompt that instructs the AI to act as a real human patient.
    The user is the doctor asking questions, and the AI (the patient) should provide realistic,
    gender-appropriate answers based on the provided medical history.
    The AI should determine its gender from the history if possible and answer accordingly,
    and it must never reveal that it is an AI.
    """
    if request.method != "POST":
        return JsonResponse({"error": "Only POST method allowed."}, status=400)

    try:
        data = json.loads(request.body)
        messages = data.get("messages")
        if not isinstance(messages, list):
            raise ValueError("messages must be a list")
        history_data = data.get("history", {})  # Expect a dict with history fields
    except Exception as e:
        logger.error("Invalid JSON or missing parameters: %s", e)
        return JsonResponse({"error": "Invalid JSON or missing required parameters."}, status=400)

    # Construct a detailed system prompt.
    system_prompt = (
        "You are a real human patient. The doctor (the user) will ask you medical questions, "
        "and you must respond naturally based on your personal experiences and your detailed medical history. "
        "Determine your gender (male or female) based on your history and incorporate that into your responses when applicable. "
        "Do not reveal that you are an AI or digital assistant at any point.\n\n"
        "Patient History:\n"
        f"Presenting Complaint (PC): {history_data.get('PC', 'Not provided')}\n"
        f"History of Presenting Complaint (HPC): {history_data.get('HPC', 'Not provided')}\n"
        f"Past Medical History (PMHx): {history_data.get('PMHx', 'Not provided')}\n"
        f"Drug History (DHx): {history_data.get('DHx', 'Not provided')}\n"
        f"Family History (FHx): {history_data.get('FHx', 'Not provided')}\n"
        f"Social History (SHx): {history_data.get('SHx', 'Not provided')}\n"
        f"Systems Review (SR): {history_data.get('SR', 'Not provided')}\n"
    )

    # Insert the system prompt as the first message if not already present.
    if len(messages) == 0 or messages[0].get("role") != "system" or "john" not in messages[0].get("content", "").lower():
        messages.insert(0, {"role": "system", "content": system_prompt})

    openai.api_key = os.getenv("OPENAI_API_KEY")
    try:
        logger.info("Sending messages to OpenAI: %s", messages)
        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=messages,
            max_tokens=300,
            temperature=0.7,
        )
        answer = response["choices"][0]["message"]["content"].strip()
        logger.info("Received AI answer: %s", answer)
        return JsonResponse({"response": answer}, status=200)
    except Exception as e:
        logger.exception("Error calling OpenAI API: %s", e)
        return JsonResponse({"error": str(e)}, status=500)

@csrf_exempt
def transcribe_audio(request):
    if request.method != "POST":
        return JsonResponse({"error": "Only POST method allowed."}, status=400)
    
    try:
        # Expect an audio file in the request.FILES.
        audio_file = request.FILES.get("file")
        if not audio_file:
            return JsonResponse({"error": "No audio file provided."}, status=400)
        
        openai.api_key = os.getenv("OPENAI_API_KEY")
        transcript_response = openai.Audio.transcribe(
            model="whisper-1",
            file=audio_file,
        )
        transcript_text = transcript_response["text"]
        return JsonResponse({"text": transcript_text})
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)

# Import additional endpoints from history.views for patient history and question generation.
from history.views import (
    generate_history,
    get_conditions,
    get_history_categories,
    ask_question,
    generate_questions,
    example_endpoint,
)
