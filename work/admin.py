from django.contrib import admin
from .models import WorkRequest, WorkRequestResponse, WorkProposal, Conversation, Message


@admin.register(WorkRequest)
class WorkRequestAdmin(admin.ModelAdmin):
    list_display = ('id', 'created_by', 'assigned_to', 'payment_amount', 'status', 'created_at')
    list_filter = ('status',)
    search_fields = ('description', 'created_by__username', 'assigned_to__username')
    ordering = ('-created_at',)


@admin.register(WorkRequestResponse)
class WorkRequestResponseAdmin(admin.ModelAdmin):
    list_display = ('id', 'user', 'work_request', 'status', 'created_at')
    list_filter = ('status',)
    search_fields = ('user__username',)


@admin.register(WorkProposal)
class WorkProposalAdmin(admin.ModelAdmin):
    list_display = ('id', 'sender', 'receiver', 'status', 'created_at')
    list_filter = ('status',)
    search_fields = ('sender__username', 'receiver__username')


@admin.register(Conversation)
class ConversationAdmin(admin.ModelAdmin):
    list_display = ('id', 'conversation_type', 'created_at')
    list_filter = ('conversation_type',)


@admin.register(Message)
class MessageAdmin(admin.ModelAdmin):
    """Read sparingly and only for genuine safety investigations — these are
    private messages between users."""
    list_display = ('id', 'sender', 'conversation', 'text', 'created_at')
    search_fields = ('sender__username', 'text')
    ordering = ('-created_at',)
