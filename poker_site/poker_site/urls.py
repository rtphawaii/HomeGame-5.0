from django.contrib import admin
from django.urls import path
from core import views as core_views  # gate + lobby
from poker import views as poker_views # room

urlpatterns = [
    path('admin/', admin.site.urls),

    # Password gate
    path('gate/', core_views.gate_view, name='gate'),
    path('gate/lock/', core_views.gate_lock, name='gate_lock'),
    path('gate/health/', core_views.gate_health, name='gate_health'),

    # Lobby (choose or create room)
    path('', core_views.lobby_view, name='lobby'),

    # A specific game room (reuses your index.html UI)
    path('room/<slug:room_name>/', poker_views.room_view, name='room'),
    
    # Optional restart endpoint you already referenced
    path('restart/', core_views.restart_view, name='restart'),
]
