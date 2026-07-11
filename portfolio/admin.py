from django.contrib import admin
from .models import PortfolioItem, Media, Reaction, Comment


@admin.register(PortfolioItem)
class PortfolioItemAdmin(admin.ModelAdmin):
    list_display = ('id', 'title', 'user', 'portfolio_type', 'verified', 'created_at')
    list_filter = ('portfolio_type', 'verified')
    search_fields = ('title', 'description', 'user__username')
    ordering = ('-created_at',)


@admin.register(Comment)
class CommentAdmin(admin.ModelAdmin):
    list_display = ('id', 'user', 'portfolio_item', 'text', 'created_at')
    search_fields = ('user__username', 'text')
    ordering = ('-created_at',)


admin.site.register(Media)
admin.site.register(Reaction)
