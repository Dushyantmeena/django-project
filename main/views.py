import os
import json
import uuid
from django.shortcuts import render
from django.http import JsonResponse
from django.conf import settings
from .models import Story

# gTTS import safe way
try:
    from gtts import gTTS
except ImportError:
    gTTS = None

# Groq API setup (OpenAI compatible)
from openai import OpenAI

GROK_API_KEY = os.getenv('GROK_API_KEY')
if GROK_API_KEY:
    client = OpenAI(
        api_key=GROK_API_KEY,
        base_url="https://api.groq.com/openai/v1",
    )
else:
    client = None


def home(request):
    return render(request, 'index.html')


def story(request):
    return render(request, 'story.html')


def generate(request):
    """
    Generates an educational story using Gemini AI, creates audio with gTTS,
    and returns JSON data for the frontend.
    """
    if request.method != "POST":
        return JsonResponse({"error": "Only POST requests are allowed"}, status=405)

    try:
        # 1. Parse Input
        try:
            data = json.loads(request.body.decode('utf-8'))
        except json.JSONDecodeError:
            return JsonResponse({"error": "Invalid JSON in request body"}, status=400)

        topic = data.get('topic', '').strip()

        # 2. Input Validation
        if not topic:
            return JsonResponse({"error": "Topic is required"}, status=400)
        if len(topic) > 100:
            return JsonResponse({"error": "Topic too long (max 100 chars)"}, status=400)

        # 3. Check for cached story
        cached_story = Story.objects.filter(topic__iexact=topic).first()
        if cached_story:
            return JsonResponse({
                "story": json.loads(cached_story.story_text),
                "audio": cached_story.audio_url,
                "image": cached_story.image_url,
                "cached": True
            })

        # 4. Generate story using Grok API
        if client:
            try:
                prompt = f"""
                Write a comprehensive educational guide about '{topic}' for a student.
                Divide it into exactly 5 chapters.
                Respond with a JSON array of objects.
                Each object must have:
                "title": The chapter title.
                "content": A detailed paragraph explaining the topic.
                "image_prompt": A short descriptive prompt for an image generator.
                """
                response = client.chat.completions.create(
                    model="llama-3.3-70b-versatile",
                    messages=[
                        {"role": "system", "content": "You are a helpful educational content creator. Always respond in valid JSON format."},
                        {"role": "user", "content": prompt},
                    ]
                )
                story_content = response.choices[0].message.content.strip()
                
                # Clean up if model includes markdown markers (some models do even with JSON instructions)
                if story_content.startswith('```'):
                    story_content = story_content.strip('`').replace('json\n', '', 1).strip()

                story_json = json.loads(story_content)
                # If the model returned an object with a 'chapters' key instead of a list, handle it
                if isinstance(story_json, dict) and 'chapters' in story_json:
                    story_json = story_json['chapters']
                elif isinstance(story_json, dict):
                    # Try to find any list in the dictionary
                    for val in story_json.values():
                        if isinstance(val, list):
                            story_json = val
                            break

            except Exception as api_error:
                return JsonResponse({"error": f"AI generation failed (Grok): {str(api_error)}"}, status=500)
        else:
            # Fallback if API key is missing
            story_json = [
                {
                    "title": "Introduction", 
                    "content": f"An overview of {topic}.",
                    "image_prompt": f"Educational illustration of {topic}"
                }
            ]
            story_content = json.dumps(story_json)

        # 5. Ensure media folder exists
        if not os.path.exists(settings.MEDIA_ROOT):
            os.makedirs(settings.MEDIA_ROOT, exist_ok=True)

        # 6. Generate unique audio file
        unique_filename = f"story_{uuid.uuid4().hex[:10]}.mp3"
        audio_path = os.path.join(settings.MEDIA_ROOT, unique_filename)
        audio_url = settings.MEDIA_URL + unique_filename

        if gTTS:
            try:
                # Combine all text for audio
                full_text = " ".join([f"Chapter {i+1}: {ch['title']}. {ch['content']}" for i, ch in enumerate(story_json)])
                tts = gTTS(text=full_text, lang='en')
                tts.save(audio_path)
            except Exception as tts_error:
                print(f"gTTS error: {tts_error}")
                audio_url = ""
        else:
            audio_url = ""

        # 7. Generate Dynamic Image URL (Using Pollinations.ai)
        # We'll use the first chapter's image prompt for the main story image
        image_query = story_json[0].get('image_prompt', topic).replace(" ", "%20")
        image_url = f"https://pollinations.ai/p/{image_query}?width=800&height=600&seed=42"

        # 8. Save to database for caching
        Story.objects.create(
            topic=topic,
            story_text=json.dumps(story_json),
            audio_url=audio_url,
            image_url=image_url
        )

        return JsonResponse({
            "story": story_json,
            "audio": audio_url,
            "image": image_url,
            "cached": False
        })

    except Exception as e:
        return JsonResponse({"error": f"Internal Server Error: {str(e)}"}, status=500)
