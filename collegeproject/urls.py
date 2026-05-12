from django.contrib import admin
from django.urls import path
from main import views

from django.conf import settings
from django.conf.urls.static import static

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', views.home),
    path('story/', views.story, name='story'),
    path('generate/', views.generate, name='generate'),
]

# 👇 MEDIA serve karne ke liye (LAST me likhna hai)
urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)