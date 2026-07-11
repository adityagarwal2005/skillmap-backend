from django.contrib import admin
from .models import CollabPost, CollabRequest


@admin.register(CollabPost)
class CollabPostAdmin(admin.ModelAdmin):
    list_display = ('id', 'title', 'user', 'status', 'created_at')
    list_filter = ('status',)
    search_fields = ('title', 'description', 'user__username')
    ordering = ('-created_at',)


@admin.register(CollabRequest)
class CollabRequestAdmin(admin.ModelAdmin):
    list_display = ('id', 'applicant', 'collab_post', 'status', 'created_at')
    list_filter = ('status',)
    search_fields = ('applicant__username', 'collab_post__title')
