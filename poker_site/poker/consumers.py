from channels.generic.websocket import AsyncWebsocketConsumer
import json
import random
from .HomeGame import run_game
import asyncio
from decimal import Decimal, InvalidOperation

#Notes
#environments open: (env)(base)
#daphne poker_site.asgi:application

ROOMS = {}  # room_name -> {
#   "players": {user_id: consumer},
#   "pending_inputs": {user_id: Future},
#   "pending_inputs_all": {"awaiting all": Future},
#   "player_count": int|None,
#   "game_started": bool,
#   "table": Table|None
# }
def room_state(name: str):
    if name not in ROOMS:
        ROOMS[name] = {
            "players": {},
            "pending_inputs": {},
            "pending_inputs_all": {},
            "player_count": None,
            "game_started": False,
            "table": None,
            "cancel_event": asyncio.Event(),   # ⬅️ new
            "game_task": None,                 # ⬅️ new
        }
    return ROOMS[name]

def clear_all_rooms():
    """
    Completely clear all rooms, players, and game states.
    """
    for room in list(ROOMS.keys()):
        state = ROOMS[room]
        # Cancel any running game tasks
        cancel_event = state.get("cancel_event")
        if cancel_event:
            cancel_event.set()
        task = state.get("game_task")
        if task and not task.done():
            task.cancel()
        # Clear pending inputs and futures
        for fut in list(state.get("pending_inputs", {}).values()):
            if not fut.done():
                fut.set_result("cancelled")
        if "pending_inputs_all" in state:
            fut_all = state["pending_inputs_all"].pop("awaiting all", None)
            if fut_all and not fut_all.done():
                fut_all.set_result("cancelled")
    ROOMS.clear()
    print("♻️ All rooms cleared.")
    return True


class ChatConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.room_name = self.scope["url_route"]["kwargs"]["room_name"]
        self.group_name = f"chat_{self.room_name}"

        #MODIFIED ALL-IN
        from urllib.parse import parse_qs
        qs = parse_qs(self.scope.get("query_string", b"").decode("utf-8"))
        self.user_id = (qs.get("user_id") or [""])[0]
        print(f"✅ CONNECT user_id={self.user_id} room={self.room_name}")

        self.state = room_state(self.room_name)

        # Register player in this room
        self.state["players"][self.user_id] = self

        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()
        print(f"✅ CONNECT {self.user_id} → room {self.room_name} (players={list(self.state['players'])})")
        await self.send(text_data=json.dumps({"debug_user_id": self.user_id}))


        # Only first connector prompts for player_count
        if self.state["player_count"] is None and not self.state["pending_inputs"]:
            asyncio.create_task(self.prompt_player_count())

        if (not self.state["game_started"]
            and self.state["player_count"] is not None
            and len(self.state["players"]) == self.state["player_count"]):
            self.state["game_started"] = True
            self.state["cancel_event"].clear()
            self.state["game_task"] = asyncio.create_task(
                run_game(list(self.state["players"].keys()),
                        self,
                        smallblind=.10, bigblind=.10,
                        room_name=self.room_name,
                        cancel_event=self.state["cancel_event"])  # ⬅️ pass it through
            )

            await self.broadcast_system(f"🎮 Game started in {self.room_name} — players: {len(self.state['players'])}")

    async def disconnect(self, code):
        await self.channel_layer.group_discard(self.group_name, self.channel_name)
        self.state["players"].pop(self.user_id, None)
        print(f"❌ DISCONNECT {self.user_id} from {self.room_name} (code {code})")

    # group helpers
    async def chat_message(self, event):
        await self.send(text_data=json.dumps({'message': event['message']}))

    async def broadcast_system(self, msg):
        for player in self.state["players"].values():
            await player.send(text_data=json.dumps({'message': f'[SYSTEM]: {msg}'}))

    # ↓↓↓ replace every ChatConsumer.<dict> access with self.state[...] ↓↓↓
    # pending_inputs / pending_inputs_all / players / player_count / game_started

    async def prompt_player_count(self):
        while True:
            try:
                input_value = await self.get_input(self.user_id, f'🎲 Enter number of players for room "{self.room_name}":')
                self.state["player_count"] = int(input_value)
                if self.state["player_count"] in (None, 1) or self.state["player_count"] > 22:
                    self.state["player_count"] = None
                    raise ValueError

                # Clear futures
                for _uid, fut in list(self.state["pending_inputs"].items()):
                    if not fut.done():
                        fut.set_result('player count done')
                self.state["pending_inputs"].clear()

                await self.broadcast_system(f"🔢 Player count set to {self.state['player_count']}")
                break
            except ValueError:
                await self.send_to_user(self.user_id, '❌ Invalid entry. Please enter an integer between 2 and 22.')

    async def receive(self, text_data):
        data = json.loads(text_data)
        msg_type = data.get("type")

        # --- Control messages ---
        if msg_type == "control":
            cmd = data.get("cmd")
            if cmd == "restart_game":
                await self._restart_room(relaunch=True)
                return
            if cmd == "start_new_round":
                fut = self.state.get("pending_inputs_all", {}).pop("awaiting all", None)
                if fut and not fut.done():
                    fut.set_result("start new round")
                return

        if msg_type == "add_balance":
            target_user_id = (data.get("target_user_id") or self.user_id)
            raw_amount = data.get("amount")
            if raw_amount is None or not getattr(self, "table", None):
                print("[WARN] add_balance: missing amount or no table bound")
                return

            # Normalize amount
            try:
                amount = float(raw_amount)
            except Exception:
                print(f"[WARN] add_balance bad amount={raw_amount!r} from {getattr(self, 'user_id', '')[:5]}")
                return

            if amount <= 0:
                print(f"[WARN] add_balance non-positive amount={amount} from {getattr(self, 'user_id', '')[:5]}")
                return

            # Lookup player (exact → base-id fallback)
            pid = str(target_user_id)
            player = self.table.get_player(pid)
            if not player and "-" in pid:
                base = pid.split("-", 1)[0]
                player = self.table.get_player(base)
                if player:
                    print(f"[INFO] add_balance: resolved {pid!r} → base {base!r}")

            if not player:
                print(f"[WARN] add_balance: unknown player {pid!r}")
                # Optional: tell the sender
                try:
                    await self.send_to_user(self.user_id, f"❌ Can't find player for id {pid!r}")
                except Exception:
                    pass
                return

            try:
                await player.add_balance(amount)
                await self.broadcast_system(f"💵 {player.name} added ${amount:.2f}")
            except Exception as e:
                print(f"[ERROR] add_balance failed for {pid!r}: {e}")
            return



        # === Regular chat / numeric input ===
        msg = data.get("message")
        if msg is None:
            return
        
        print(f"[receive] from {self.user_id[:5]} msg={msg!r} "
      f"pending_keys={list(self.state['pending_inputs'].keys())} "
      f"group_waiting={'awaiting all' in self.state.get('pending_inputs_all', {})}")

        # 1) Resolve per-user future FIRST (betting input)
        fut = self.state["pending_inputs"].pop(self.user_id, None)
        if fut and not fut.done():
            fut.set_result(msg)
            return

        # 2) Then resolve any group future (“start new round”)
        fut_all = self.state.get("pending_inputs_all", {}).pop("awaiting all", None)
        if fut_all and not fut_all.done():
            fut_all.set_result(msg)
            return

        # 3) Otherwise broadcast
        await self.channel_layer.group_send(
            self.group_name,
            {"type": "chat_message", "message": f"{self.user_id[:5]}: {msg}"},
        )


    # async def send_to_user(self, user_id, message):
    #     player = self.state["players"].get(user_id)
    #     if player:
    #         await player.send(text_data=json.dumps({'message': message}))
    #         print('sent to player')

    # MANAGE ALL-IN
    async def send_to_user(self, user_id, message):
        player = self.state["players"].get(user_id)
        if not player:
            return
        if isinstance(message, dict):
            # send raw JSON (control signals like your_turn/turn_end)
            await player.send(text_data=json.dumps(message))
        else:
            # send chat-style text
            await player.send(text_data=json.dumps({'message': message}))



    async def send_player_info(self, user_id, message):
        player = self.state["players"].get(user_id)
        if player:
            await player.send(text_data=json.dumps(message))

    async def send_info_all(self, message):
        for _uid, player in self.state["players"].items():
            await player.send(text_data=json.dumps(message))


    async def get_input(self, user_id, prompt, cancel_event=None):
        print(f"[get_input] -> set pending for {user_id!r}")
        await self.send_to_user(user_id, prompt)
        fut = asyncio.Future()
        self.state["pending_inputs"][user_id] = fut
        if cancel_event is None:
            res = await fut
            self.state["pending_inputs"].pop(user_id, None)
            return res
        done, _ = await asyncio.wait({fut, cancel_event.wait()}, return_when=asyncio.FIRST_COMPLETED)
        self.state["pending_inputs"].pop(user_id, None)
        if cancel_event.is_set():
            raise asyncio.CancelledError
        return fut.result()

    async def get_input_all(self, prompt, cancel_event=None):
        await self.broadcast_system(prompt)
        fut = asyncio.Future()
        self.state["pending_inputs_all"]["awaiting all"] = fut
        if cancel_event is None:
            res = await fut
            self.state["pending_inputs_all"].pop("awaiting all", None)
            return res
        done, _ = await asyncio.wait({fut, cancel_event.wait()}, return_when=asyncio.FIRST_COMPLETED)
        self.state["pending_inputs_all"].pop("awaiting all", None)
        if cancel_event.is_set():
            raise asyncio.CancelledError
        return fut.result()


    async def _restart_room(self, *, relaunch: bool = True):
        state = self.state

        # 1) Trip cancel & cancel the running task once
        if "cancel_event" not in state:
            state["cancel_event"] = asyncio.Event()
        state["cancel_event"].set()

        task = state.get("game_task")
        if task and not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

        # 2) Resolve/clear any outstanding futures
        for _, fut in list(state.get("pending_inputs", {}).items()):
            if not fut.done():
                fut.set_result("cancelled")
        state["pending_inputs"].clear()
        fut_all = state.get("pending_inputs_all", {}).pop("awaiting all", None)
        if fut_all and not fut_all.done():
            fut_all.set_result("cancelled")

        # 3) Drop table and flags
        state["table"] = None
        self.table = None
        state["game_started"] = False

        # 4) Tell all clients to wipe their UI
        await self.broadcast_system("🔄 Game reset.")
        await self.send_info_all({"reset": True})
        await self.send_info_all({"board": {"board": "Waiting for cards..."}})
        await self.send_info_all({"pot": {"pot": 0}})
        await self.send_info_all({"bet": {"amount": 0}})

        # 5) Recreate cancel_event for next run
        state["cancel_event"] = asyncio.Event()

        # 6) Relaunch run_game so the prompt returns
        if relaunch:
            from .HomeGame import run_game  # local import to avoid cycles
            player_ids = list(state["players"].keys())
            if player_ids:
                state["game_started"] = True
                state["game_task"] = asyncio.create_task(
                    run_game(
                        player_ids,
                        self,
                        smallblind=.10,
                        bigblind=.10,
                        room_name=self.room_name,
                        cancel_event=state["cancel_event"],
                    )
                )
                await self.broadcast_system("✅ Ready. Type **start new round** or press the button.")

    

