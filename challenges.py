"""注册引导 challenge 的内存存储。

按 CONTEXT.md「注册引导凭证」与「遥测鉴权边界」要求：
- challenge 与限时 token 配合使用，用于抬高低成本批量伪造的成本。
- 这只是接入层防伪造手段，不承诺阻止能改造客户端的强对手。

首版采用进程内内存存储足以满足单实例部署。后续若要多实例水平扩展，
可以平迁到 Redis 或 PostgreSQL 临时表。
"""

from __future__ import annotations

from dataclasses import dataclass
import time
from threading import Lock
from uuid import uuid4


@dataclass(slots=True, frozen=True)
class IssuedChallenge:
    """已签发的注册 challenge 状态。"""

    challenge_id: str
    challenge_token: str
    client_instance_id: str
    issued_at: float
    expires_at: float


class ChallengeStore:
    """注册 challenge 存储。"""

    def __init__(self, ttl_seconds: int = 300) -> None:
        self._ttl_seconds = ttl_seconds
        self._lock = Lock()
        self._challenges: dict[str, IssuedChallenge] = {}

    def issue(
        self,
        *,
        client_instance_id: str,
    ) -> IssuedChallenge:
        """签发一个新的限时 challenge。"""

        now = time.time()
        challenge = IssuedChallenge(
            challenge_id=uuid4().hex,
            challenge_token=uuid4().hex,
            client_instance_id=client_instance_id,
            issued_at=now,
            expires_at=now + self._ttl_seconds,
        )
        with self._lock:
            self._purge_expired_locked(now)
            self._challenges[challenge.challenge_id] = challenge
        return challenge

    def consume(
        self,
        *,
        challenge_id: str,
        challenge_token: str,
        client_instance_id: str,
    ) -> bool:
        """一次性消费 challenge，返回是否通过校验。"""

        now = time.time()
        with self._lock:
            self._purge_expired_locked(now)
            challenge = self._challenges.pop(challenge_id, None)

        if challenge is None:
            return False
        if challenge.expires_at < now:
            return False
        if challenge.challenge_token != challenge_token:
            return False
        if challenge.client_instance_id != client_instance_id:
            return False
        return True

    def _purge_expired_locked(self, now: float) -> None:
        """在持锁状态下清理已过期 challenge。"""

        expired_ids = [
            cid
            for cid, challenge in self._challenges.items()
            if challenge.expires_at < now
        ]
        for cid in expired_ids:
            self._challenges.pop(cid, None)
