import json
import uuid
from django.shortcuts import render, get_object_or_404
from django.http import JsonResponse
from django.views import View
from django.contrib.auth.mixins import LoginRequiredMixin
from ..models import OjaUser, PortfolioPost, ClientReview, Notification
from ..services.oja_score import recalculate_ojascore

class PortfolioListView(LoginRequiredMixin, View):
    """Seeker's own portfolio dashboard"""
    def get(self, request):
        posts = PortfolioPost.objects.filter(
            seeker=request.user
        ).order_by('-created_at')
        
        verified_count = posts.filter(
            client_review__is_completed=True
        ).count()
        
        reviews = ClientReview.objects.filter(
            post__seeker=request.user,
            is_completed=True
        )
        avg_rating = (
            sum(r.rating for r in reviews) / reviews.count()
            if reviews.count() > 0 else 0
        )
        
        context = {
            'posts': posts,
            'verified_count': verified_count,
            'total_posts': posts.count(),
            'avg_rating': round(avg_rating, 1),
            'review_count': reviews.count(),
        }
        return render(request, 'portfolio.html', context)

    def post(self, request):
        """Create a new portfolio post"""
        data = json.loads(request.body)
        
        post = PortfolioPost.objects.create(
            seeker=request.user,
            title=data.get('title'),
            description=data.get('description') or "No description provided",
            category=data.get('category'),
            location=data.get('location'),
            work_date=data.get('workDate'),
            client_name=data.get('clientName'),
            client_contact=data.get('clientContact'),
            amount_earned=data.get('amountEarned') or None,
        )
        
        return JsonResponse({
            "success": True,
            "postId": post.id,
            "reviewLink": request.build_absolute_uri(post.review_link),
            "message": "Portfolio post created. Share the review link with your client."
        })


class PublicPortfolioView(View):
    """
    Public profile page — anyone can see a seeker's portfolio.
    This is what you share with potential employers.
    """
    def get(self, request, phone):
        seeker = get_object_or_404(OjaUser, phone=phone)
        posts = PortfolioPost.objects.filter(
            seeker=seeker, status='active'
        ).order_by('-work_date')
        
        reviews = ClientReview.objects.filter(
            post__seeker=seeker, is_completed=True
        )
        
        context = {
            'seeker': seeker,
            'posts': posts,
            'reviews': reviews,
            'avg_rating': round(
                sum(r.rating for r in reviews) / reviews.count(), 1
            ) if reviews.count() > 0 else None,
            'verified_count': posts.filter(
                client_review__is_completed=True
            ).count(),
        }
        return render(request, 'public_portfolio.html', context)


class HiringMarketplaceView(View):
    """
    Standalone marketplace for hiring seekers.
    Publicly accessible.
    """
    def get(self, request):
        category = request.GET.get('category')
        lga = request.GET.get('lga')
        search = request.GET.get('search')
        
        seekers = OjaUser.objects.filter(role__in=['seeker', 'both']).order_by('-ojapass_score')
        
        if category:
            seekers = seekers.filter(trade_category__icontains=category)
        if lga:
            seekers = seekers.filter(lga__icontains=lga)
        if search:
            from django.db.models import Q
            seekers = seekers.filter(
                Q(full_name__icontains=search) | 
                Q(skills__icontains=search) | 
                Q(bio__icontains=search)
            )
            
        context = {
            'seekers': seekers,
            'categories': ['Creative & Design', 'Tech & IT', 'Logistics & Delivery', 'Beauty & Fashion', 'Domestic Services', 'Construction', 'Other'],
            'lgas': ['Surulere', 'Ikeja', 'Lekki', 'Victoria Island', 'Yaba'],
        }
        return render(request, 'hiring_marketplace.html', context)


class ReviewRequestView(View):
    """
    Public page where a client leaves a review.
    No account needed — just the token link.
    """
    def get(self, request, token):
        post = get_object_or_404(PortfolioPost, review_token=token)
        
        # Check if already reviewed
        if hasattr(post, 'client_review') and post.client_review.is_completed:
            return render(request, 'review_already_done.html', {'post': post})
        
        return render(request, 'leave_review.html', {'post': post})

    def post(self, request, token):
        post = get_object_or_404(PortfolioPost, review_token=token)
        
        # Prevent duplicate reviews
        if hasattr(post, 'client_review') and post.client_review.is_completed:
            return JsonResponse(
                {"success": False, "message": "This job has already been reviewed."},
                status=400
            )
        
        data = json.loads(request.body)
        rating = int(data.get('rating', 0))
        
        if not 1 <= rating <= 5:
            return JsonResponse(
                {"success": False, "message": "Rating must be between 1 and 5."},
                status=400
            )
        
        review, created = ClientReview.objects.get_or_create(
            post=post,
            defaults={
                'rating': rating,
                'comment': data.get('comment', ''),
                'reviewer_name': data.get('reviewerName', 'Anonymous Client'),
                'reviewer_phone': data.get('reviewerPhone', ''),
                'is_completed': True,
            }
        )
        
        if not created:
            # Review existed but wasn't completed — complete it now
            review.rating = rating
            review.comment = data.get('comment', '')
            review.reviewer_name = data.get('reviewerName', 'Anonymous Client')
            review.is_completed = True
            review.save()
        
        # Notify seeker
        Notification.objects.create(
            user=post.seeker,
            message=f"NEW REVIEW: {review.reviewer_name} left you a {rating}★ review for '{post.title}'!"
        )
        
        # Recalculate OjaScore
        recalculate_ojascore(post.seeker.id)
        
        return JsonResponse({
            "success": True,
            "message": f"Thank you! Your {rating}★ review has been submitted.",
        })


class ReviewShareView(LoginRequiredMixin, View):
    """Generate the shareable review link for a post"""
    def get(self, request, post_id):
        post = get_object_or_404(PortfolioPost, id=post_id, seeker=request.user)
        
        review_url = request.build_absolute_uri(
            f"/portfolio/review/{post.review_token}/"
        )
        
        whatsapp_msg = (
            f"Hi {post.client_name}, I recently completed '{post.title}' for you. "
            f"I'd appreciate if you could rate my work on OjaPass: {review_url}"
        )
        
        return JsonResponse({
            "success": True,
            "reviewUrl": review_url,
            "whatsappUrl": f"https://wa.me/?text={whatsapp_msg}",
            "message": "Share this link with your client to collect a review."
        })