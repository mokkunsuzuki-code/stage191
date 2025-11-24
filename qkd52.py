# stage52_persistent_state.py
# 段階52：安全な永続化（AES-GCM暗号化）＋ 再起動復帰 ＋ 監査ログ（HMACチェーン）
# 実行: pip install cryptography && python stage52_persistent_state.py

import os, time, json, base64, random, hmac, hashlib, collections
from dataclasses import dataclass, asdict, field
from typing import Dict, Tuple, List, Optional, Any
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

# ====== パラメータ ======
IKM_BYTES     = 32
CHUNK_BYTES   = 1024
SKIP_WINDOW   = 16
ACK_TIMEOUT   = 0.12
MAX_RETRIES   = 6
RUNTIME_SEC   = 2.0
DROP_PROB     = 0.12
REORDER_PROB  = 0.25
MAX_DELAY     = 0.02

STATE_FILE    = "state.bin"         # 暗号化された状態保存ファイル
KEY_FILE      = "storage_master.key" # ストレージ暗号鍵（32B）※デモ用。権限600推奨
AUDIT_FILE    = "audit.log"         # 監査ログ（HMACチェーン）※プレーン（内容は暗号化不要）

random.seed(7)

# ====== ユーティリティ ======
def hkdf(ikm: bytes, length: int, info: bytes) -> bytes:
    return HKDF(algorithm=hashes.SHA256(), length=length, salt=None, info=info).derive(ikm)

def b64e(b: bytes) -> str:
    return base64.b64encode(b).decode()

def b64d(s: str) -> bytes:
    return base64.b64decode(s.encode())

# ====== 監査ログ（ハッシュチェーンHMAC） ======
class AuditLog:
    """
    tamper-evident 監査ログ
    - 各レコードは JSON 行
    - prev_tag と data から tag = HMAC(key, prev_tag || data)
    - 改ざん検出可能
    """
    def __init__(self, path=AUDIT_FILE, key_seed=b"qkd-audit"):
        self.path = path
        # デモ用：固定seedから鍵派生（実運用は別ストア管理）
        self.key = hashlib.sha256(key_seed).digest()
        self.prev_tag = b"\x00"*32
        # 既存ログがあれば継続
        if os.path.exists(self.path):
            with open(self.path, "rb") as f:
                for line in f:
                    try:
                        rec = json.loads(line.decode())
                        tag = b64d(rec["tag"]); data = rec["data"].encode()
                        exp = hmac.new(self.key, self.prev_tag + data, hashlib.sha256).digest()
                        if not hmac.compare_digest(tag, exp): raise ValueError("audit log tampered")
                        self.prev_tag = tag
                    except Exception:
                        # 壊れていたら新規開始
                        self.prev_tag = b"\x00"*32
                        break

    def append(self, data: str):
        tag = hmac.new(self.key, self.prev_tag + data.encode(), hashlib.sha256).digest()
        rec = {"data": data, "tag": b64e(tag)}
        with open(self.path, "ab") as f:
            f.write((json.dumps(rec, ensure_ascii=False)+"\n").encode())
        self.prev_tag = tag

# ====== QKDグループ・テープ（模擬） ======
class GroupTape:
    def __init__(self): self.buf = bytearray()
    def ensure(self, min_bytes=IKM_BYTES):
        while len(self.buf) < min_bytes:
            self.buf.extend(os.urandom(CHUNK_BYTES))
    def take_ikm(self, n=IKM_BYTES)->bytes:
        self.ensure(n); ikm = bytes(self.buf[:n]); del self.buf[:n]; return ikm
    def to_dict(self): return {"buf": b64e(bytes(self.buf))}
    @classmethod
    def from_dict(cls, d):
        obj = cls(); obj.buf = bytearray(b64d(d["buf"])); return obj

# ====== ラチェット（Sender Keys） ======
@dataclass
class SenderState:
    send_ck: bytes
    nonce_base: bytes
    seq: int = 0
    def next_mk_nonce(self) -> Tuple[bytes, bytes, int]:
        mk = hmac.new(self.send_ck, b"MSG", hashlib.sha256).digest()
        self.send_ck = hmac.new(self.send_ck, b"NEXT", hashlib.sha256).digest()
        nonce = self.seq.to_bytes(4, "big") + self.nonce_base
        s = self.seq; self.seq += 1
        return mk, nonce, s
    def to_dict(self): return {"send_ck": b64e(self.send_ck), "nonce_base": b64e(self.nonce_base), "seq": self.seq}
    @classmethod
    def from_dict(cls, d): return cls(b64d(d["send_ck"]), b64d(d["nonce_base"]), d["seq"])

@dataclass
class ReceiverState:
    recv_ck: bytes
    nonce_base: bytes
    next_seq: int = 0
    skip: Dict[int, bytes] = field(default_factory=dict)
    def _advance_to(self, target_seq: int, limit: int = SKIP_WINDOW):
        if target_seq < self.next_seq: return
        steps = target_seq - self.next_seq
        if steps > limit: raise ValueError("skip window 超過")
        for _ in range(steps):
            mk = hmac.new(self.recv_ck, b"MSG", hashlib.sha256).digest()
            self.recv_ck = hmac.new(self.recv_ck, b"NEXT", hashlib.sha256).digest()
            self.skip[self.next_seq] = mk
            self.next_seq += 1
    def key_for(self, seq: int) -> Tuple[bytes, bytes]:
        if seq < self.next_seq:
            if seq not in self.skip: raise ValueError("過去鍵なし")
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
    def to_dict(self):
        return {
            "recv_ck": b64e(self.recv_ck),
            "nonce_base": b64e(self.nonce_base),
            "next_seq": self.next_seq,
            "skip": {str(k): b64e(v) for k, v in self.skip.items()},
        }
    @classmethod
    def from_dict(cls, d):
        obj = cls(b64d(d["recv_ck"]), b64d(d["nonce_base"]), d["next_seq"])
        obj.skip = {int(k): b64d(v) for k, v in d.get("skip", {}).items()}
        return obj

# ====== エポック ======
class GroupEpoch:
    def __init__(self, epoch_id: int, ikm: bytes, member_ids: List[str]):
        self.id = epoch_id
        self.members = list(member_ids)
        self.root = hkdf(ikm, 32, b"group-root:"+str(epoch_id).encode())
        self.control_key = hkdf(ikm, 32, b"group-control:"+str(epoch_id).encode())
        self.sender_seeds: Dict[str, Tuple[bytes, bytes]] = {}
        for sid in member_ids:
            seed = hkdf(self.root, 40, b"sender-seed:"+sid.encode())
            self.sender_seeds[sid] = (seed[:32], seed[32:40])
    def to_dict(self):
        return {
            "id": self.id, "members": self.members,
            "root": b64e(self.root), "control_key": b64e(self.control_key),
            "sender_seeds": {k: [b64e(v[0]), b64e(v[1])] for k, v in self.sender_seeds.items()},
        }
    @classmethod
    def from_dict(cls, d):
        obj = cls.__new__(cls)
        obj.id = d["id"]; obj.members = list(d["members"])
        obj.root = b64d(d["root"]); obj.control_key = b64d(d["control_key"])
        obj.sender_seeds = {k: (b64d(v[0]), b64d(v[1])) for k, v in d["sender_seeds"].items()}
        return obj

# ====== メンバー ======
class Member:
    def __init__(self, mid: str, all_ids: List[str]):
        self.id = mid
        self.all_ids = list(all_ids)
        self.sender: Optional[SenderState] = None
        self.receivers: Dict[str, ReceiverState] = {}
        self.epoch_id: int = -1
        self.ctrl_key: Optional[bytes] = None
        self.inbox: List[str] = []
        self.seen: set = set()
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
    def encrypt_for_group(self, text: str, aad: bytes=b""):
        mk, nonce, seq = self.sender.next_mk_nonce()
        ct = AESGCM(mk).encrypt(nonce, text.encode(), aad)
        return ("DATA", self.id, self.epoch_id, seq, nonce, ct, aad)
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
    # --- シリアライズ ---
    def to_dict(self):
        return {
            "id": self.id, "all_ids": self.all_ids, "epoch_id": self.epoch_id,
            "ctrl_key": b64e(self.ctrl_key) if self.ctrl_key else None,
            "sender": self.sender.to_dict() if self.sender else None,
            "receivers": {k: v.to_dict() for k, v in self.receivers.items()},
            "inbox": self.inbox, "seen": [list(x) for x in self.seen],
        }
    @classmethod
    def from_dict(cls, d):
        obj = cls(d["id"], d["all_ids"])
        obj.epoch_id = d["epoch_id"]
        obj.ctrl_key = b64d(d["ctrl_key"]) if d["ctrl_key"] else None
        obj.sender = SenderState.from_dict(d["sender"]) if d["sender"] else None
        obj.receivers = {k: ReceiverState.from_dict(v) for k, v in d["receivers"].items()}
        obj.inbox = list(d["inbox"]); obj.seen = set(tuple(x) for x in d["seen"])
        return obj

# ====== 擬似ネット ======
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

# ====== Inflight（ACK待ち） ======
@dataclass
class Inflight:
    epoch: int; seq: int; nonce: bytes; ct: bytes; aad: bytes
    waiting: set
    last_send: Dict[str,float]
    tries: Dict[str,int]
    def to_dict(self):
        return {
            "epoch": self.epoch, "seq": self.seq,
            "nonce": b64e(self.nonce), "ct": b64e(self.ct), "aad": b64e(self.aad),
            "waiting": list(self.waiting),
            "last_send": {k: v for k, v in self.last_send.items()},
            "tries": {k: v for k, v in self.tries.items()},
        }
    @classmethod
    def from_dict(cls, d):
        return cls(d["epoch"], d["seq"], b64d(d["nonce"]), b64d(d["ct"]), b64d(d["aad"]),
                   set(d["waiting"]), {k: float(v) for k, v in d["last_send"].items()},
                   {k: int(v) for k, v in d["tries"].items()})

# ====== 永続化マネージャ ======
class Persistence:
    """
    ストレージ鍵（32B）を KEY_FILE に保存（権限600推奨）。
    状態JSONは AES-GCM(storage_key) で暗号化し STATE_FILE へ。
    """
    def __init__(self, key_file=KEY_FILE, state_file=STATE_FILE):
        self.key_file = key_file; self.state_file = state_file
        self.storage_key = self._load_or_create_key()

    def _load_or_create_key(self) -> bytes:
        if os.path.exists(self.key_file):
            with open(self.key_file, "rb") as f: return f.read()
        key = os.urandom(32)
        with open(self.key_file, "wb") as f: f.write(key)
        try: os.chmod(self.key_file, 0o600)
        except Exception: pass
        return key

    def save(self, obj: Dict[str, Any]):
        data = json.dumps(obj, ensure_ascii=False).encode()
        nonce = os.urandom(12)
        aead = AESGCM(self.storage_key)
        ct = aead.encrypt(nonce, data, b"stage52-state")
        with open(self.state_file, "wb") as f:
            f.write(nonce + ct)

    def load(self) -> Optional[Dict[str, Any]]:
        if not os.path.exists(self.state_file): return None
        with open(self.state_file, "rb") as f:
            blob = f.read()
        nonce, ct = blob[:12], blob[12:]
        aead = AESGCM(self.storage_key)
        try:
            data = aead.decrypt(nonce, ct, b"stage52-state")
        except Exception:
            return None
        return json.loads(data.decode())

# ====== グループ管理（永続化つき） ======
class GroupReliablePersistent:
    def __init__(self, member_ids: List[str]):
        self.ids = list(member_ids)
        self.roster = list(member_ids)
        self.members = {mid: Member(mid, self.ids) for mid in self.ids}
        self.tape = GroupTape()
        self.bus = UnreliableBus()
        self.audit = AuditLog()
        self.epoch_id = -1
        self.inflight: Dict[str, Dict[int, Inflight]] = {mid:{} for mid in self.ids}
        self.persist = Persistence()
        # 復元 or 新規
        if not self._restore():
            self._start_epoch()
            self.audit.append(f"BOOT new epoch E{self.epoch_id} roster={self.roster}")

    # === エポック ===
    def _start_epoch(self):
        self.epoch_id += 1
        ikm = self.tape.take_ikm(IKM_BYTES)
        epoch = GroupEpoch(self.epoch_id, ikm, self.roster)
        for mid in self.roster:
            self.members[mid].enter_epoch(epoch)
        self.audit.append(f"REKEY E{self.epoch_id} roster={self.roster}")

    # === 送信 ===
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
        self.audit.append(f"SEND {sid} E{ep} seq={seq} to={sorted(list(waiting))}")

    # === ネット配送 ===
    def _deliver_bus(self):
        for to_id, pkt in self.bus.recv_ready():
            typ = pkt[0]
            if typ == "DATA":
                _, sid, ep, seq, nonce, ct, aad = pkt
                if to_id not in self.roster:  # 既に脱退
                    continue
                ok, ack = self.members[to_id].recv_data(sid, ep, seq, nonce, ct, aad)
                if ack: self.bus.send(sid, ack)
            elif typ == "ACK":
                _, sid, ep, seq, from_id = pkt
                infl = self.inflight.get(sid, {}).get(seq)
                if infl and ep==infl.epoch and from_id in infl.waiting:
                    infl.waiting.remove(from_id)
                    if not infl.waiting:
                        self.audit.append(f"DELIVERED {sid} E{ep} seq={seq}")
            elif typ == "CTRL":
                pass  # 段階52では固定メンバーのまま（必要なら段階51のJOIN/LEAVEを合体可能）

    # === 再送 ===
    def _retransmit_timeouts(self):
        now=time.time()
        for sid, table in self.inflight.items():
            for seq, infl in list(table.items()):
                if not infl.waiting:
                    del table[seq]; continue
                for rid in list(infl.waiting):
                    last = infl.last_send.get(rid, 0.0)
                    tries = infl.tries.get(rid, 0)
                    if now - last > ACK_TIMEOUT and tries < MAX_RETRIES:
                        pkt = ("DATA", sid, infl.epoch, infl.seq, infl.nonce, infl.ct, infl.aad)
                        self.bus.send(rid, pkt)
                        infl.last_send[rid]=now; infl.tries[rid]=tries+1
                        if tries+1 == MAX_RETRIES:
                            self.audit.append(f"RETRY_LIMIT {sid} seq={infl.seq} to={rid}")

    # === 完了判定 ===
    def all_delivered(self)->bool:
        return all(len(tbl)==0 for tbl in self.inflight.values())

    # === ループ ===
    def run_until_done(self, time_limit=RUNTIME_SEC, autosave_every: int = 6):
        end = time.time() + time_limit
        tick = 0
        while time.time() < end and not self.all_delivered():
            self._deliver_bus()
            self._retransmit_timeouts()
            time.sleep(0.003)
            tick += 1
            if tick % autosave_every == 0:
                self.save_state()

        # 最後に掃き出し＆保存
        self._deliver_bus()
        self.save_state()

    # === 永続化 ===
    def save_state(self):
        obj = {
            "epoch_id": self.epoch_id,
            "roster": self.roster,
            "tape": self.tape.to_dict(),
            "members": {k: v.to_dict() for k, v in self.members.items()},
            "inflight": {sid: {str(seq): infl.to_dict() for seq, infl in tbl.items()} for sid, tbl in self.inflight.items()},
        }
        self.persist.save(obj)

    def _restore(self) -> bool:
        obj = self.persist.load()
        if not obj: return False
        try:
            self.epoch_id = obj["epoch_id"]
            self.roster = obj["roster"]
            self.tape = GroupTape.from_dict(obj["tape"])
            # メンバー復元
            self.members = {mid: Member.from_dict(md) for mid, md in obj["members"].items()}
            # inflight復元
            self.inflight = {sid: {int(seq): Inflight.from_dict(v) for seq, v in tbl.items()} for sid, tbl in obj["inflight"].items()}
            self.audit.append(f"RESTORE E{self.epoch_id} roster={self.roster}")
            return True
        except Exception:
            return False

# ====== デモ ======
def run_demo():
    # 初回実行は新規起動、2回目以降は state.bin を読み込んで継続
    ids = ["A","B","C"]
    chat = GroupReliablePersistent(ids)

    # 新規起動の場合に少し送る（復元起動なら何も送らず配達＆保存のみでもOK）
    if chat.all_delivered():
        for i in range(4):
            for sid in ids:
                chat.send(sid, f"{sid}-hello-{i+1}")
    chat.run_until_done()

    # 結果表示
    for mid in ids:
        inbox = chat.members[mid].inbox
        print(f"=== {mid} が受け取った（合計 {len(inbox)} 通）===")
        print(", ".join(inbox))
        print()

if __name__ == "__main__":
    run_demo()

