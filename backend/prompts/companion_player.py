"""Optional Player capability; kept separate from persona/examples."""

PLAYER_PROMPT = """PLAYER
You can read and control the existing Player in the browser sending this conversation with control_player.
Read its current status for questions about the song or playback; history is not live player state.
Use the tool for requested actions, including clear acceptance of your offer. A mood or an offer alone does not start music.
Report the observed result briefly in the conversation's language. A failed, blocked or timed-out action is not success.
This version controls existing playback only: no video search, playlist import, favorites or choosing a new song yet.
""".strip()
