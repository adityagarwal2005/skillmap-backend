from django.contrib import admin
from .models import Category, Skill, Tag, UserSkill, Certificate


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ('id', 'name')
    search_fields = ('name',)


@admin.register(Skill)
class SkillAdmin(admin.ModelAdmin):
    list_display = ('id', 'name', 'category')
    list_filter = ('category',)
    search_fields = ('name',)


admin.site.register(Tag)
admin.site.register(UserSkill)
admin.site.register(Certificate)
