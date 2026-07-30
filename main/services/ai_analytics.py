import os
import json
from django.core.cache import cache
from django.utils import timezone
from google import genai
from google.genai import types

from .analytics import get_sales_trends, generate_restock_alerts


class AIAnalytics:
    @staticmethod
    def generate_dashboard_report(user, days=30):
        """
        Generate an AI-enhanced dashboard report including:
         - weekly/monthly performance highlights
         - top-performing products
         - prioritized restock recommendations with reasons

        Returns dict with `summary` (text) and `data` (structured JSON).
        """
        api_key = os.environ.get('GEMINI_API_KEY')
        cache_key = f"ai_analytics_report_{user.id}_{days}"
        cached = cache.get(cache_key)
        if cached:
            return cached

        # Prepare structured context for the model
        sales = get_sales_trends(user, days=days)
        restock = generate_restock_alerts(user, lookback_days=90, horizon_days=30)

        products_snippet = []
        for p in user.products.all()[:50]:
            products_snippet.append({
                'id': p.id,
                'name': p.name,
                'qty_on_hand': p.quantity_in_stock,
                'selling_price': float(p.selling_price or 0),
            })

        prompt = f"""
You are an expert retail analyst. Use the provided sales history and inventory snapshot to create a concise report for the merchant. Provide both a short natural-language summary and a structured JSON object with these fields:

- top_products: list of up to 5 products with highest recent revenue (id, name, revenue_last_30_days)
- weekly_highlights: 3 bullet points explaining recent weekly performance trends
- monthly_summary: one paragraph summary of month-to-date performance and recommendations
- restock_recommendations: list of objects {{"product_id", "product_name", "reason", "recommended_order_qty"}}

Context:
Sales (daily list): {json.dumps(sales['daily'][-14:], indent=2)}
Weekly aggregates: {json.dumps(sales['weekly'], indent=2)}
Monthly aggregates: {json.dumps(sales['monthly'], indent=2)}
Inventory snapshot (first 50 products): {json.dumps(products_snippet, indent=2)}
Existing restock signals (from simple heuristic): {json.dumps(restock, indent=2)}

Return ONLY a JSON object matching the schema described above.
"""

        if not api_key:
            # No API key — return heuristic-based fallback
            fallback = {
                'summary': 'AI unavailable — showing heuristic results.',
                'data': {
                    'top_products': [],
                    'weekly_highlights': [],
                    'monthly_summary': '',
                    'restock_recommendations': restock,
                }
            }
            cache.set(cache_key, fallback, 300)
            return fallback

        try:
            client = genai.Client(api_key=api_key, http_options=types.HttpOptions(api_version='v1beta'))
            response = client.models.generate_content(
                model='gemini-3-flash-preview',
                contents=prompt,
                config={'response_mime_type': 'application/json'}
            )
            text = response.text.strip()
            # strip code fences
            if text.startswith('```'):
                text = text.split('```')[-2].strip()
            result = json.loads(text)
            out = {'summary': None, 'data': result}
            # Optionally build a short summary from the structured data
            out['summary'] = (out['data'].get('monthly_summary') or '')
            cache.set(cache_key, out, 3600)
            return out
        except Exception as e:
            print(f"AI analytics error: {e}")
            fallback = {
                'summary': 'AI analysis failed — showing heuristic results.',
                'data': {
                    'top_products': [],
                    'weekly_highlights': [],
                    'monthly_summary': '',
                    'restock_recommendations': restock,
                }
            }
            cache.set(cache_key, fallback, 60)
            return fallback
