import os
import json
import uuid
from urllib.parse import quote
from django.shortcuts import render
from django.http import JsonResponse
from django.conf import settings
from .models import Story

# Load environment variables
from dotenv import load_dotenv
load_dotenv()

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
    Generates an educational story using Groq AI, creates audio using Groq TTS,
    and returns Unsplash image search URLs for the frontend.
    """
    if request.method != "POST":
        return JsonResponse({"error": "Only POST requests are allowed"}, status=405)

    try:
        # 1. Parse Input
        body = request.body.decode('utf-8').strip()
        data = {}
        if body:
            try:
                data = json.loads(body)
            except json.JSONDecodeError:
                if request.POST:
                    data = request.POST.dict()
                else:
                    return JsonResponse({"error": "Invalid JSON in request body"}, status=400)
        elif request.POST:
            data = request.POST.dict()

        topic = (data.get('topic') or '').strip()

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

        # 4. Generate story using Grok API (Groq)
        if client:
            try:
                prompt = f"""
                Write a comprehensive educational guide about '{topic}' for a student.
                Divide it into exactly 5 chapters.
                Respond ONLY with a valid JSON array of objects. Do not include any explanation, markdown, or extra text.
                The response must be a JSON array like this:
                [
                  {{
                    "title": "Chapter Title",
                    "content": "Detailed paragraph (3-4 sentences).",
                    "image_prompt": "Descriptive AI image prompt (10-15 words)."
                  }},
                  ... (4 more objects)
                ]
                """
                response = client.chat.completions.create(
                    model="llama-3.3-70b-versatile",
                    messages=[
                        {"role": "system", "content": "You are a helpful educational content creator. You always respond with raw JSON arrays."},
                        {"role": "user", "content": prompt},
                    ],
                    temperature=0.7,
                )
                story_content = ''
                if hasattr(response, 'choices') and response.choices:
                    choice = response.choices[0]
                    if hasattr(choice, 'message') and choice.message is not None:
                        story_content = str(choice.message.content or '').strip()
                    elif hasattr(choice, 'text'):
                        story_content = str(choice.text or '').strip()

                if not story_content:
                    raise ValueError('AI returned empty story content. Please retry.')

                # 4.a Clean up and Extract JSON robustly
                import re
                json_match = re.search(r'(\[.*\]|\{.*\})', story_content, re.DOTALL)
                if json_match:
                    story_content = json_match.group(1)

                try:
                    story_json = json.loads(story_content)
                except json.JSONDecodeError:
                    # Try one more time by stripping markdown blocks manually
                    cleaned = story_content.replace('```json', '').replace('```', '').strip()
                    story_json = json.loads(cleaned)
                
                # Handling different JSON structures from AI
                if isinstance(story_json, dict):
                    if 'chapters' in story_json:
                        story_json = story_json['chapters']
                    else:
                        # Find the first list in the dictionary
                        for key in story_json:
                            if isinstance(story_json[key], list):
                                story_json = story_json[key]
                                break
                
                # Ensure it's a list and has content
                if not isinstance(story_json, list) or len(story_json) == 0:
                    raise ValueError("AI did not return a valid list of chapters.")

            except Exception as api_error:
                return JsonResponse({"error": f"AI generation failed: {str(api_error)}"}, status=500)
        else:
            return JsonResponse({"error": "API Client not configured. Please check your .env file."}, status=500)

        # 5. Ensure media folder exists
        if not os.path.exists(settings.MEDIA_ROOT):
            os.makedirs(settings.MEDIA_ROOT, exist_ok=True)

        # 6. Generate audio file (Combined for the whole story)
        unique_filename = f"story_{uuid.uuid4().hex[:10]}.mp3"
        audio_path = os.path.join(settings.MEDIA_ROOT, unique_filename)
        audio_url = settings.MEDIA_URL + unique_filename

        if client:
            try:
                # Robust text extraction for TTS
                full_text_parts = []
                for i, ch in enumerate(story_json):
                    title = ch.get('title', f'Chapter {i+1}')
                    content = ch.get('content', '')
                    full_text_parts.append(f"Chapter {i+1}: {title}. {content}")

                full_text = " ".join(full_text_parts)
                if full_text.strip():
                    audio_response = client.audio.speech.create(
                        model="gpt-4o-mini-tts",
                        voice="alloy",
                        input=full_text,
                        response_format="mp3",
                    )
                    if hasattr(audio_response, 'read'):
                        audio_bytes = audio_response.read()
                    elif hasattr(audio_response, 'content'):
                        audio_bytes = audio_response.content
                    else:
                        audio_bytes = bytes(audio_response)

                    with open(audio_path, 'wb') as audio_file:
                        audio_file.write(audio_bytes)
                    print(f"Groq audio generated: {audio_path}")
                else:
                    audio_url = ""
            except Exception as tts_error:
                print(f"Groq audio error: {tts_error}")
                if gTTS:
                    try:
                        tts = gTTS(text=full_text, lang='en')
                        tts.save(audio_path)
                        print(f"gTTS fallback audio generated: {audio_path}")
                    except Exception as gtts_error:
                        print(f"gTTS fallback error: {gtts_error}")
                        audio_url = ""
                else:
                    audio_url = ""
        else:
            print("Groq client not configured, skipping audio generation.")
            audio_url = ""

        # 7. Images: Use Unsplash search for the most related topic image
        main_image_prompt = f"{topic}, educational illustration, photography"
        main_image_url = f"https://source.unsplash.com/featured/800x600/?{quote(main_image_prompt)}"

        # 8. Save to database for caching
        Story.objects.create(
            topic=topic,
            story_text=json.dumps(story_json),
            audio_url=audio_url,
            image_url=main_image_url
        )

        return JsonResponse({
            "story": story_json,
            "audio": audio_url,
            "image": main_image_url,
            "cached": False
        })

    except Exception as e:
        return JsonResponse({"error": f"Internal Server Error: {str(e)}"}, status=500)
