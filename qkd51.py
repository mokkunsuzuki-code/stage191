# stage51_dynamic_group_reliable.py
# 段階51：動的メンバー管理（JOIN/LEAVE＋即REKEY）× 信頼配送（ACK/再送）
#          ＋ ダブルラチェット（Sender Keys）でPFS
# 依存: cryptography
# 実行: pip install cryptography && python stage51_dynamic_group_reliable.py

import os, time, random, hmac, hashlib, collections
from dataclasses import dataclass
from typing import Dict, Tuple, List, Optional
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

# ========= パラメータ（軽量・高速） =========
IKM_BYTES     = 32
CHUNK_BYTES   = 1024
SKIP_WINDOW   = 16
ACK_TIMEOUT   = 0.12
MAX_RETRIES   = 6
RUNTIME_SEC   = 2.5
DROP_PROB     = 0.12
REORDER_PROB  = 0.25
MAX_DELAY     = 0.02

random.seed(7)

# ========= 共通ユーティリティ =========
def hkdf(ikm: bytes, length: int, info: bytes) -> bytes:
    return HKDF(algorithm=hashes.SHA256(), length=length, salt=None, info=info).derive(ikm)

# ========= QKDグループ・テープ（模擬：全員同じ塊を共有） =========
class GroupTape:
    def __init__(self): self.buf = bytearray()
    def ensure(self, min_bytes=IKM_BYTES):
        while len(self.buf) < min_bytes:
            self.buf.extend(os.urandom(CHUNK_BYTES))
    def take_ikm(self, n=IKM_BYTES)->bytes:
        self.ensure(n); ikm = bytes(self.buf[:n]); del self.buf[:n]; return ikm

# ========= ラチェット（Sender Keys） =========
@dataclass
class SenderState:
    send_ck: bytes
    nonce_base: bytes  # 8B
    seq: int = 0
    def next_mk_nonce(self) -> Tuple[bytes, bytes, int]:
        mk = hmac.new(self.send_ck, b"MSG", hashlib.sha256).digest()
        self.send_ck = hmac.new(self.send_ck, b"NEXT", hashlib.sha256).digest()
        nonce = self.seq.to_bytes(4, "big") + self.nonce_base
        s = self.seq; self.seq += 1
        return mk, nonce, s

@dataclass
class ReceiverState:
    recv_ck: bytes
    nonce_base: bytes  # 8B
    next_seq: int = 0
    skip: Dict[int, bytes] = None  # seq -> mk（取り置き）
    def __post_init__(self):
        if self.skip is None: self.skip = {}
    def _advance_to(self, target_seq: int, limit: int = SKIP_WINDOW):
        if target_seq < self.next_seq: return
        steps = target_seq - self.next_seq
        if steps > limit: raise ValueError("skip window 超過（遅延しすぎ）")
        for _ in range(steps):
            mk = hmac.new(self.recv_ck, b"MSG", hashlib.sha256).digest()
            self.recv_ck = hmac.new(self.recv_ck, b"NEXT", hashlib.sha256).digest()
            self.skip[self.next_seq] = mk
            self.next_seq += 1
    def key_for(self, seq: int) -> Tuple[bytes, bytes]:
        # 対象はその場で生成、手前は取り置き（KeyError対策の安全版）
        if seq < self.next_seq:
            if seq not in self.skip: raise ValueError("過去鍵が見つからない（期限切れ）")
            mk = self.skip.pop(seq)
        elif seq == self.next_seq:
            mk = hmac.new(self.recv_ck, b"MSG", hashlib.sha256).digest()
            self.recv_ck = hmac.new(self.recv_ck, b"NEXT", hashlib.sha256).digest()
            self.next_seq += 1
        else:
            self._advance_to(seq)
            mk = hmac.new(self.recv_ck, b"MSG", hashlib.sha256).digest()
            self.recv_ck = hmac.new(self.recv_ck, b"NEXT", hashlib.sha256).digest()
            self.next_seq += 1
        nonce = seq.to_bytes(4, "big") + self.nonce_base
        return mk, nonce

# ========= エポック（全員で一斉初期化） =========
class GroupEpoch:
    """
    IKM -> group_root, control_key(HMAC) -> 各送信者の (send_ck, nonce_base)
    """
    def __init__(self, epoch_id: int, ikm: bytes, member_ids: List[str]):
        self.id = epoch_id
        self.members = list(member_ids)
        self.root = hkdf(ikm, 32, b"group-root:"+str(epoch_id).encode())
        self.control_key = hkdf(ikm, 32, b"group-control:"+str(epoch_id).encode())
        self.sender_seeds: Dict[str, Tuple[bytes, bytes]] = {}
        for sid in member_ids:
            seed = hkdf(self.root, 40, b"sender-seed:"+sid.encode())
            self.sender_seeds[sid] = (seed[:32], seed[32:40])  # (send_ck, nonce_base)

# ========= メンバー =========
class Member:
    def __init__(self, mid: str, all_ids: List[str]):
        self.id = mid
        self.all_ids = list(all_ids)
        self.sender: Optional[SenderState] = None
        self.receivers: Dict[str, ReceiverState] = {}
        self.epoch_id: int = -1
        self.ctrl_key: Optional[bytes] = None
        self.inbox: List[str] = []
        self.seen: set = set()  # (sender, epoch, seq) for dedup

    def enter_epoch(self, epoch: GroupEpoch):
        self.epoch_id = epoch.id
        self.ctrl_key = epoch.control_key
        sc, nb = epoch.sender_seeds[self.id]
        self.sender = SenderState(sc, nb, 0)
        self.receivers = {}
        for sid in epoch.members:
            if sid == self.id: continue
            rc, rnb = epoch.sender_seeds[sid]
            self.receivers[sid] = ReceiverState(rc, rnb, 0)
        self.seen.clear()

    # データ送信（ブロードキャスト）
    def encrypt_for_group(self, text: str, aad: bytes=b""):
        mk, nonce, seq = self.sender.next_mk_nonce()
        ct = AESGCM(mk).encrypt(nonce, text.encode(), aad)
        return ("DATA", self.id, self.epoch_id, seq, nonce, ct, aad)

    # データ受信
    def recv_data(self, sender_id: str, epoch: int, seq: int, nonce: bytes, ct: bytes, aad: bytes=b""):
        key=(sender_id, epoch, seq)
        if key in self.seen:
            return True, ("ACK", sender_id, epoch, seq, self.id)
        if epoch != self.epoch_id or sender_id not in self.receivers:
            return False, None
        try:
            mk, expected = self.receivers[sender_id].key_for(seq)
        except Exception:
            return False, None
        if expected != nonce: return False, None
        try:
            pt = AESGCM(mk).decrypt(nonce, ct, aad).decode()
        except Exception:
            return False, None
        self.inbox.append(f"{sender_id}@E{epoch}: {pt}")
        self.seen.add(key)
        return True, ("ACK", sender_id, epoch, seq, self.id)

    # 管理メッセージ（JOIN/LEAVE/REKEY）検証
    def verify_control(self, kind: str, epoch_id: int, payload: dict, tag: bytes) -> bool:
        if self.ctrl_key is None or epoch_id != self.epoch_id: return False
        msg = f"{kind}|epoch={epoch_id}|{payload}".encode()
        return hmac.compare_digest(tag, hmac.new(self.ctrl_key, msg, hashlib.sha256).digest())

# ========= 擬似ネット（宛先付きの単一路線バス） =========
class UnreliableBus:
    def __init__(self, drop=DROP_PROB, reorder=REORDER_PROB, max_delay=MAX_DELAY):
        self.drop=drop; self.reorder=reorder; self.max_delay=max_delay
        self.buf: List[Tuple[float, str, tuple]] = []
    def send(self, to_id: str, packet: tuple):
        if random.random() < self.drop: return
        d = random.random()*self.max_delay
        if random.random() < self.reorder: d += random.random()*self.max_delay
        self.buf.append((time.time()+d, to_id, packet))
    def recv_ready(self) -> List[Tuple[str, tuple]]:
        now=time.time(); out=[]; keep=[]
        for t, to_id, pk in self.buf:
            (out if t<=now else keep).append((t, to_id, pk))
        self.buf=keep
        return [(to_id, pk) for _,to_id,pk in out]

# ========= 送信側の進捗（受信者ごとのACK待ち） =========
@dataclass
class Inflight:
    epoch: int; seq: int; nonce: bytes; ct: bytes; aad: bytes
    waiting: set               # まだACKが来てない受信者ID
    last_send: Dict[str,float] # 受信者ごとの最終送信時刻
    tries: Dict[str,int]       # 受信者ごとの試行回数

# ========= グループ管理（動的メンバー＋信頼配送＋再鍵） =========
class GroupReliableDynamic:
    def __init__(self, member_ids: List[str]):
        self.ids = list(member_ids)
        self.members = {mid: Member(mid, self.ids) for mid in self.ids}
        self.roster = list(member_ids)
        self.tape = GroupTape()
        self.bus = UnreliableBus()
        self.epoch_id = -1
        self.inflight: Dict[str, Dict[int, Inflight]] = {mid:{} for mid in self.ids}
        self._start_epoch()

    # ==== エポック（全員一斉再鍵） ====
    def _start_epoch(self):
        self.epoch_id += 1
        ikm = self.tape.take_ikm(IKM_BYTES)
        epoch = GroupEpoch(self.epoch_id, ikm, self.roster)
        for mid in self.roster:
            self.members[mid].enter_epoch(epoch)
        # 管理メッセージ：REKEY を署名して全員へ
        ctrl = self._ctrl_packet("REKEY", {"roster": self.roster})
        for mid in self.roster:
            self.bus.send(mid, ctrl)
        print(f"[REKEY] E{self.epoch_id} roster={self.roster}")

    def _ctrl_packet(self, kind: str, payload: dict) -> tuple:
        # 代表=roster[0] が作る（教育用）。実運用では全員が検証。
        rep = self.roster[0]
        msg = f"{kind}|epoch={self.epoch_id}|{payload}".encode()
        tag = hmac.new(self.members[rep].ctrl_key, msg, hashlib.sha256).digest() if self.members[rep].ctrl_key else b""
        return ("CTRL", kind, self.epoch_id, payload, tag)

    # ==== 送信（1→多、ACK待ちに登録） ====
    def send(self, sender_id: str, text: str, aad: bytes=b""):
        if sender_id not in self.roster: return
        pkt = self.members[sender_id].encrypt_for_group(text, aad)
        _, sid, ep, seq, nonce, ct, aad = pkt
        waiting = set(self.roster) - {sid}
        infl = Inflight(ep, seq, nonce, ct, aad, waiting, {}, {})
        self.inflight.setdefault(sid, {})[seq] = infl
        now = time.time()
        for rid in list(waiting):
            self.bus.send(rid, pkt)
            infl.last_send[rid]=now; infl.tries[rid]=1

    # ==== JOIN/LEAVE（即REKEY） ====
    def join(self, new_id: str):
        if new_id not in self.members:
            self.members[new_id] = Member(new_id, self.ids)
        if new_id in self.roster: return
        # CTRL:JOINを現メンバーへ
        ctrl = self._ctrl_packet("JOIN", {"add": new_id})
        for mid in self.roster: self.bus.send(mid, ctrl)
        # ロスター更新 → REKEY（新入りは過去を読めない）
        self.roster.append(new_id)
        self._start_epoch()
        # 既存のinflightは“今のロスター”基準：新メンバーへの過去メッセージ送付はしない

    def leave(self, member_id: str):
        if member_id not in self.roster: return
        # CTRL:LEAVE を現メンバーへ
        ctrl = self._ctrl_packet("LEAVE", {"remove": member_id})
        for mid in self.roster: self.bus.send(mid, ctrl)
        # ロスターから除外
        self.roster = [m for m in self.roster if m != member_id]
        # Inflightの待ち先からも除外（今後はACK不要）
        for table in self.inflight.values():
            for infl in table.values():
                infl.waiting.discard(member_id)
        # REKEY（脱退者は未来を読めない）
        self._start_epoch()

    # ==== ネット配送 ====
    def _deliver_bus(self):
        for to_id, pkt in self.bus.recv_ready():
            typ = pkt[0]
            if typ == "DATA":
                _, sid, ep, seq, nonce, ct, aad = pkt
                if to_id not in self.roster:  # すでに脱退していたら配らない
                    continue
                ok, ack = self.members[to_id].recv_data(sid, ep, seq, nonce, ct, aad)
                if ack: self.bus.send(sid, ack)
            elif typ == "ACK":
                _, sid, ep, seq, from_id = pkt
                infl = self.inflight.get(sid, {}).get(seq)
                if infl and ep==infl.epoch and from_id in infl.waiting:
                    infl.waiting.remove(from_id)
            elif typ == "CTRL":
                _, kind, ep, payload, tag = pkt
                # 成員だけが検証・適用（このデモでは検証のみ）
                for mid in list(self.roster):
                    self.members[mid].verify_control(kind, ep, payload, tag)

    def _retransmit_timeouts(self):
        now=time.time()
        for sid, table in self.inflight.items():
            for seq, infl in list(table.items()):
                # 全ACK揃ったら完了
                if not infl.waiting:
                    del table[seq]; continue
                # 個別にタイムアウト再送
                for rid in list(infl.waiting):
                    last = infl.last_send.get(rid, 0.0)
                    tries = infl.tries.get(rid, 0)
                    if rid not in self.roster:
                        infl.waiting.remove(rid); continue
                    if now - last > ACK_TIMEOUT and tries < MAX_RETRIES:
                        pkt = ("DATA", sid, infl.epoch, infl.seq, infl.nonce, infl.ct, infl.aad)
                        self.bus.send(rid, pkt)
                        infl.last_send[rid]=now; infl.tries[rid]=tries+1

    def all_delivered(self)->bool:
        return all(len(tbl)==0 for tbl in self.inflight.values())

    def run_until_done(self, time_limit=RUNTIME_SEC):
        end = time.time() + time_limit
        while time.time() < end and not self.all_delivered():
            self._deliver_bus()
            self._retransmit_timeouts()
            time.sleep(0.003)
        # 最後に一掃き
        self._deliver_bus()

# ========= デモ =========
def run_demo():
    chat = GroupReliableDynamic(["A","B"])  # 初期2人

    # ラウンド1：A/Bが各3通ずつ
    for i in range(3):
        for sid in ["A","B"]:
            chat.send(sid, f"{sid}-round1-{i+1}")
    chat.run_until_done()

    # Cが参加（JOIN ⇒ 即REKEY）
    chat.join("C")

    # ラウンド2：A/B/Cが各2通ずつ
    for i in range(2):
        for sid in ["A","B","C"]:
            chat.send(sid, f"{sid}-round2-{i+1}")
    chat.run_until_done()

    # Bが脱退（LEAVE ⇒ 即REKEY）
    chat.leave("B")

    # ラウンド3：A/Cが各2通ずつ
    for i in range(2):
        for sid in ["A","C"]:
            chat.send(sid, f"{sid}-round3-{i+1}")
    chat.run_until_done()

    # 結果表示
    for mid in ["A","B","C"]:
        if mid in chat.members:
            inbox = chat.members[mid].inbox
            print(f"=== {mid} が受け取った（合計 {len(inbox)} 通）===")
            print(", ".join(inbox) if inbox else "(なし)")
            print()

if __name__ == "__main__":
    run_demo()

