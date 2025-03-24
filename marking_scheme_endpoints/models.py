from django.db import models
import uuid
class HistoryMarkingResult(models.Model):
    expected_history = models.TextField()
    user_response = models.TextField()
    conversation_logs = models.TextField(blank=True, null=True)
    guessed_condition = models.CharField(max_length=255)
    right_disease = models.CharField(max_length=255)
    time_taken = models.FloatField()
    questions_count = models.IntegerField()
    overall_score = models.CharField(max_length=10)  # e.g., "50%" or "0"
    overall_feedback = models.TextField()
    section_scores = models.JSONField()  # Django 3.1+
    section_feedback = models.JSONField()
    history_taking_feedback = models.TextField(blank=True, null=True)
    history_taking_score = models.CharField(max_length=10, blank=True, null=True)
    profile_questions = models.JSONField(blank=True, null=True)
    user_id = models.UUIDField(default=uuid.uuid4)  # Updated to use UUIDField
    created_at = models.DateTimeField(auto_now_add=True)


    def __str__(self):
        return f"MarkingResult {self.id} - {self.overall_score}"
