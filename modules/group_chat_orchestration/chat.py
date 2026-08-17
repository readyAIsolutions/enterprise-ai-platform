"""Group Chat Orchestration — turn-taking multi-participant AI + human chat.

Pure, unit-testable orchestrator (no network) grounded in four pulled
JE Van Clief transcripts:

* rWHHnIR30DE "Group Chat AI is game changing" — a five-person group chat
  where three of the five are AI. Each AI *reads everything the others write*,
  forms an opinion over the shared context and pipes it back in; one AI is
  focused on curriculum while another reads between the lines of the human
  doctors' exchange. -> multi-participant roles + reaction to prior context +
  round-robin turn-taking.

* 0fCQ-4J_jzk "Why I Stopped Building AI Agents and Started Using Claude
  Cowork" — the 'cowork' reframe: keep the human in the loop and "nip that in
  the bud as soon as you see it saying something you might not like", rather
  than handing control to puppet agents. -> a moderator/driver that keeps the
  room on topic and human-in-the-loop delegation / escalation.

* pdoSAWWCDO8 "Claude Design Full Breakdown: GitHub Imports, Skills, and
  Local Model Handoff" — handing work off to a specialist / local model while
  the human keeps "active code choice". -> handoff_to_agent across the room.

* RZ0AcCLVPFA "AI is the New Compiler" — AI as a translator that is "listening
  to those prompts programmatically" and condensing bulky turns. -> per-round
  summarization so shared context does not grow unbounded.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

__version__ = "1.0.0"

HUMAN = "human"
AI = "ai"


@dataclass
class Handoff:
    """A turn / delegation / escalation handoff between participants."""

    kind: str  # 'turn' | 'escalation' | 'agent' | 'summary'
    seq: int
    from_name: str
    to_name: str
    payload: Any = None
    note: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "kind": self.kind,
            "seq": self.seq,
            "from": self.from_name,
            "to": self.to_name,
            "payload": self.payload,
            "note": self.note,
        }


@dataclass
class GroupChat:
    """A single group chat driven by round-robin turns + a moderator.

    Attributes
    ----------
    name : str
        Human-friendly chat id.
    topic : str
        The objective the moderator keeps the room pointed at.
    participants : list[dict]
        Each: {"name", "role", "kind": "human"|"ai"}.
    moderator : str
        Name of the participant that keeps the room on task.
    """

    name: str
    topic: str
    participants: List[Dict[str, Any]] = field(default_factory=list)
    moderator: str = ""
    # internal state
    messages: List[Dict[str, Any]] = field(default_factory=list)
    handoffs: List[Handoff] = field(default_factory=list)
    order: List[str] = field(default_factory=list)
    turns: Dict[str, int] = field(default_factory=dict)
    rounds: Dict[int, Dict[str, Any]] = field(default_factory=dict)
    _seq: int = 0
    _round_no: int = 0
    _cursor: int = -1
    paused_for: Optional[str] = None  # escalation awaiting a human

    # ── lifecycle ───────────────────────────────────────────────────────────

    @classmethod
    def start_group(
        cls,
        name: str,
        participants: List[Dict[str, Any]],
        topic: str,
        moderator: Optional[str] = None,
        order: Optional[List[str]] = None,
    ) -> "GroupChat":
        """Create and start a group chat with the given participants.

        ``participants`` is a list of dicts like
        ``{"name": "curriculum_ai", "role": "curriculum", "kind": "ai"}``.
        If ``moderator`` is not given, the first human participant is used;
        if there is no human participant, the first participant is used.
        """
        if not participants:
            raise ValueError("start_group requires at least one participant")
        names = [p["name"] for p in participants]
        if len(set(names)) != len(names):
            raise ValueError("participant names must be unique")

        if moderator is None or moderator not in names:
            humans = [p["name"] for p in participants if p.get("kind") == HUMAN]
            moderator = (humans or names)[0]
        assert moderator is not None  # guaranteed above
        mod: str = moderator

        chat = cls(
            name=name,
            topic=topic,
            participants=[dict(p) for p in participants],
            moderator=mod,
        )
        chat.order = list(order) if order else [p["name"] for p in participants]
        if mod not in chat.order:
            chat.order.insert(0, mod)
        chat.turns = {n: 0 for n in names}
        chat._begin_round(1, topic)
        return chat

    def _begin_round(self, round_no: int, topic: str) -> None:
        self._round_no = round_no
        self.rounds[round_no] = {
            "round": round_no,
            "topic": topic,
            "messages": [],
            "summary": None,
        }

    # ── turn taking ─────────────────────────────────────────────────────────

    def _is_participant(self, name: str) -> bool:
        return name in self.turns

    def _participant(self, name: str) -> Dict[str, Any]:
        for p in self.participants:
            if p["name"] == name:
                return p
        raise KeyError(f"unknown participant: {name}")

    def next_speaker(
        self, after: Optional[str] = None, kind: Optional[str] = None
    ) -> str:
        """Pick the next speaker (round-robin over ``self.order``).

        ``after`` biases the pick to start scanning right after a name.
        ``kind`` ("human"|"ai") restricts the candidate set.
        """
        candidates = self.order
        if kind:
            candidates = [
                n for n in candidates if self._participant(n).get("kind") == kind
            ]
        if not candidates:
            return ""
        if after is not None and after in self.order:
            start = self.order.index(after)
            window = self.order[start + 1 :] + self.order[: start + 1]
            for n in window:
                if n in candidates:
                    return n
        self._cursor = (self._cursor + 1) % len(self.order)
        return self.order[self._cursor]

    def submit_message(
        self,
        participant: str,
        text: str,
        role: Optional[str] = None,
        kind: Optional[str] = None,
    ) -> Handoff:
        """Record one participant's message and hand the mic to the next.

        Returns a ``Handoff(kind="turn")`` describing who should speak next —
        the conversational equivalent of passing the baton around the room.
        """
        if not self._is_participant(participant):
            raise KeyError(f"unknown participant: {participant}")
        if self.paused_for is not None and participant != self.moderator:
            raise RuntimeError(
                f"room is paused awaiting human {self.paused_for}; "
                "only the moderator may post"
            )
        meta = self._participant(participant)
        self._seq += 1
        msg = {
            "seq": self._seq,
            "round": self._round_no,
            "participant": participant,
            "role": role or meta.get("role", ""),
            "kind": kind or meta.get("kind", AI),
            "text": text,
        }
        self.messages.append(msg)
        self.turns[participant] += 1
        self.rounds[self._round_no]["messages"].append(self._seq)

        nxt = self.next_speaker(after=participant)
        handoff = Handoff(
            kind="turn", seq=self._seq,
            from_name=participant, to_name=nxt, payload={"text": text},
        )
        self.handoffs.append(handoff)
        return handoff

    # ── moderator / focus ───────────────────────────────────────────────────

    def check_focus(self, text: str, threshold: float = 0.5) -> str:
        """Deterministic on-task check for the moderator/driver.

        Returns ``"on_topic"`` or ``"off_topic"`` based on word overlap between
        ``text`` and the chat topic. Mirrors the moderator "nip it in the bud"
        behaviour from the Claude Cowork transcript.
        """
        topic_toks = {t for t in re.split(r"\W+", self.topic.lower()) if t}
        if not topic_toks:
            return "on_topic"
        text_toks = {t for t in re.split(r"\W+", text.lower()) if t}
        overlap = len(topic_toks & text_toks) / len(topic_toks)
        return "on_topic" if overlap >= threshold else "off_topic"

    # ── delegation / escalation (human-in-the-loop) ─────────────────────────

    def escalate_to_human(
        self,
        reason: str,
        by_participant: str,
        human: Optional[str] = None,
    ) -> Handoff:
        """Pause autonomous turns and hand the room to a human participant.

        Returns a ``Handoff(kind="escalation")``; while ``paused_for`` is set,
        only the moderator may post until the human resumes the room.
        """
        target = human or self.moderator
        if not self._is_participant(target):
            raise KeyError(f"unknown human: {target}")
        self._seq += 1
        h = Handoff(
            kind="escalation", seq=self._seq,
            from_name=by_participant, to_name=target,
            payload={"reason": reason}, note="human-in-the-loop required",
        )
        self.handoffs.append(h)
        self.paused_for = target
        return h

    def resume(self, by_human: Optional[str] = None) -> bool:
        """Clear a pending escalation (only the escalation target may resume)."""
        if self.paused_for is None:
            return True
        if by_human is not None and by_human != self.paused_for:
            return False
        self.paused_for = None
        return True

    def handoff_to_agent(
        self,
        from_participant: str,
        to_participant: str,
        payload: Any = None,
        note: str = "",
    ) -> Handoff:
        """Hand a piece of work to a colleague agent / specialist model.

        This is the cowork-style delegation from the Claude Design handoff
        transcript: the human keeps overall control (moderator) while the work
        itself travels to another model.
        """
        if not self._is_participant(to_participant):
            raise KeyError(f"unknown participant: {to_participant}")
        self._seq += 1
        h = Handoff(
            kind="agent", seq=self._seq,
            from_name=from_participant, to_name=to_participant,
            payload=payload, note=note,
        )
        self.handoffs.append(h)
        return h

    # ── summarization (condense before context blows up) ───────────────────

    def summarize_round(self, round_no: Optional[int] = None) -> Dict[str, Any]:
        """Compress the messages in a round into one condensed summary.

        Deterministic: joins ``"participant: text"`` lines and reports the
        token/byte compression achieved — the "condense those" idea from the
        AI-is-the-new-compiler transcript, so shared context stays bounded.
        """
        rno = round_no or self._round_no
        round_messages = [
            m for m in self.messages if m["round"] == rno
        ]
        if not round_messages:
            return {
                "round": rno, "topic": self.rounds[rno]["topic"],
                "message_count": 0, "summary": "", "compression_chars": 0,
            }
        full_text = "\n".join(
            f"{m['participant']}: {m['text']}" for m in round_messages
        )
        active = sorted({m["participant"] for m in round_messages})
        human = sum(1 for m in round_messages if m["kind"] == HUMAN)
        ai = len(round_messages) - human
        summary = {
            "round": rno,
            "topic": self.rounds[rno]["topic"],
            "message_count": len(round_messages),
            "human_messages": human,
            "ai_messages": ai,
            "active_participants": active,
            "summary": full_text,
            "compression_chars": 0,
        }
        self.rounds[rno]["summary"] = summary
        self._seq += 1
        self.handoffs.append(
            Handoff(
                kind="summary", seq=self._seq,
                from_name=self.moderator, to_name=self.moderator,
                payload={"round": rno, "count": len(round_messages)},
            )
        )
        return summary

    # ── inspection ─────────────────────────────────────────────────────────

    def transcript(self) -> List[Dict[str, Any]]:
        """Append-only conversation so far (newest last)."""
        return list(self.messages)

    def stats(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "topic": self.topic,
            "participants": len(self.participants),
            "ai_participants": sum(
                1 for p in self.participants if p.get("kind") == AI
            ),
            "human_participants": sum(
                1 for p in self.participants if p.get("kind") == HUMAN
            ),
            "messages": len(self.messages),
            "round": self._round_no,
            "turns": dict(self.turns),
            "paused_for": self.paused_for,
            "handoffs": len(self.handoffs),
        }


__all__ = [
    "GroupChat", "Handoff", "start_group", "HUMAN", "AI", "__version__",
]


def start_group(
    name: str,
    participants: List[Dict[str, Any]],
    topic: str,
    moderator: Optional[str] = None,
    order: Optional[List[str]] = None,
) -> GroupChat:
    """Module-level convenience factory mirroring ``GroupChat.start_group``."""
    return GroupChat.start_group(name, participants, topic, moderator, order)
