from django.db import models
from django.contrib.auth.models import User
import uuid

# ✅ Model for storing medical conditions from MIMIC database
class MimicCondition(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    condition_type = models.CharField(max_length=255, unique=True)

    def __str__(self):
        return self.condition_type

# ✅ Model for storing patient histories linked to a condition
class MimicPatientHistory(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    condition_type = models.ForeignKey(MimicCondition, on_delete=models.CASCADE)
    history_text = models.TextField()

    def __str__(self):
        return f"{self.condition_type}: {self.history_text[:50]}"

# ✅ Model for user profiles (storing avatar/profile image)
class UserProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, primary_key=True)
    avatar_url = models.TextField(blank=True, null=True, default="/default-avatar.jpg")  # Default profile pic

    def __str__(self):
        return f"{self.user.username}'s Profile"
