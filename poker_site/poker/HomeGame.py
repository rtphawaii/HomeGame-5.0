import sys
sys.path.append('../pokerlib')

from argparse import ArgumentParser
from pokerlib import Player, PlayerSeats
from pokerlib import Table
from pokerlib import HandParser as HandParser
from pokerlib.enums import Rank, Suit
from collections import OrderedDict, defaultdict
from decimal import Decimal, ROUND_HALF_UP, getcontext
import random
import copy

#UPDATES AND FIXES NEEDED:

#UPDATE 1
#must fix all-in scenarios where one player is out of balance
#in an all-in scenario the player without balance is forced to fold if another player bets
#this is not ideal and instead it should skip their action, carve out a side pot, and let the action carry on for other players

#UPDATE 2 - Done
# need to deduct small and big blinds from players

#UPDATE 3 - Done
# need to fix order updating for new rounds

#UPDATE 4A - Done
# need to fix current bet and hand score

#UPDATE 4B
# need to fix subtraction of blinds at start of round from player balances

#UPDATE 4C - Done
# need to reset universal bet box each betting round

#UPDATE 4D - Done
# fix evaluation, pot is not awarded to the winner and the player balances arent working

#UPDATE 5
# need to notify small and big blinds that they are already in for their blinds

#UPDATE 6 
# need to deploy to a hosted website using AWS EC2

#UPDATE 7 
# does not work with only 2 players 

#UPDATE 8 - Done
# New betting box that tracks current bets

#UPDATE 9 - Done
# Cards stored in static/cards/ now render on the board and in the players hand

#UPDATE 10 - Done
# Button for adding to player balance, update balance after

#UPDATE 11 - Done
# Pot live update while players are betting - pot calc and pot update when call or raise 

#UPDATE 11B - Done
# Fixed folding action where players receive pot twice after everyone folds

#UPDATE 11C - Done
# Fixed start new round function where betting wasn't working

#UPDATE 12 - Done
# Make the chat button press by pressing enter key 

#UPDATE 13 - Done
# Make game rooms for each websocket 

#UPDATE 13B - Done
# Make it mobile friendly using @media, vertical stack and anchor restart button to bottom

#UPDATE 13C - Done
# Can now play with two players, added position() function and modified preflop Round() and bets() 

#Update 13D - Done
# fixed mobile and desktop add balance issues

#UPDATE 13E - Done
# add message for when player raises
# remove redundant system messages, removed pot update messages, removed 'now dealing' (flop, turn, river) 

#UPDATE 13F - Done
# all-in button
# PROGRESS -> the game is broken and not letting the initial bidding take place. After dealing cards the game fails.
# PROGRESS 2 -> seems to be working locally, try to deploy and test
# PROGRESS 3 -> needs testing, partially works
# PROGRESS 3 -> breaks when a short stacked player goes all-in and the bigger stack player subsequently goes all-in
# BACKUP -> Google Drive HomeGame 5.3 

#UPDATE 13G - Done
# fix raise loop where raiser gets action again

#UPDATE 13H - Testing
# fix add balance glitch where when one player adds balance another cannot afterward

#UPDATE 14 
# For each time you send or maybe receive add to a game ledger, feed the entire ledger joined with separators to an open ai api and spit back a summary of the game play

from decimal import Decimal, ROUND_HALF_UP, getcontext
getcontext().prec = 28

EPS = Decimal("0.0000001")  # tiny epsilon for Decimal compares
CENT = Decimal("0.01")

def _money(x) -> Decimal:
    """Coerce to Decimal with 2dp."""
    if isinstance(x, Decimal):
        return x.quantize(CENT)
    return Decimal(str(x)).quantize(CENT)

def _to_float(d: Decimal) -> float:
    return float(d.quantize(CENT))


class Table():
    def __init__(self,smallblind,bigblind,input,output,send_to_user,send_player_info,send_info_all):
        self.list=[]
        self.perma_list=[]
        self.players_by_id = {}
        self.order=[]
        self.startingorder=[]
        self.pot = Decimal("0.00")
        self.smallblind=smallblind
        self.bigblind=bigblind
        self.currentprice=self.bigblind
        self.bet=[]
        self.board=[]
        self.deck=[]
        self.rank=[]
        self.preflop=True
        self.rivercheck=False
        self.gameover=False
        self.round=1
        self.all_in=[]
        self.output=output
        self.input=input
        self.send_to_user=send_to_user
        self.send_player_info=send_player_info
        self.send_info_all=send_info_all
        self.contributed=defaultdict(Decimal)
    def createdeck(self):
        '''create the deck'''
        self.deck = [(rank, suit) for rank in Rank for suit in Suit]
        self.shuffledeck()
    def shuffledeck(self):
        random.shuffle(self.deck)

    async def addplayer(self, player):
        '''add a player to the game'''
        print(f'table is adding {player}')
        self.list.append(player)
        self.perma_list.append(player)
        self.players_by_id[str(player.player_id)] = player   # ✅ index by string key
        await self.send_to_user(player.player_id, f"you are {player}")

    def pickdealer(self):
        '''pick a dealer'''
        self.order=self.list
        random.shuffle(self.order)
        return self.order[0].name

    def deal(self):
        '''deal hands'''
        for x in self.list:
            x.hand.append(self.deck.pop())
            x.hand.append(self.deck.pop())
    
    def _iter_seats(self, start_idx: int, end_idx: int):
        """Yield seats from start_idx up to (but not including) end_idx, wrapping once."""
        n = len(self.order)
        i = start_idx % n
        stop = end_idx % n
        while True:
            yield self.order[i]
            if i == (stop - 1) % n:    # stop right before end_idx
                break
            i = (i + 1) % n
    
    CENT = Decimal("0.01")

    @staticmethod
    def _money(x):
        return Decimal(str(x)).quantize(Table.CENT, rounding=ROUND_HALF_UP)

    def _apply_delta(self, player, delta_dec: Decimal) -> Decimal:
        """Apply a chip delta in Decimal to all ledgers + UI list."""
        delta_dec = _money(delta_dec)
        if delta_dec <= Decimal("0.00"):
            return Decimal("0.00")

        # Decimal ledgers
        self.contributed[player] += delta_dec
        self.pot += delta_dec
        player.balance = _to_float(_money(player.balance) - delta_dec)  # keep balance as float for UI

        # UI history expects floats (your bet_info_update reads self.bet[-1][-1])
        self.bet.append((player, _to_float(delta_dec)))
        return delta_dec
    

    async def flop(self):
        '''deals flop'''
        print('flop')
        #await self.output(f"now dealing the flop...")
        #burn one card
        self.deck.pop()
        #deal 3 cards to the board
        self.board.append(self.deck.pop())
        self.board.append(self.deck.pop())
        self.board.append(self.deck.pop())
        print(self.board)
        rank1, suit1 = self.board[0]
        rank2, suit2 = self.board[1]
        rank3, suit3 = self.board[2]
        await self.output(f"the flop is: {rank1.name} of {suit1.name}, {rank2.name} of {suit2.name}, {rank3.name} of {suit3.name}")

        #send the update to the board
        board_flop=f"{rank1.name} of {suit1.name}, {rank2.name} of {suit2.name}, {rank3.name} of {suit3.name}"
        await self.send_info_all({
                "board": {
                    'board':board_flop
                }})
        
        #update handscores
        await self.update_handscore()

    async def turn(self):
        '''deals turn'''
        print('turn')
        #await self.output(f"now dealing the turn...")
        #burn one card
        self.deck.pop()
        #deal 1 card to the board
        self.board.append(self.deck.pop())
        print(self.board)
        rank1, suit1 = self.board[0]
        rank2, suit2 = self.board[1]
        rank3, suit3 = self.board[2]
        rank4, suit4 = self.board[3]
        await self.output(f"the turn is: {rank1.name} of {suit1.name}, {rank2.name} of {suit2.name}, {rank3.name} of {suit3.name}, {rank4.name} of {suit4.name}")

        #send the update to the board
        board_turn=f"{rank1.name} of {suit1.name}, {rank2.name} of {suit2.name}, {rank3.name} of {suit3.name}, {rank4.name} of {suit4.name}"
        await self.send_info_all({
                "board": {
                    'board':board_turn
                }})
        
        #update hand score
        await self.update_handscore()
        
    async def river(self):
        '''deals river'''
        print('~river')
        #await self.output(f"now dealing the river...")
        #burn one card
        self.deck.pop()
        #deal 1 card to the board
        self.board.append(self.deck.pop())
        print(self.board)
        rank1, suit1 = self.board[0]
        rank2, suit2 = self.board[1]
        rank3, suit3 = self.board[2]
        rank4, suit4 = self.board[3]
        rank5, suit5 = self.board[4]
        print(rank5.name,suit5.name)
        await self.output(f"the river is: {rank1.name} of {suit1.name}, {rank2.name} of {suit2.name}, {rank3.name} of {suit3.name}, {rank4.name} of {suit4.name}, {rank5.name} of {suit5.name}")

        #send the update to the board
        board_river=f"{rank1.name} of {suit1.name}, {rank2.name} of {suit2.name}, {rank3.name} of {suit3.name}, {rank4.name} of {suit4.name}, {rank5.name} of {suit5.name}"
        await self.send_info_all({
                "board": {
                    'board':board_river
                }})
        
        #update hand score
        await self.update_handscore()

    def get_player(self, player_id: str):
        pid = str(player_id)
        # fast path via index
        p = self.players_by_id.get(pid)
        if p:
            return p
        # fallback scan (in case something wasn’t indexed yet)
        for p in self.perma_list:
            if str(p.player_id) == pid:
                # backfill the index for next time
                self.players_by_id[pid] = p
                return p
        for p in self.list:
            if str(p.player_id) == pid:
                self.players_by_id[pid] = p
                return p
        return None
    
    def positions(self):
        """
        Returns (dealer_idx, sb_idx, bb_idx) for current self.order.
        Heads-up: dealer IS small blind; other player is big blind.
        3+ players: dealer at 0, SB at 1, BB at 2 (as before).
        """
        n = len(self.order)
        if n < 2:
            raise RuntimeError("Not enough players to compute positions")

        dealer_idx = 0
        if n == 2:
            sb_idx = dealer_idx
            bb_idx = (dealer_idx + 1) % n
        else:
            sb_idx = (dealer_idx + 1) % n
            bb_idx = (dealer_idx + 2) % n
        return dealer_idx, sb_idx, bb_idx


    # async def bets(self,preflop=False):
    #     '''betting mechanism'''
    #     print('betting started')
    #     #start collecting the first round of bets starting from next to the big blind
    #     raise_offset=1

    #     #reset currentbet
    #     for player in self.perma_list:
    #         player.currentbet=0
        
    #     #reset bet box if it is new betting round post flop
    #     if preflop==False:
    #         await self.bet_info_update(new_bets=True)
    #     else:
    #         await self.bet_info_update(blinds_start=True)


    #     #find the big blind index in self.order
    #     if self.preflop==True:
            
    #         #find the player that is big blind
    #         player_to_find = self.bet[-1][0]
    #         found_index = None
    #         for index, player in enumerate(self.order):
    #             if player == player_to_find:
    #                 found_index = index
    #                 #the action starts one player after the big blind if there has not been a straddle
    #                 found_index+=1
    #                 #set an endpoint, the betting should end before reaching the end index based on the loop parameters
    #                 end_index=found_index
    #                 break
    #     else:
    #         #when it is post flop,river, turn, action starts after the dealer and ends on the dealer
    #         #self.bet=[(self.list[-1],0)]
    #         found_index=1
    #         end_index=1
    #     #once the index of the big blind player is found, loop around starting from the person next to them
    #     if found_index is not None:
    #         print('found_index is defined')
    #         #everything should be in a while loop that resets betting if someone raises
    #         continue_loop = True
    #         while continue_loop:
    #                 #continue through the betting process as normal unless someone raises
    #                 continue_loop=False
    #                 print('enter first while loop')
    #                 #betting loop starts
    #                 print(self.order[found_index:])
    #                 print(self.order[:end_index])
    #                 for offset,player in enumerate(self.order[found_index:] + self.order[:end_index]):
    #                     print('player betting: ', player)
    #                     #betting ends if everyone has folded except for one player 
    #                     if len(self.order)<=1:
    #                         continue_loop=False
    #                         return

    #                     # if the player is all-in, skip betting for that player 
    #                     if player in self.all_in:
    #                         await self.output(f'{player} is all-in and has no action')
    #                         continue

    #                     #a player needs to place a valid bet that is a fold, call, check, or raise
    #                     while True:
    #                         print('second while loop for individual betting enter')
    #                         playerbet = await player.placebet(self.bet[-1][1])  # Wait for the player to place a bet
    #                         print('placebet called', player)

    #                         if playerbet == -1 or playerbet == self.bet[-1][1] or playerbet > self.bet[-1][1]:
    #                             print('valid bet - loop break and evaluate')
    #                             await self.output(f'{player} bets {playerbet}')
    #                             break  # Valid bet, exit the loop
    #                         else:
    #                             print("Invalid bet. Please enter another bet.")
    #                             await self.send_to_user(player.player_id, '❌ Invalid bet. Please enter another bet.')


    #                     #remove the player from the order if they fold
    #                     if playerbet==-1:
    #                         index = self.order.index(player)
    #                         self.order.pop(index)
    #                         print('fold by', player)
    #                         await self.output(f"{player} has folded")
    #                     #player raises, evaluate bets for everyone again starting from the next player around to the player that raises
    #                     elif playerbet>self.bet[-1][1]:
    #                         #add the bet to the betting log
    #                         self.bet.append((player,playerbet))

    #                         #update the current bet display
    #                         await self.bet_info_update()

    #                         #update current bet
    #                         player.currentbet=playerbet
    #                         await self.player_info_update_all()

    #                         #the player object that raised and needs to be found
    #                         player_to_find = self.bet[-1][0]
    #                         #find the index of the player that raised
    #                         for index, player in enumerate(self.order):
    #                             if player == player_to_find:
    #                                 found_index = index
    #                                 found_index+=1
    #                         #end the betting action on the person before the person that is raising 
    #                         end_index=found_index-1
    #                         print('raise')
    #                         raise_offset=0
    #                         continue_loop=True

    #                         break  # Break out of the loop to restart (enter the start of the first while loop)
    #                     else:
    #                         #if the bet is a call then it is simply added and we move to the next better
    #                         self.bet.append((player,playerbet))
    #                         print(f'{player} calls the bet of {playerbet}')

    #                         #update current bet
    #                         player.currentbet=playerbet
    #                         await self.player_info_update_all()


    #                         await self.output(f'{player} calls the bet of {playerbet}')

    async def bets(self, preflop: bool = False):
        """Betting mechanism (Decimal-safe, short-all-in aware)."""
        print('betting started')

        if self.cancel_event and self.cancel_event.is_set():
            raise asyncio.CancelledError

        # Reset per-street meters
        for p in self.perma_list:
            if not preflop or (p is not getattr(self, "small_blind_player", None) and
                            p is not getattr(self, "big_blind_player", None)):
                p.currentbet = 0.0

        # Street target (float for UI, Decimal for math)
        if preflop:
            self.round_to = float(self.bigblind)
            if hasattr(self, "small_blind_player"):
                self.small_blind_player.currentbet = float(self.smallblind)
            if hasattr(self, "big_blind_player"):
                self.big_blind_player.currentbet = float(self.bigblind)
            await self.bet_info_update(blinds_start=True)
        else:
            self.round_to = 0.0
            await self.bet_info_update(new_bets=True)

        # Find starting index
        n = len(self.order)
        dealer_idx, sb_idx, bb_idx = self.positions()
        if preflop:
            found_index = (bb_idx + 1) % n
            end_index   = found_index
        else:
            found_index = (dealer_idx + 1) % n
            end_index   = found_index

        if found_index is None:
            return

        continue_loop = True
        while continue_loop:
            if self.cancel_event and self.cancel_event.is_set():
                raise asyncio.CancelledError

            continue_loop = False

            restart = False  # 🔹 will break the for-loop when a raise occurs
            seats = list(self._iter_seats(found_index, end_index))
            # iterate seats once; may restart if someone raises
            for player in seats:
                # hand ended by folds
                if len(self.order) <= 1:
                    return

                # no action for all-in players
                if player in self.all_in:
                    await self.output(f'{player} is all-in and has no action')
                    continue

                # --- solicit a valid action ---
                while True:
                    if self.cancel_event and self.cancel_event.is_set():
                        raise asyncio.CancelledError

                    # current street target (Decimal for comparisons)
                    target_dec = _money(self.round_to)

                    # let UI know it's their turn
                    await self.send_to_user(player.player_id, {"action": "your_turn", "target": float(target_dec)})

                    raw = await player.placebet(float(target_dec), cancel_event=self.cancel_event)
                    print(f"[bets] recv raw={raw!r} from {player.name} target={target_dec} "f"curbet={player.currentbet} bal={player.balance}")

                    # normalize to Decimal and allow "-1" fold
                    try:
                        playerbet_dec = _money(raw)
                    except Exception:
                        if str(raw).strip() == "-1":
                            playerbet_dec = Decimal("-1")
                        else:
                            await self.send_to_user(player.player_id, '❌ Invalid bet. Please enter another bet.')
                            continue

                    # FOLD
                    if playerbet_dec == Decimal("-1"):
                        self.order.remove(player)
                        await self.send_to_user(player.player_id, {"action": "turn_end"})
                        await self.output(f"{player} has folded")
                        if len(self.order) == 1:
                            self.gameover = True
                            return "hand_over"
                        break  # out of inner while; go to next player

                    # legal cap “to” this street = currentbet + balance
                    current_to_dec = _money(player.currentbet)
                    balance_dec    = _money(player.balance)
                    allowed_to     = current_to_dec + balance_dec

                    # clamp the requested TO amount
                    bet_to = playerbet_dec if playerbet_dec <= allowed_to else allowed_to

                    # how many new chips now (delta)?
                    delta = bet_to - current_to_dec

                    # nothing added and not an exact check -> invalid
                    if delta <= Decimal("0.00") and bet_to != target_dec:
                        await self.send_to_user(player.player_id, '❌ Invalid bet. Please enter another bet.')
                        continue

                    # apply the delta to ledgers (Decimal) and update UI meters
                    if delta > Decimal("0.00"):
                        self._apply_delta(player, delta)
                        player.currentbet = _to_float(bet_to)
                        await self.pot_info_update()
                        await self.player_info_update_all()
                        await self.bet_info_update()
                    else:
                        # check / already-in (no chips added)
                        player.currentbet = _to_float(bet_to)

                    # flag all-in if they hit their cap
                    if abs(bet_to - allowed_to) <= EPS and player not in self.all_in:
                        self.all_in.append(player)
                        await self.output(f"{player.name} is ALL-IN for {bet_to:.2f}")

                    # ---- decide outcome: raise / call / short-call / check / already-in ----
                    round_to_dec = _money(self.round_to)

                    # Genuine raise only if they exceed current street target
                    if bet_to > round_to_dec + EPS:
                        self.round_to = float(bet_to)
                        await self.output(f'{player} raises to {self.round_to}')
                        await self.send_to_user(player.player_id, {"action": "turn_end"})

                        # restart from seat after raiser
                        raiser_idx = next(i for i, p2 in enumerate(self.order) if p2 is player)
                        found_index = (raiser_idx + 1) % len(self.order)

                        # heads-up: end on the raiser so they do NOT act again
                        if len(self.order) == 2:
                            end_index = raiser_idx
                        else:
                            # multiway: typical behavior—action closes when it comes back to the raiser
                            end_index = raiser_idx

                        continue_loop = True
                        restart = True
                        break

                    # Not a raise:
                    if round_to_dec <= EPS:
                        # price == 0 → check
                        await self.output(f'{player} checks')
                        await self.send_to_user(player.player_id, {"action": "turn_end"})
                        break

                    # Positive price:
                    if abs(_money(player.currentbet) - round_to_dec) <= EPS:
                        # exactly matched the price
                        if delta <= EPS:
                            # added nothing now
                            if balance_dec > EPS:
                                await self.output(f'{player} is already in for {self.round_to}')
                            else:
                                await self.output(f'{player} is all-in and has no action')
                        else:
                            await self.output(f'{player} calls to {self.round_to}')
                        await self.send_to_user(player.player_id, {"action": "turn_end"})
                        break

                    # short all-in (can’t cover full call)
                    if bet_to + EPS < round_to_dec:
                        await self.output(f'{player} is all-in short for {bet_to:.2f} (cannot cover full call)')
                        await self.send_to_user(player.player_id, {"action": "turn_end"})
                        break
                    


                    # fallback (shouldn’t hit)
                    await self.output(f'{player} action registered')
                    await self.send_to_user(player.player_id, {"action": "turn_end"})
                    break  # end inner while; move to next player
                if restart:
                    break
            if not restart:
                return "street_done"
            if not restart:
                return  


    # async def evaluate(self):
    #     '''determine winner and give pot'''

    #     #if everyone else has folded, award the winner
    #     if len(self.order)==1:
    #         self.order[0].balance+=self.pot
    #         print(f'everyone else folded... {self.order[0].name} wins {self.pot}')
    #         await self.output(f"everyone else folded... {self.order[0].name} wins {self.pot}")
    #         return
    
    #     #add each hand to hands
    #     hands=[]
    #     for x in self.order:
    #         x.hand=HandParser(x.hand)
    #         x.hand+=self.board
    #         hands.append((x,x.hand))

    #     #evaluate the best hand and player
    #     max_player = max(hands, key=lambda x: x[1])
    #     winner_index = hands.index(max_player)
    #     winners = []  # List to store players with the maximum hand value
    #     # Iterate through handlist excluding the winner_index
    #     winners.append(max_player[0])

    #     #check to see if there are any other winners
    #     for index, (player, hand) in enumerate(hands):
    #         if index != winner_index:
    #             if hand == max_player[1]:
    #                 winners.append(player)

    #     #if the winner is all-in add the side pot to their balance and subtract it from the pot
    #     #all-in -> if all-in wins they should win a side pot 
    #     for winner in winners:
    #         sidepot=0
    #         if winner in self.all_in:
    #             for player,bet in self.bet:
    #                 if player==winner:
    #                     winner.balance+=bet
    #                     sidepot+=bet
    #                     self.pot-=bet
    #                     winners.remove(winner)
    #                     await self.output(f'{winner} wins a side pot of {sidepot} with hand {str(winner.hand.handenum)}')
        
    #     #if there is one winner add the pot to their balance
    #     if len(winners)==1:
    #         winners[0].balance+=self.pot
    #         print(f'{winners[0].name} wins {self.pot}','with',winners[0].hand.handenum)
    #         await self.output(f"{winners[0].name} wins {self.pot}, with, {str(winners[0].hand.handenum)}")
    #     #if there is more than one winner split the pot between them
    #     else:
    #         for x in winners:
    #             print(x, 'wins with:',x.handscore)
    #             await self.output(f"{x} wins with: {x.handscore}")
    #             x.balance+=self.pot/len(winners)

    async def evaluate(self):
        print('EVALUATE')

        # 1) If only one player remains -> instant win (fold-out)
        if len(self.order) == 1:
            winner = self.order[0]
            self._add_to_balance(winner, _money(self.pot))
            await self.output(f"everyone else folded... {winner.name} wins {float(self.pot):.2f}")
            self.pot = Decimal("0.00")
            await self.player_info_update_all()
            return

        # ---------- Parse hands WITHOUT mutating player.hand ----------
        board = list(self.board)
        results = []  # list[(player, hp)]
        for player in self.order:
            hole = list(player.hand)               # copy
            hp = HandParser(hole + board)          # eval on fresh snapshot
            player.hand_forscore = hp              # optional: keep for UI/debug
            player.handscore = hp.handenum.name
            results.append((player, hp))

        # ---------- Tie handling helpers ----------
        def hands_equal(a, b):
            return not (a > b) and not (b > a)

        def tier_results_with_ties(pairs):
            """
            pairs: list[(player, hp)]
            returns: list[list[(player, hp)]]  # tiers; each inner list is a tie group
            """
            pool = {p: hp for p, hp in pairs}
            tiers = []
            while pool:
                # find best in pool
                best_p, best_hp = next(iter(pool.items()))
                for p, hp in pool.items():
                    if hp > best_hp:
                        best_p, best_hp = p, hp
                # collect ties with best
                tied = [(p, hp) for p, hp in list(pool.items()) if hands_equal(hp, best_hp)]
                tiers.append(tied)
                for p, _ in tied:
                    del pool[p]
            return tiers

        ranked_tiers = tier_results_with_ties(results)  # best tier first
        seat_index = {p: i for i, p in enumerate(self.order)}  # deterministic remainders

        # ---------- Build pots correctly from total contributions ----------
        bets_by_player = dict(self.contributed)  # {player: Decimal total_contributed}
        print('[EVAL] contributed:', {p.name: float(a) for p, a in bets_by_player.items()})

        # money helpers (Decimal-safe)
        getcontext().prec = 28
        CENT = Decimal("0.01")

        def money(x) -> Decimal:
            if isinstance(x, Decimal):
                return x.quantize(CENT, rounding=ROUND_HALF_UP)
            return Decimal(str(x)).quantize(CENT, rounding=ROUND_HALF_UP)

        def split_even(amount: Decimal, n: int):
            total_cents = int((amount / CENT).to_integral_value(rounding=ROUND_HALF_UP))
            q, r = divmod(total_cents, n)
            return [(Decimal(q + (1 if i < r else 0)) * CENT) for i in range(n)]

        def build_side_pots(bets_by_player, active_players):
            """
            Canonical side-pot construction using contribution caps.
            Returns: list[(pot_amount: Decimal, eligible_set: set(player))]
            """
            contrib = {p: money(a) for p, a in bets_by_player.items() if money(a) > 0}
            if not contrib:
                return []

            levels = sorted(set(contrib.values()))
            actives = set(active_players)

            def capped_sum(cap):
                return sum(min(a, cap) for a in contrib.values())

            pots, prev = [], Decimal("0.00")
            for cap in levels:
                layer_amount = money(capped_sum(cap) - capped_sum(prev))
                if layer_amount > 0:
                    elig = {p for p, a in contrib.items() if a >= cap} & actives
                    if elig:
                        pots.append((layer_amount, elig))
                prev = cap
            return pots

        pots = build_side_pots(bets_by_player, self.order)
        print('[EVAL] pots:', [(float(a), {p.name for p in s}) for a, s in pots])

        # ---------- Award pots (tier-aware, Decimal-safe) ----------
        for pot_amount, elig in pots:
            pot_amount = money(pot_amount)
            if pot_amount <= 0 or not elig:
                continue

            # Find the best eligible tier (highest hand among elig set)
            winners = None
            for tier in ranked_tiers:  # best → worse
                tier_players = [p for (p, _hp) in tier if p in elig]
                if tier_players:
                    winners = tier_players
                    break
            if not winners:
                # No eligible winners (shouldn't happen if elig non-empty)
                continue

            winners_sorted = sorted(winners, key=lambda p: seat_index.get(p, 0))

            if len(winners_sorted) == 1:
                # ✅ Single winner takes THIS pot_amount
                w = winners_sorted[0]
                self._add_to_balance(w, pot_amount)
                await self.output(f"{w.name} wins {float(pot_amount):.2f}")
                continue

            # Tie: split into exact cents
            shares = split_even(pot_amount, len(winners_sorted))
            for share, p in zip(shares, winners_sorted):
                self._add_to_balance(p, share)

            names = " & ".join(p.name for p in winners_sorted)
            if len(set(shares)) == 1:
                await self.output(f"{names} split {float(pot_amount):.2f} ({float(shares[0]):.2f} each)")
            else:
                await self.output(
                    f"{names} split {float(pot_amount):.2f} "
                    f"({', '.join(f'{float(s):.2f}' for s in shares)})"
                )

        # ---------- Cleanup & broadcast AFTER paying ----------
        self.pot = Decimal("0.00")
        self.all_in.clear()
        self.round_to = 0
        self.bet.clear()
        self.contributed.clear()  # start next hand fresh
        for pl in self.perma_list:
            pl.currentbet = 0.0

        await self.pot_info_update()
        await self.bet_info_update(new_bets=True)
        await self.player_info_update_all()

        print("[ALL-IN STATUS]", [p.name for p in self.all_in])
        print("[BETS]", [(p.name, b) for p, b in self.bet])
        print("[POTS BUILT]", [(float(a), {p.name for p in s}) for a, s in pots])


    async def evaluate_original(self):
        '''Determine winner(s), split main/side pots, and award balances'''
        if len(self.order) == 1:
            # Everyone else folded
            winner = self.order[0]
            winner.balance += self.pot
            print(f'everyone else folded... {winner.name} wins {self.pot}')
            await self.output(f"everyone else folded... {winner.name} wins {self.pot}")
            self.pot = 0
            return

        # --- Parse hands ---
        hands = []
        for player in self.order:
            player.hand = HandParser(player.hand)
            player.hand += self.board
            hands.append((player, player.hand))
        print('!!!', hands)

        # Sort hands best to worst
        hands.sort(key=lambda x: x[1], reverse=True)

        print('!!!', hands)

        # --- Total contributions for the whole hand (built as deltas during betting) ---
        bets_by_player = dict(self.contributed)   # e.g., {playerA: 140, playerB: 60, ...}
        print('!!! totals', bets_by_player)

        # --- Create side pots ---
        sorted_players = sorted(bets_by_player.items(), key=lambda x: x[1])
        pots = []  # List of tuples: (pot_amount, eligible_players)
        prev_amount = 0
        remaining_players = list(bets_by_player.keys())

        for player, amount in sorted_players:
            diff = amount - prev_amount
            if diff > 0:
                pot_amount = diff * len(remaining_players)
                pots.append((pot_amount, remaining_players.copy()))
                prev_amount = amount
            remaining_players.remove(player)
        
        print('!!!!!', pots)

        # --- Award pots ---
        total_distributed = 0
        for pot_amount, eligible_players in pots:
            # Find best hand among eligible players
            best_hand = None
            winners = []

            for player, hand in hands:
                if player in eligible_players:
                    if best_hand is None:
                        best_hand = hand
                        winners = [player]
                    elif hand == best_hand:
                        winners.append(player)
                    else:
                        break  # lower hands, ignore

            # Split the pot among winners
            split = pot_amount / len(winners)
            for winner in winners:
                for player in self.list:
                    if player.name == winner.name:  # match actual object
                        player.balance += split
                        await self.output(f"{player.name} wins ${split:.2f} from pot with {str(winner.hand.handenum)}")
                        break

            total_distributed += pot_amount

        # Sanity check: all pot money should be distributed
        self.pot -= total_distributed
        if self.pot > 0.01:
            print(f"⚠️ Warning: ${self.pot:.2f} remaining in pot after distribution")
        self.pot = 0  # reset for next round

        self.pot = 0

        #reset after awarding pot
        self.bet.clear()
        self.contributed.clear()
        for p in self.perma_list:
            p.currentbet = 0
        await self.player_info_update_all()



    async def fold_check(self):
        if len(self.order)==1:
            # self.order[0].balance+=self.pot
            print(f'everyone else folded... {self.order[0].name} wins {self.pot}')
            await self.output(f"everyone else folded... {self.order[0].name} wins {self.pot}")
            self.gameover=True
  
        
    def potcalc(self):
        #takes the latest bets from each player unless the player bet then folded
        latest_bets = {}
        print(self.bet)

        #go through the list of bets in reverse
        for player, bet in reversed(self.bet):
            if player not in latest_bets and bet != -1:
                latest_bets[player] = bet
            elif player not in latest_bets:
                latest_bets[player] = 0
            elif bet != -1:
                continue  # Skip if player already has a non-negative bet
            elif latest_bets[player] != -1:
                latest_bets[player] = 0  # Treat -1 bet as 0 if there's no previous non-negative bet
            #subtract the latest bet for each player from their balance
            print('subtracting bet from balance')
            player.balance-=latest_bets[player]
            print(player,player.balance)
        
        #if all the latest bets are greater than or equal to big blind then the two blinds have bet or checked
        if all(value >= self.bigblind for value in latest_bets.values()) and self.preflop==True:
            #remove small blind and big blind bets
            self.bet.pop(0)
            self.bet.pop(1)
            print('preflop bets list after removing blinds:',self.bet)

        print(latest_bets)
        sum_pot=sum(value for value in latest_bets.values())
        print('potcalc sum_pot: ',sum_pot)
        return sum_pot
    
    def _add_to_balance(self, player, amount_dec: Decimal):
        player.balance = _to_float(_money(player.balance) + _money(amount_dec))

    async def pot_info_update(self):
        await self.send_info_all({
            "pot": {
                "pot": float(self.pot)  # ← cast to float
            }
        })
    
    async def bet_info_update(self, blinds_start=False, new_bets=False):
        if blinds_start:
            await self.send_info_all({"bet": {"amount": float(self.bigblind)}})
            return
        if new_bets:
            await self.send_info_all({"bet": {"amount": 0.0}})
            return
        if self.bet:
            last = float(self.bet[-1][-1])  # ✅ ensure JSON-serializable
            await self.send_info_all({"bet": {"amount": last}})

    
    async def player_info_update(self):
        for player in self.order:
            print(f"Sending stats to {player.player_id}:", player.balance)

            hand_pairs = []
            if len(player.hand) >= 2:
                (rank1, suit1), (rank2, suit2) = player.hand[:2]
                hand_pairs = [(rank1.name, suit1.name), (rank2.name, suit2.name)]

            await self.send_player_info(player.player_id, {
                "player": {
                    "user_id": player.player_id,
                    "name": player.name,
                    "balance": float(player.balance),
                    "currentbet": float(player.currentbet),
                    "handscore": getattr(player, "handscore", None),
                    "hand": hand_pairs,
                }
            })


    async def player_info_update_all(self):
        for player in self.perma_list:
            print(f"Sending stats to {player.player_id}:", player.balance)

            hand_pairs = []
            if len(player.hand) >= 2:
                (rank1, suit1), (rank2, suit2) = player.hand[:2]
                hand_pairs = [(rank1.name, suit1.name), (rank2.name, suit2.name)]

            await self.send_player_info(player.player_id, {
                "player": {
                    "user_id": player.player_id,
                    "name": player.name,
                    "balance": float(player.balance),
                    "currentbet": float(player.currentbet),
                    "handscore": getattr(player, "handscore", None),
                    "hand": hand_pairs,
                }
            })


    async def update_handscore(self):
        for player in self.perma_list:
            # player.hand_forscore=None
            # player.handscore=None
            # player.hand_forscore = HandParser(player.hand)
            # player.hand_forscore += self.board
            # player.handscore=player.hand_forscore.handenum.name

            # 1) Build a fresh snapshot; never pass references you might mutate later
            hole = list(player.hand)      # copy
            board = list(self.board)      # copy
            seven = hole + board          # 2 to 7 cards, depending on street

            # 2) Create a NEW parser on the combined snapshot
            hp = HandParser(seven)
            player.hand_forscore = hp
            player.handscore = hp.handenum.name

            await self.player_info_update_all()


    async def Round(self,bet=0):
        if self.cancel_event and self.cancel_event.is_set():
            raise asyncio.CancelledError

        print('round enter')
        # --- per-hand reset ---
        self.gameover = False
        self.pot = Decimal("0.00")
        self.bet = []
        self.contributed = defaultdict(Decimal)
        self.board = []
        self.preflop = True
        self.rivercheck = False
        self.all_in = []

        # per-hand resets:
        st = getattr(self, "send_info_all", None)
        # access via consumer.state if you keep a ref there
        if hasattr(self, "send_to_user"):  # we have the consumer bound
            try:
                # clear any leftover "awaiting all" so it can't eat bets
                self.input.__self__.state["pending_inputs_all"].pop("awaiting all", None)
            except Exception:
                pass

        # refresh active players list (keep everyone with chips)
        self.list = [p for p in self.perma_list if not getattr(p, "out_of_balance", False) and p.balance > 0]

        # seed/rotate order BEFORE dealing
        if not getattr(self, "startingorder", []):
            # first hand in a match: pick dealer & freeze starting order
            self.pickdealer()
            self.startingorder = self.order[:]  # snapshot
        else:
            # subsequent hands: rotate against startingorder + round counter
            if getattr(self, "round", None) is None:
                self.round = 1
            n = (self.round - 1) % len(self.startingorder)
            self.order = self.startingorder[n:] + self.startingorder[:n]

        # safety: if order accidentally collapsed last hand, repopulate from startingorder
        if len(self.order) < len(self.list):
            # Re-synchronize order with active players while preserving rotation
            active_ids = {p.player_id for p in self.list}
            self.order = [p for p in self.order if p.player_id in active_ids]
            # append any missing active players in startingorder order
            for p in self.startingorder:
                if p.player_id in active_ids and p not in self.order:
                    self.order.append(p)

        # still not enough players? bail gracefully
        if len(self.order) < 2:
            await self.output("Not enough players to continue.")
            return

        if self.cancel_event and self.cancel_event.is_set():
                raise asyncio.CancelledError
        
        await self.output("Game round begins")
        print(self.list)

        #remove player from game if they are out of balance
        for player in self.list[:]:  # iterate over a copy
            if player.balance == 0:
                player.out_of_balance = True
                self.list.remove(player)

        #reset hands
        for x in self.list:
            x.hand=[]
        if self.round==1:
            #pick a dealer
            self.pickdealer()
            print('dealer picked')
            self.startingorder=copy.copy(self.order)
        print(self.order)
        await self.output(f"{self.order[0]} is the dealer - the order is {self.order}")
        #create a new deck
        self.createdeck()
        #shuffle the deck
        self.shuffledeck()
        #deal each player 2 cards 
        self.deal()
        for player in self.order:
            print(player.hand)
            print(type(player.hand[0][0]))
            rank1, suit1 = player.hand[0]
            rank2, suit2 = player.hand[1]
            msg = f"your hand is {rank1.name} of {suit1.name}, {rank2.name} of {suit2.name}"
            await self.send_to_user(player.player_id, msg)

        #sends an update to player info
        await self.player_info_update()

        #update hand score
        await self.update_handscore()
        
        #preflop
        # at the start of the hand (before posting blinds)
        self.contributed.clear()
        self.bet.clear()
        self.pot = 0

        # ... after dealing, before preflop betting ...
        dealer_idx, sb_idx, bb_idx = self.positions()
        sbp = self.order[sb_idx]
        bbp = self.order[bb_idx]

        # Post blinds using Decimal-safe helper
        sb_amt = _money(self.smallblind)
        bb_amt = _money(self.bigblind)

        self._apply_delta(sbp, sb_amt)  # logs (player, delta), bumps pot, contributed, balance
        self._apply_delta(bbp, bb_amt)

        # UI-facing per-street meters remain floats
        sbp.currentbet = _to_float(sb_amt)
        bbp.currentbet = _to_float(bb_amt)
        self.round_to = _to_float(bb_amt)

        # Remember who posted blinds (bets() reads these safely)
        self.small_blind_player = sbp
        self.big_blind_player   = bbp

        await self.pot_info_update()
        await self.bet_info_update(blinds_start=True)


        #reset
        if self.cancel_event and self.cancel_event.is_set():
                raise asyncio.CancelledError

        # Preflop betting begins vs target == BB (bets() will set self.round_to accordingly)
        res = await self.bets(preflop=True)
        if res == "hand_over" or self.gameover:
            await self.pot_info_update()          # optional: refresh UI before paying
            await self.player_info_update_all()   # optional
            await self.evaluate()                 # ✅ pay once here
            # ✅ rotate for the NEXT hand now
            self.round = getattr(self, "round", 1) + 1
            n = (self.round - 1) % len(self.startingorder)
            self.order = self.startingorder[n:] + self.startingorder[:n]
            return

        print('after preflop betting loop these players remain: ',self.list)

        #calculate the pot for preflop
        #self.pot=self.potcalc()
        print('pot is: ',self.pot)
        print('preflop betting list: ',self.bet)

        #send pot info
        await self.pot_info_update()
        await self.player_info_update_all()


        await self.fold_check()
        
        if self.gameover==False:
            if self.cancel_event and self.cancel_event.is_set():
                raise asyncio.CancelledError

            #flop
            await self.flop()
            self.preflop=False

            if self.cancel_event and self.cancel_event.is_set():
                raise asyncio.CancelledError

            #self.bet=[]
            res = await self.bets()
            if res == "hand_over" or self.gameover:
                await self.pot_info_update()
                await self.player_info_update_all()
                await self.evaluate()
                self.round = getattr(self, "round", 1) + 1
                n = (self.round - 1) % len(self.startingorder)
                self.order = self.startingorder[n:] + self.startingorder[:n]                
                return
            print(self.bet)

            #sends an update to player info
            await self.player_info_update()

            #self.pot+=self.potcalc()
            print('pot:',self.pot)
            await self.output(f"the pot is: {self.pot}")

            #send pot info
            await self.pot_info_update()
            await self.player_info_update()

            await self.fold_check()
        if self.gameover==False:
            #turn

            if self.cancel_event and self.cancel_event.is_set():
                raise asyncio.CancelledError
            
            await self.turn()
            self.preflop=False

            if self.cancel_event and self.cancel_event.is_set():
                raise asyncio.CancelledError
            
            #self.bet=[]
            res = await self.bets()
            if res == "hand_over" or self.gameover:
                await self.pot_info_update()
                await self.player_info_update_all()
                await self.evaluate()
                self.round = getattr(self, "round", 1) + 1
                n = (self.round - 1) % len(self.startingorder)
                self.order = self.startingorder[n:] + self.startingorder[:n]
                return

            #sends an update to player info
            await self.player_info_update()

            print(self.bet)
            #self.pot+=self.potcalc()
            print('pot:',self.pot)
            await self.output(f"the pot is: {self.pot}")

            #send pot info
            await self.pot_info_update()
            await self.player_info_update()

            await self.fold_check()
        if self.gameover==False:
            if self.cancel_event and self.cancel_event.is_set():
                raise asyncio.CancelledError
            #river
            await self.river()
            self.preflop=False

            if self.cancel_event and self.cancel_event.is_set():
                raise asyncio.CancelledError

            #self.bet=[]
            res = await self.bets()
            if res == "hand_over" or self.gameover:
                await self.pot_info_update()
                await self.player_info_update_all()
                await self.evaluate()
                self.round = getattr(self, "round", 1) + 1
                n = (self.round - 1) % len(self.startingorder)
                self.order = self.startingorder[n:] + self.startingorder[:n]
                return
            print(self.bet)

            #sends an update to player info
            await self.player_info_update()

            #self.pot+=self.potcalc()
            print('pot:',self.pot)
            await self.output(f"the pot is: {self.pot}")

            #send pot info
            await self.pot_info_update()
            await self.player_info_update()

            self.rivercheck=True

            if self.cancel_event and self.cancel_event.is_set():
                raise asyncio.CancelledError
            
            await self.fold_check()
            await self.evaluate()
            await self.send_info_all({"action": "hand_over"})

        #changed from list to order 
        for x in self.order:
            print(x,'  ','balance:',x.balance)
            await self.output(f"{x} has the balance: {x.balance}")
            print(x, x.hand)
            #fails here on second round of game specifically for players that fold - has to do with evaluate
            #print(x.hand.cards)
            # readable_cards = [f"{rank.name} of {suit.name}" for rank, suit in x.hand]
            # print(x.hand.handenum)
            # await self.output(f"{x} has a {str(x.hand.handenum.name)} with the cards {', '.join(readable_cards)}")
            # hole & board snapshots (copies to avoid aliasing)
            hole  = list(x.hand)          # [('SEVEN','DIAMOND'), ('QUEEN','SPADE')] via enums
            board = list(self.board)      # 0..5 board cards

            # parser for scoring (7-card eval when board is complete enough)
            hp = HandParser(hole + board)

            # readable strings — choose what you want to show:
            hole_readable  = [f"{r.name} of {s.name}" for r, s in hole]
            board_readable = [f"{r.name} of {s.name}" for r, s in board]
            all_readable   = hole_readable + board_readable

            score_name = hp.handenum.name  # e.g., "TWO_PAIR", "FLUSH", etc.

            # If x is a player object, use x.name (str(x) may be an object repr)
            await self.output(
                f"{x.name} has a {score_name} with the cards {', '.join(all_readable)}"
            )

        for x in self.list:
            #reset hand for next round
            x.hand=[]
            print(f'hand reset for {x}')
        
        #sends an update to player info
        for player in self.list:
            print(f"Sending stats to {player.player_id}:", player.balance)
            await self.send_player_info(player.player_id, {
                "player": {
                    "name": player.name,
                    "balance": player.balance,
                    "currentbet": player.currentbet,
                    "handscore": player.handscore,
                    "hand": ['']
                }
            })
            print(f'info update sent to player {player}')
        
        # #reset variables for next round
        # self.order=[]
        # self.pot=0
        # self.currentprice=self.bigblind
        # self.bet=[]
        # self.board=[]
        # self.deck=[]
        # self.rank=[]
        # self.preflop=True
        self.rivercheck=False

        #reset pot
        await self.pot_info_update()

        #reset board
        await self.send_info_all({
                "board": {
                    'board':'new round'
                }})


        #change order for next round
        self.round+=1
        self.gameover=False

        #rotate button clockwise and wrap
        n = (self.round - 1) % len(self.startingorder)
        self.order = self.startingorder[n:] + self.startingorder[:n]






        
class Player():
    def __init__(self,player_id,balance,table):
        self.player_id=player_id
        self.balance=balance
        self.out_of_balance=False
        self.hand=[]
        #need to fix currentbet
        self.currentbet=0
        #need to fix handscore
        self.handscore=None
        self.hand_forscore=None
        self.table=table
        self.name=f'player #{self.player_id[:5]}'

    def __repr__(self):
        return (f'{self.name}')
    
    # MANAGE ALL-IN
    async def placebet(self, current_price, valid=True, cancel_event=None):
        print(f"[placebet] prompt for {self.player_id[:5]} target={current_price} bal={self.balance} curbet={self.currentbet}")
        while True:
            raw = await self.table.input(
                self.player_id,
                f'{self.name}, price is {current_price}, place your bet (0 for check, -1 for fold): ',
                cancel_event=cancel_event
            )

            # --- interpret ALL-IN keyword(s) ---
            if isinstance(raw, str) and raw.strip().lower() in ("all-in", "all in", "allin"):
                # RETURN A TO-PRICE, NOT THE REMAINING AMOUNT
                to_price = float(self.currentbet) + float(self.balance)
                if self not in self.table.all_in:
                    self.table.all_in.append(self)
                await self.table.output(f"{self.name} goes ALL-IN for {self.balance}")
                return to_price  # <-- was: return float(self.balance)

            # --- otherwise parse numeric ---
            try:
                bet = float(raw)
            except (TypeError, ValueError):
                await self.table.send_to_user(self.player_id, "❌ Invalid input. Enter a number, -1 to fold, or 'all-in'.")
                continue

            if bet < -1:
                await self.table.send_to_user(self.player_id, "❌ Invalid bet.")
                continue

            # If they typed exactly their remaining amount, treat that as ALL-IN TO-PRICE as well.
            # (Prevents ‘short’ all-in when they already have chips in this street.)
            if abs(bet - float(self.balance)) < 1e-9:
                to_price = float(self.currentbet) + float(self.balance)
                if self not in self.table.all_in:
                    self.table.all_in.append(self)
                await self.table.output(f"{self.name} goes ALL-IN for {self.balance}")
                return to_price  # <-- was: return bet

            if bet > float(self.balance):
                await self.table.send_to_user(self.player_id, "❌ Bet exceeds your balance.")
                continue

            return bet


    # async def placebet(self, current_price, valid=True, cancel_event=None):
    #     print("[DEBUG] Prompting player:", self.player_id)
    #     '''place a bet'''
    #     if valid == False:
    #         while True:
    #             try:
    #                 print('placebet enter invalid bet attempted')
    #                 bet = float(await self.table.input(self.player_id,f'{self.name}, price is {current_price}, place your bet (0 for check, -1 for fold): ', cancel_event=cancel_event))
    #                 if bet <= self.balance:  # Check if bet is within balance

    #                     #MODIFIED FOR ALL-IN
    #                     if bet==self.balance:
    #                         self.table.all_in.append(self)
    #                         print(f'{self} is now all-in')
    #                     #working on all-in

    #                     return bet
    #                 else:
    #                     await self.table.send_to_user(self.player_id,"Invalid bet. Bet exceeds balance.")
    #             except ValueError:
    #                 await self.table.send_to_user(self.player_id,"Invalid input. Please enter a valid number.")
    #     else:
    #         while True:
    #             print('placebet enter')
    #             try:
    #                 print('placebet valid input')
    #                 bet = float(await self.table.input(self.player_id,f'{self.name}, price is {current_price}, place your bet (0 for check, -1 for fold): ',cancel_event=cancel_event))
    #                 print('placebet valid done')
    #                 if bet <= self.balance:  # Check if bet is within balance
    #                     print('bet: ',bet)

    #                     #working on all-in 
    #                     if bet == self.balance:
    #                         self.table.all_in.append(self)
    #                         await self.table.output(f"{self.name} is all-in for {bet}")
    #                         return bet
    #                     #working on all-in
                        
    #                     return bet
    #                 else:
    #                     await self.table.send_to_user(self.player_id,"Invalid bet. Bet exceeds balance.")
    #             except ValueError:
    #                 await self.table.send_to_user(self.player_id,"Invalid input. Please enter a valid number.")

    async def add_balance(self, amount):
        try:
            inc = _money(amount)  # Decimal-safe
        except (ValueError, TypeError, InvalidOperation):
            return

        # add safely and keep UI float
        self.balance = _to_float(_money(self.balance) + inc)

        # if they were marked out, revive them for the NEXT hand
        if self.out_of_balance and self.balance > 0:
            self.out_of_balance = False

        # notify clients
        await self.table.player_info_update_all()
        await self.table.send_to_user(
            self.player_id,
            f"💵 Added {float(inc):.2f}. New balance: {float(self.balance):.2f}"
        )

import asyncio
async def run_game(player_ids, consumer, smallblind=.10, bigblind=.10, room_name=None, cancel_event=None):
    table = Table(
        smallblind, bigblind,
        output=consumer.broadcast_system,
        input=consumer.get_input,          # supports cancel_event
        send_to_user=consumer.send_to_user,
        send_player_info=consumer.send_player_info,
        send_info_all=consumer.send_info_all,
    )
    table.cancel_event = cancel_event

    for pid in player_ids:
        player = Player(player_id=pid, balance=20, table=table)
        await table.addplayer(player)

    consumer.table = table
    if isinstance(getattr(consumer, "state", None), dict):
        consumer.state["table"] = table

    await consumer.broadcast_system("✅ Game is ready. Type **start new round** to begin.")

    try:
        round_continue = True
        while round_continue:
            if cancel_event and cancel_event.is_set():
                raise asyncio.CancelledError

            round_continue = False
            pending_response = True
            while pending_response:
                rsp = await consumer.get_input_all(
                    'Would you like to play a round? Enter **start new round**:',
                    cancel_event=cancel_event,
                )
                if str(rsp).strip().lower() == "start new round":
                    await table.Round()

                    # Clear any dangling per-user or group futures from the last hand
                    state = getattr(consumer, "state", {})
                    for fut in list(state.get("pending_inputs", {}).values()):
                        if not fut.done():
                            fut.set_result("hand over")
                    state.get("pending_inputs", {}).clear()

                    f_all = state.get("pending_inputs_all", {}).pop("awaiting all", None)
                    if f_all and not f_all.done():
                        f_all.set_result("hand over")

                    # Tell clients the hand is done and re-arm the next prompt
                    await consumer.broadcast_system("🟢 Hand finished. Type **start new round** or press the button.")

                    round_continue = True
                    pending_response = False
                else:
                    await consumer.broadcast_system('[INVALID ENTRY] Please type **start new round**')
    except asyncio.CancelledError:
        return {"status": "cancelled", "players": player_ids}
    return {"status": "started", "players": player_ids}




         