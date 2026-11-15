import logging
import struct

from discord.gateway import DiscordVoiceWebSocket
from discord.voice_state import VoiceConnectionState

_log = logging.getLogger("dave_fix")
_MLS_COMMIT = 29
_MLS_WELCOME = 30


def apply():
    """Complete the DAVE transition handshake that discord.py-self 2.1.0 skips.

    Two gaps: ``_execute_transition`` never calls the davey session, and the
    commit/welcome handlers ignore transition ID 0 so it is never prepared on
    first join. Both leave ``session.ready`` False and audio unencrypted.
    """
    _patch_execute()
    _patch_binary()
    return True


def _patch_execute():
    original = VoiceConnectionState._execute_transition
    if getattr(original, "_dave_fixed", False):
        return

    async def _execute_transition(self, transition_id):
        session = getattr(self, "dave_session", None)
        version = self.dave_pending_transitions.get(transition_id)
        if session is not None and version is not None and not session.ready:
            try:
                session.prepare_transition(transition_id, version)
                if session.execute_transition(transition_id):
                    _log.info("DAVE actif, transition %d, epoch %s", transition_id, session.epoch)
            except Exception as exc:
                _log.warning("DAVE transition %d refusee : %r", transition_id, exc)
        await original(self, transition_id)

    _execute_transition._dave_fixed = True
    VoiceConnectionState._execute_transition = _execute_transition


def _patch_binary():
    original = DiscordVoiceWebSocket.received_binary_message
    if getattr(original, "_dave_fixed", False):
        return

    async def received_binary_message(self, msg):
        op = msg[2] if len(msg) > 2 else -1
        await original(self, msg)
        if op not in (_MLS_COMMIT, _MLS_WELCOME) or len(msg) < 5:
            return
        transition_id = struct.unpack_from(">H", msg, 3)[0]
        if transition_id != 0:
            return
        state = self._connection
        session = getattr(state, "dave_session", None)
        if session is None or session.ready or not state.dave_protocol_version:
            return
        try:
            session.prepare_transition(transition_id, state.dave_protocol_version)
            await self.send_transition_ready(transition_id)
            _log.info("DAVE transition 0 preparee, en attente d'execution")
        except Exception as exc:
            _log.warning("DAVE preparation transition 0 refusee : %r", exc)

    received_binary_message._dave_fixed = True
    DiscordVoiceWebSocket.received_binary_message = received_binary_message
