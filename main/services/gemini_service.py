from google import genai
from google.genai import types
import json
import os
from django.conf import settings
from django.core.cache import cache

class GeminiService:
    @staticmethod
    def match_seekers(gig, seekers):
        api_key = "AIzaSyAE86H4sXuPIsQaWEEJF7fuiCmeuxS0Exk"
        
        if not api_key:
            print("WARNING: GOOGLE_API_KEY not found. Returning empty matches.")
            return []

        cache_key = f"gig_matches_{gig.id}"
        cached_results = cache.get(cache_key)
        if cached_results:
            print(f"Serving matches from CACHE for gig {gig.id}")
            return cached_results

        try:
            client = genai.Client(
                api_key=api_key,
                http_options=types.HttpOptions(api_version='v1beta')
            )
            
            seeker_data = []
            for s in seekers:
                seeker_data.append({
                    "id": s.id,
                    "name": s.full_name,
                    "skills": s.skills or "N/A",
                    "score": s.ojapass_score,
                    "location": s.address or "N/A",
                    "bio": s.bio or "N/A"
                })
                
            gig_data = {
                "title": gig.title,
                "description": gig.description,
                "skills_needed": gig.skills_needed,
                "location": gig.location,
                "pay": float(gig.pay_rate)
            }

            prompt = f"""
            You are an intelligent matchmaker for OjaPass, an economic platform in Nigeria.
            Your task is to match a Gig to the most suitable Job Seekers.

            Gig Details:
            {json.dumps(gig_data, indent=2)}

            Available Seekers:
            {json.dumps(seeker_data, indent=2)}

            Analyze each seeker's skills, OjaScore (higher is better), and bio. 
            Nearby location and relevant skills are high priorities.
            
            Return a JSON list of the top 5 matches.
            Each match must include:
            - seeker_id: The ID of the seeker
            - match_score: A percentage (0-100) representing how well they fit the gig
            - reasoning: A brief explanation of why they were matched.

            Return ONLY the JSON list.
            """

            # Switch to gemini-3-flash-preview which is confirmed working in this environment
            response = client.models.generate_content(
                model='gemini-3-flash-preview',
                contents=prompt,
                config={
                    'response_mime_type': 'application/json'
                }
            )
            
            text = response.text.strip()
            
            # Remove markdown formatting if present
            if text.startswith("```json"):
                text = text[7:].split("```")[0].strip()
            elif text.startswith("```"):
                text = text[3:].split("```")[0].strip()
                
            results = json.loads(text)
            cache.set(cache_key, results, 3600) # Cache for 1 hour
            return results
        except Exception as e:
            print(f"Gemini Error (New SDK): {e}")
            # Fallback to simple matching if Gemini fails/quota exceeded
            fallback_matches = []
            # Sort by score for a slightly better fallback
            sorted_seekers = sorted(seekers, key=lambda s: s.ojapass_score, reverse=True)
            for s in sorted_seekers[:5]:
                fallback_matches.append({
                    "seeker_id": s.id,
                    "match_score": 75,
                    "reasoning": "Matched based on strong OjaScore and system availability (Fallback)."
                })
            return fallback_matches

    @staticmethod
    def generate_score_narrative(user, history_record=None):
        api_key = "AIzaSyAE86H4sXuPIsQaWEEJF7fuiCmeuxS0Exk"
        
        if not api_key:
            return "Keep trading and completing gigs to build your OjaScore and unlock new tiers!"

        cache_key = f"ojascore_narrative_{user.id}_{user.ojapass_score}"
        cached_narrative = cache.get(cache_key)
        if cached_narrative:
            return cached_narrative

        try:
            from .oja_score import build_narrative_prompt
            from ..models import OjaScoreHistory

            client = genai.Client(
                api_key=api_key,
                http_options=types.HttpOptions(api_version='v1beta')
            )
            
            # Calculate delta for the prompt
            new_score = user.ojapass_score
            delta = 0
            if history_record:
                prev_history = OjaScoreHistory.objects.filter(
                    user=user, 
                    timestamp__lt=history_record.timestamp
                ).order_by('-timestamp').first()
                if prev_history:
                    delta = new_score - prev_history.score
            
            prompt = build_narrative_prompt(user, history_record, new_score, delta)

            response = client.models.generate_content(
                model='gemini-3-flash-preview',
                contents=prompt
            )
            
            text = response.text.strip()
            
            cache.set(cache_key, text, 3600 * 24) # Cache for 24 hours
            return text
        except Exception as e:
            print(f"Gemini Error (Narrative): {e}")
            return "Keep trading and completing gigs to build your OjaScore and unlock new tiers!"
