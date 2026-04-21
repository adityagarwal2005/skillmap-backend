"""
URL configuration for social project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/6.0/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import path
from django.views.decorators.csrf import csrf_exempt
from django.conf import settings
from django.conf.urls.static import static

from users import views as user_views
from skills import views as skill_views
from work import views as work_views
from portfolio import views as portfolio_views
from notifications import views as notification_views
from reviews import views as review_views

from feed import views as feed_views
from collab import views as collab_views


urlpatterns = [
    path("admin/", admin.site.urls),

    # Auth
    path("users/register/", csrf_exempt(user_views.register)),
    path("users/login/", csrf_exempt(user_views.login)),
    path("users/token/refresh/", csrf_exempt(user_views.refresh_token)),
    path("users/status/update/", csrf_exempt(user_views.update_status)),

    # Users
    path("users/search/", csrf_exempt(user_views.search_users)),
    path("users/<int:user_id>/", csrf_exempt(user_views.get_user)),
    path("users/<int:user_id>/edit/", csrf_exempt(user_views.edit_user)),
    path("users/<int:user_id>/delete/", csrf_exempt(user_views.delete_user)),

    # Collab
    path("collab/", csrf_exempt(collab_views.show_collab_posts)),
    path("collab/create/", csrf_exempt(collab_views.create_collab_post)),
    path("collab/mine/", csrf_exempt(collab_views.show_my_collab_posts)),
    path("collab/<int:post_id>/apply/", csrf_exempt(collab_views.apply_to_collab)),
    path("collab/<int:post_id>/applicants/", csrf_exempt(collab_views.get_collab_applicants)),
    path("collab/<int:post_id>/close/", csrf_exempt(collab_views.close_collab_post)),
    path("collab/requests/<int:request_id>/respond/", csrf_exempt(collab_views.respond_to_collab_request)),


    # Feed
    path("feed/", csrf_exempt(feed_views.smart_feed)),
    path("feed/search/", csrf_exempt(feed_views.search_feed)),
    path("feed/trending/", csrf_exempt(feed_views.trending_feed)),

    # Student Profile
    path("users/<int:user_id>/student-profile/", csrf_exempt(user_views.get_student_profile)),
    path("users/<int:user_id>/student-profile/add/", csrf_exempt(user_views.add_student_profile)),
    path("users/<int:user_id>/student-profile/edit/", csrf_exempt(user_views.edit_student_profile)),

    # Skills
    path("users/<int:user_id>/skills/add/", csrf_exempt(skill_views.add_skill)),
    path("users/<int:user_id>/skills/remove/", csrf_exempt(skill_views.remove_skill)),

    # Certificates
    path("certificates/add/", csrf_exempt(skill_views.add_certificate)),
    path("certificates/<int:certificate_id>/remove/", csrf_exempt(skill_views.remove_certificate)),
    path("users/<int:user_id>/certificates/", csrf_exempt(skill_views.show_certificates)),

    # Categories
    path("categories/", csrf_exempt(skill_views.show_categories)),
    path("categories/add/", csrf_exempt(skill_views.add_category)),
    path("categories/<int:category_id>/skills/", csrf_exempt(skill_views.get_category_skills)),

    # Portfolio
    path("portfolio/", csrf_exempt(portfolio_views.show_portfolio_items)),
    path("portfolio/create/", csrf_exempt(portfolio_views.create_portfolio_item)),
    path("portfolio/user/<int:user_id>/", csrf_exempt(portfolio_views.show_user_portfolio)),
    path("portfolio/<int:item_id>/comments/", csrf_exempt(portfolio_views.show_item_comments)),
    path("portfolio/<int:item_id>/react/", csrf_exempt(portfolio_views.react_to_item)),
    path("portfolio/<int:item_id>/edit/", csrf_exempt(portfolio_views.edit_portfolio_item)),
    path("portfolio/<int:item_id>/delete/", csrf_exempt(portfolio_views.delete_portfolio_item)),
    path("portfolio/<int:item_id>/comment/", csrf_exempt(portfolio_views.add_comment)),
    path("portfolio/<int:item_id>/media/add/", csrf_exempt(portfolio_views.add_media)),
    path("portfolio/comments/<int:comment_id>/edit/", csrf_exempt(portfolio_views.edit_comment)),
    path("portfolio/comments/<int:comment_id>/remove/", csrf_exempt(portfolio_views.remove_comment)),

    # Work Requests
    path("work/requests/create/", csrf_exempt(work_views.create_work_request)),
    path("work/requests/user/<int:user_id>/", csrf_exempt(work_views.get_my_work_requests)),
    path("work/requests/available/<int:user_id>/", csrf_exempt(work_views.get_available_work_requests)),
    path("work/requests/<int:work_request_id>/respond/", csrf_exempt(work_views.respond_to_work_request)),
    path("work/requests/<int:work_request_id>/responses/", csrf_exempt(work_views.get_work_request_responses)),
    path("work/requests/<int:work_request_id>/assign/", csrf_exempt(work_views.assign_work_request)),
    path("work/requests/<int:work_request_id>/close/", csrf_exempt(work_views.close_work_request)),

    # Work Proposals
    path("work/proposals/send/<int:receiver_id>/", csrf_exempt(work_views.send_work_proposal)),
    path("work/proposals/<int:proposal_id>/respond/", csrf_exempt(work_views.respond_to_work_proposal)),
    path("work/proposals/mine/", csrf_exempt(work_views.get_my_proposals)),

    # Conversations & Messages
    path("conversations/", csrf_exempt(work_views.get_my_conversations)),
    path("conversations/<int:conversation_id>/send/", csrf_exempt(work_views.send_message)),
    path("conversations/<int:conversation_id>/messages/", csrf_exempt(work_views.get_messages)),

    # Notifications
    path("notifications/", csrf_exempt(notification_views.get_my_notifications)),
    path("notifications/unread/", csrf_exempt(notification_views.get_unread_count)),
    path("notifications/read-all/", csrf_exempt(notification_views.mark_all_as_read)),
    path("notifications/<int:notification_id>/read/", csrf_exempt(notification_views.mark_as_read)),

    # Reviews
    path("reviews/user/<int:reviewee_id>/add/", csrf_exempt(review_views.add_review)),
    path("reviews/user/<int:user_id>/", csrf_exempt(review_views.get_user_reviews)),

] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)