import logging
import struct
import sys

from discord.gateway import DiscordVoiceWebSocket
from discord.voice_state import VoiceConnectionState

_log = logging.getLogger("dave_fix")
_MLS_COMMIT = 29
_MLS_WELCOME = 30


def _ensure_logging():
    """Rend les lignes du correctif visibles dans les logs Render."""
    if _log.handlers or logging.getLogger().handlers:
        return
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter("[dave_fix] %(levelname)s %(message)s"))
    _log.addHandler(handler)
    _log.setLevel(logging.INFO)
    _log.propagate = False


def apply():
    """Complete the DAVE transition handshake that discord.py-self 2.1.0 skips.

    Three gaps: ``_execute_transition`` never calls the davey session, the
    commit/welcome handlers ignore transition ID 0 so it is never prepared on
    first join, and nothing ever executes that initial transition. All three
    leave ``session.ready`` False and audio unencrypted, which Discord drops.
    """
    _ensure_logging()
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
        if session is not None and not session.ready:
            if version is None:
                version = self.dave_protocol_version
            if version:
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
            executed = session.execute_transition(transition_id)
            await self.send_transition_ready(transition_id)
            _log.info(
                "DAVE transition 0 executee (ready=%s, epoch=%s), envoi accuse",
                session.ready,
                session.epoch,
            )
            if not executed:
                _log.warning("DAVE transition 0 : execute_transition a renvoye False")
        except Exception as exc:
            _log.warning("DAVE preparation transition 0 refusee : %r", exc)

    received_binary_message._dave_fixed = True
    DiscordVoiceWebSocket.received_binary_message = received_binary_message
