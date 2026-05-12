from django.db import models

# Create your models here.

class Story(models.Model):
    topic = models.CharField(max_length=100)
    story_text = models.TextField()
    audio_url = models.URLField(blank=True)
    image_url = models.URLField()
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Story about {self.topic}"
