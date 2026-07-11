from django.contrib import admin
from .models import (
    User, StudentProfile, OTPVerification, Block,
    SkillEndorsement, PushSubscription, Report,
)


@admin.register(User)
class UserAdmin(admin.ModelAdmin):
    list_display = ('id', 'username', 'email', 'category', 'status', 'rating', 'created_at')
    list_filter = ('status', 'category')
    search_fields = ('username', 'email')
    ordering = ('-created_at',)


@admin.register(Report)
class ReportAdmin(admin.ModelAdmin):
    """The moderation inbox — every report a user submits lands here.
    'Block reported user' lets you act on a report in one click without
    needing to separately look up and block the account."""
    list_display = ('id', 'reporter', 'report_type', 'reported_target', 'reason', 'created_at')
    list_filter = ('report_type', 'reason', 'created_at')
    search_fields = ('reporter__username', 'reported_user__username', 'details')
    ordering = ('-created_at',)
    actions = ['block_reported_user']

    @admin.display(description='Reported')
    def reported_target(self, obj):
        return obj.reported_user.username if obj.reported_user else f"post #{obj.reported_post_id}"

    @admin.action(description="Block the reported user (for the reporter)")
    def block_reported_user(self, request, queryset):
        created = 0
        for report in queryset:
            if report.reported_user:
                _, was_created = Block.objects.get_or_create(
                    blocker=report.reporter, blocked=report.reported_user
                )
                created += int(was_created)
        self.message_user(request, f"Created {created} block(s).")


@admin.register(Block)
class BlockAdmin(admin.ModelAdmin):
    list_display = ('id', 'blocker', 'blocked', 'created_at')
    search_fields = ('blocker__username', 'blocked__username')


@admin.register(StudentProfile)
class StudentProfileAdmin(admin.ModelAdmin):
    list_display = ('id', 'user', 'education_type', 'degree_name', 'current_year')
    search_fields = ('user__username',)


admin.site.register(OTPVerification)
admin.site.register(SkillEndorsement)
admin.site.register(PushSubscription)
