from django.shortcuts import render
import uuid
from django.http import JsonResponse
from .consumers import ChatConsumer


try:
    import pokerlib
    print("✅ pokerlib imported")
except ModuleNotFoundError:
    print("❌ still broken")

def index(request):
    user_id = str(uuid.uuid4())  # generate random user ID
    return render(request, 'poker/index.html', {'user_id': user_id})

def restart_app(request):
    # Clear all global game states
    ChatConsumer.players.clear()
    ChatConsumer.pending_inputs.clear()
    ChatConsumer.pending_inputs_all.clear()
    ChatConsumer.game_started = False
    ChatConsumer.player_count = None
    return JsonResponse({"status": "ok"})

from django.shortcuts import render, redirect
from django.urls import reverse

def room_view(request, room_name: str):
    # Enforce gate
    if not request.session.get("passed_gate"):
        return redirect(f"{reverse('gate')}?next={request.path}")

    user_id = request.session.get("user_id")
    if not user_id:
        # Should have been created in lobby, but backfill if someone deep-links
        import uuid
        user_id = uuid.uuid4().hex
        request.session["user_id"] = user_id

    return render(request, "poker/index.html", {"user_id": user_id, "room_name": room_name})
