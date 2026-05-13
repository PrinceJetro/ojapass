from django.shortcuts import render, redirect, get_object_or_404
from django.http import JsonResponse
from django.views import View
from django.contrib.auth.mixins import LoginRequiredMixin
from ..models import Notification, OjaScoreHistory
from ..services.gemini_service import GeminiService

class ScoreNarrativeAPIView(LoginRequiredMixin, View):
    def get(self, request):
        history = OjaScoreHistory.objects.filter(user=request.user).order_by('-timestamp').first()
        from ..services.gemini_service import GeminiService
        narrative = GeminiService.generate_score_narrative(request.user, history)
        return JsonResponse({"success": True, "narrative": narrative, "currentScore": request.user.ojapass_score})

class NotificationListView(LoginRequiredMixin, View):
    def get(self, request):
        notifications = Notification.objects.filter(user=request.user).order_by('-created_at')
        unread_count = notifications.filter(is_read=False).count()
        score_history = OjaScoreHistory.objects.filter(user=request.user).order_by('-timestamp')[:5]
        
        context = {
            'notifications': notifications,
            'unread_count': unread_count,
            'score_history': score_history,
            'user': request.user
        }
        return render(request, 'notification_center.html', context)
        
    def post(self, request, pk): # Using POST for update
        Notification.objects.filter(id=pk, user=request.user).update(is_read=True)
        return JsonResponse({"success": True})