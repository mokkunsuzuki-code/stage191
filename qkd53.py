# stage53_secure_audit_recovery.py
# 段階53：監査（HMACチェーンで不可改ざん）＋ 安全ロールバック復旧（前回の整合スナップショットへ）
# 依存: cryptography
# 実行: pip install cryptography && python stage53_secure_audit_recovery.py

import os, time, json, base64, random, hmac, hashlib
from dataclasses import dataclass, field
from typing import Dict, Tuple, List, Optional, Any
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

# ===== パラメータ（軽量・高速） =====
IKM_BYTES     = 32
CHUNK_BYTES   = 1024
SKIP_WINDOW   = 16
ACK_TIMEOUT   = 0.12
MAX_RETRIES   = 6
RUNTIME_SEC   = 2.0
DROP_PROB     = 0.12
REORDER_PROB  = 0.25
MAX_DELAY     = 0.02

STATE_FILE    = "state.bin"         # 現行スナップショット（AES-GCM暗号化）
STATE_FILE_OLD= "state.prev.bin"    # 直前の良品スナップショット（ロールバック用）
KEY_FILE      = "storage_master.key" # ストレージ暗号鍵（32B）※デモ用
AUDIT_FILE    = "audit.log"         # 不可改ざん監査ログ（HMACチェーン）
AUDIT_KEY_SEED= b"qkd-audit-stage53" # デモ用：固定seed（実運用は別安全保護）
AUTOSAVE_EVERY= 6                   # 自動保存のステップ間隔

random.seed(7)

# ===== ユーティリティ =====
def hkdf(ikm: bytes, length: int, info: bytes) -> bytes:
    return HKDF(algorithm=hashes.SHA256(), length=length, salt=None, info=info).derive(ikm)
def b64e(b: bytes) -> str: return base64.b64encode(b).decode()
def b64d(s: str) -> bytes: return base64.b64decode(s.encode())

# ===== 監査ログ（HMACチェーン＋検証＋ロールオーバー） =====
class AuditVerifier:
    """
    tamper-evident 監査ログ
      ・各レコード: {"ts": float, "data": dict, "tag": b64(HMAC(prev_tag||json(data)))}
      ・全走査 verify_all() で改ざんを検出
      ・破損時は新しいチェーンを start_new_chain() で再開（前チェーンは保持）
    """
    def __init__(self, path=AUDIT_FILE, key_seed=AUDIT_KEY_SEED):
        self.path = path
        self.key = hashlib.sha256(key_seed).digest()
        self.prev_tag = b"\x00"*32
        self._bootstrap()

    def _bootstrap(self):
        if not os.path.exists(self.path):
            self.start_new_chain(note="init empty")
            return
        try:
            ok = self.verify_all(verbose=False)
            if not ok:  # 壊れている場合は新チェーンで継続
                self.start_new_chain(note="auto-recover(new-chain)")
        except Exception:
            self.start_new_chain(note="auto-recover(exception)")

    def _hmac(self, prev: bytes, data_json: str) -> bytes:
        return hmac.new(self.key, prev + data_json.encode(), hashlib.sha256).digest()

    def append(self, event: dict):
        data_json = json.dumps(event, ensure_ascii=False, separators=(",", ":"))
        tag = self._hmac(self.prev_tag, data_json)
        rec = {"ts": time.time(), "data": event, "tag": b64e(tag)}
        with open(self.path, "ab") as f:
            f.write((json.dumps(rec, ensure_ascii=False)+"\n").encode())
        self.prev_tag = tag

    def verify_all(self, verbose=True) -> bool:
        prev = b"\x00"*32
        if not os.path.exists(self.path):
            if verbose: print("[AUDIT] ログがありません。")
            return True
        with open(self.path, "rb") as f:
            for i, line in enumerate(f, 1):
                try:
                    rec = json.loads(line.decode())
                    tag = b64d(rec["tag"])
                    data_json = json.dumps(rec["data"], ensure_ascii=False, separators=(",", ":"))
                    calc = self._hmac(prev, data_json)
                    if not hmac.compare_digest(tag, calc):
                        if verbose: print(f"[AUDIT] 改ざん検出: {i} 行目")
                        return False
                    prev = tag
                except Exception:
                    if verbose: print(f"[AUDIT] パース失敗: {i} 行目")
                    return False
        if verbose: print("[AUDIT] 監査ログは正当です。")
        self.prev_tag = prev
        return True

    def start_new_chain(self, note=""):
        # 既存を退避せずに“追記開始”で新チェーンを継続（運用簡素化）
        self.prev_tag = b"\x00"*32
        self.append({"event":"AUDIT_CHAIN_START","note":note,"ts":time.time()})

# ===== QKDグループ・テープ（模擬） =====
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

# ===== ラチェット（Sender Keys） =====
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
    def to_dict(self):
        return {"send_ck": b64e(self.send_ck), "nonce_base": b64e(self.nonce_base), "seq": self.seq}
    @classmethod
    def from_dict(cls, d): return cls(b64d(d["send_ck"]), b64d(d["nonce_base"]), d["seq"])

@dataclass
class ReceiverState:
    recv_ck: bytes
    nonce_base: bytes  # 8B
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
        return {"recv_ck": b64e(self.recv_ck), "nonce_base": b64e(self.nonce_base),
                "next_seq": self.next_seq, "skip": {str(k): b64e(v) for k, v in self.skip.items()}}
    @classmethod
    def from_dict(cls, d):
        obj = cls(b64d(d["recv_ck"]), b64d(d["nonce_base"]), d["next_seq"])
        obj.skip = {int(k): b64d(v) for k,v in d.get("skip", {}).items()}
        return obj

# ===== エポック =====
class GroupEpoch:
    def __init__(self, epoch_id: int, ikm: bytes, member_ids: List[str]):
        self.id = epoch_id
        self.members = list(member_ids)
        self.root = hkdf(ikm, 32, b"group-root:"+str(epoch_id).encode())
        self.control_key = hkdf(ikm, 32, b"group-control:"+str(epoch_id).encode())
        self.sender_seeds: Dict[str, Tuple[bytes, bytes]] = {}
        for sid in self.members:
            seed = hkdf(self.root, 40, b"sender-seed:"+sid.encode())
            self.sender_seeds[sid] = (seed[:32], seed[32:40])  # (send_ck, nonce_base)
    def to_dict(self):
        return {"id": self.id, "members": self.members,
                "root": b64e(self.root), "control_key": b64e(self.control_key),
                "sender_seeds": {k:[b64e(v[0]), b64e(v[1])] for k,v in self.sender_seeds.items()}}
    @classmethod
    def from_dict(cls, d):
        obj = cls.__new__(cls)
        obj.id = d["id"]; obj.members = list(d["members"])
        obj.root = b64d(d["root"]); obj.control_key = b64d(d["control_key"])
        obj.sender_seeds = {k:(b64d(v[0]), b64d(v[1])) for k,v in d["sender_seeds"].items()}
        return obj

# ===== メンバー =====
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
    def to_dict(self):
        return {"id": self.id, "all_ids": self.all_ids, "epoch_id": self.epoch_id,
                "ctrl_key": b64e(self.ctrl_key) if self.ctrl_key else None,
                "sender": self.sender.to_dict() if self.sender else None,
                "receivers": {k:v.to_dict() for k,v in self.receivers.items()},
                "inbox": self.inbox, "seen":[list(x) for x in self.seen]}
    @classmethod
    def from_dict(cls, d):
        obj = cls(d["id"], d["all_ids"])
        obj.epoch_id = d["epoch_id"]
        obj.ctrl_key = b64d(d["ctrl_key"]) if d["ctrl_key"] else None
        obj.sender = SenderState.from_dict(d["sender"]) if d["sender"] else None
        obj.receivers = {k:ReceiverState.from_dict(v) for k,v in d["receivers"].items()}
        obj.inbox = list(d["inbox"]); obj.seen = set(tuple(x) for x in d["seen"])
        return obj

# ===== 擬似ネット =====
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

# ===== Inflight（ACK待ち） =====
@dataclass
class Inflight:
    epoch: int; seq: int; nonce: bytes; ct: bytes; aad: bytes
    waiting: set
    last_send: Dict[str,float]
    tries: Dict[str,int]
    def to_dict(self):
        return {"epoch": self.epoch, "seq": self.seq,
                "nonce": b64e(self.nonce), "ct": b64e(self.ct), "aad": b64e(self.aad),
                "waiting": list(self.waiting),
                "last_send": {k: v for k,v in self.last_send.items()},
                "tries": {k: v for k,v in self.tries.items()}}
    @classmethod
    def from_dict(cls, d):
        return cls(d["epoch"], d["seq"], b64d(d["nonce"]), b64d(d["ct"]), b64d(d["aad"]),
                   set(d["waiting"]), {k: float(v) for k,v in d["last_send"].items()},
                   {k: int(v) for k,v in d["tries"].items()})

# ===== 永続化（AES-GCM、ロールバック対応） =====
class Persistence:
    """
    - KEY_FILE に 32B の storage_key（権限600推奨）
    - save(): state.bin に安全書き込み（tmp→.prev→.bin の順で原子入替）
    - load(): state.bin を優先、失敗なら state.prev.bin を復旧（ロールバック）
    """
    def __init__(self, key_file=KEY_FILE, state_file=STATE_FILE, state_file_old=STATE_FILE_OLD):
        self.key_file=key_file; self.state_file=state_file; self.state_file_old=state_file_old
        self.storage_key = self._load_or_create_key()

    def _load_or_create_key(self)->bytes:
        if os.path.exists(self.key_file):
            with open(self.key_file,"rb") as f: return f.read()
        key = os.urandom(32)
        with open(self.key_file,"wb") as f: f.write(key)
        try: os.chmod(self.key_file, 0o600)
        except Exception: pass
        return key

    def save(self, obj: Dict[str, Any]):
        data = json.dumps(obj, ensure_ascii=False).encode()
        aead = AESGCM(self.storage_key)
        nonce = os.urandom(12)
        ct = aead.encrypt(nonce, data, b"stage53-state")
        tmp = self.state_file + ".tmp"
        with open(tmp, "wb") as f: f.write(nonce + ct)
        # ロールバック用に現行を退避
        if os.path.exists(self.state_file):
            try: os.replace(self.state_file, self.state_file_old)
            except Exception: pass
        os.replace(tmp, self.state_file)

    def load(self) -> Optional[Dict[str, Any]]:
        # まず現行
        obj = self._try_load(self.state_file)
        if obj is not None: return obj
        # だめならロールバック
        obj = self._try_load(self.state_file_old)
        return obj

    def _try_load(self, path)->Optional[Dict[str, Any]]:
        if not os.path.exists(path): return None
        with open(path, "rb") as f: blob = f.read()
        nonce, ct = blob[:12], blob[12:]
        aead = AESGCM(self.storage_key)
        try:
            data = aead.decrypt(nonce, ct, b"stage53-state")
            return json.loads(data.decode())
        except Exception:
            return None

# ===== グループ管理（監査＋永続＋信頼配送） =====
class GroupReliablePersistent:
    def __init__(self, member_ids: List[str]):
        self.ids = list(member_ids)
        self.roster = list(member_ids)
        self.members = {mid: Member(mid, self.ids) for mid in self.ids}
        self.tape = GroupTape()
        self.bus = UnreliableBus()
        self.audit = AuditVerifier()
        self.persist = Persistence()
        self.epoch_id = -1
        self.inflight: Dict[str, Dict[int, Inflight]] = {mid:{} for mid in self.ids}

        # 起動：監査検証→状態復元→必要なら新エポック
        if not self._restore():
            self._start_epoch()
            self.audit.append({"event":"BOOT_NEW","epoch":self.epoch_id,"roster":self.roster})

    # --- エポック ---
    def _start_epoch(self):
        self.epoch_id += 1
        ikm = self.tape.take_ikm(IKM_BYTES)
        epoch = GroupEpoch(self.epoch_id, ikm, self.roster)
        for mid in self.roster:
            self.members[mid].enter_epoch(epoch)
        self.audit.append({"event":"REKEY","epoch":self.epoch_id,"roster":self.roster})

    # --- 送信 ---
    def send(self, sender_id: str, text: str, aad: bytes=b""):
        if sender_id not in self.roster: return
        pkt = self.members[sender_id].encrypt_for_group(text, aad)
        _, sid, ep, seq, nonce, ct, aad = pkt
        waiting = set(self.roster) - {sid}
        infl = Inflight(ep, seq, nonce, ct, aad, waiting, {}, {})
        self.inflight.setdefault(sid, {})[seq] = infl
        now = time.time()
        for rid in list(waiting):
            self.bus.send(rid, pkt); infl.last_send[rid]=now; infl.tries[rid]=1
        self.audit.append({"event":"SEND","sid":sid,"epoch":ep,"seq":seq,"to":sorted(list(waiting))})

    # --- ネット配送 ---
    def _deliver_bus(self):
        for to_id, pkt in self.bus.recv_ready():
            typ = pkt[0]
            if typ == "DATA":
                _, sid, ep, seq, nonce, ct, aad = pkt
                if to_id not in self.roster:  # 脱退者は無し（段階53では固定メンバー）
                    continue
                ok, ack = self.members[to_id].recv_data(sid, ep, seq, nonce, ct, aad)
                if ack: self.bus.send(sid, ack)
            elif typ == "ACK":
                _, sid, ep, seq, from_id = pkt
                infl = self.inflight.get(sid, {}).get(seq)
                if infl and ep==infl.epoch and from_id in infl.waiting:
                    infl.waiting.remove(from_id)
                    if not infl.waiting:
                        self.audit.append({"event":"DELIVERED","sid":sid,"epoch":ep,"seq":seq})

    # --- タイムアウト再送 ---
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
                            self.audit.append({"event":"RETRY_LIMIT","sid":sid,"seq":infl.seq,"to":rid})

    # --- 完了判定 ---
    def all_delivered(self)->bool:
        return all(len(tbl)==0 for tbl in self.inflight.values())

    # --- ループ実行（オートセーブ付き） ---
    def run_until_done(self, time_limit=RUNTIME_SEC, autosave_every: int = AUTOSAVE_EVERY):
        end = time.time() + time_limit
        tick = 0
        while time.time() < end and not self.all_delivered():
            self._deliver_bus()
            self._retransmit_timeouts()
            time.sleep(0.003)
            tick += 1
            if tick % autosave_every == 0:
                self.save_state()
        self._deliver_bus()
        self.save_state()

    # --- 保存／復元 ---
    def save_state(self):
        obj = {
            "epoch_id": self.epoch_id,
            "roster": self.roster,
            "tape": self.tape.to_dict(),
            "members": {k: v.to_dict() for k, v in self.members.items()},
            "inflight": {sid: {str(seq): infl.to_dict() for seq, infl in tbl.items()}
                         for sid, tbl in self.inflight.items()},
        }
        self.persist.save(obj)
        self.audit.append({"event":"CHECKPOINT","epoch":self.epoch_id,"inflight_total":
                           sum(len(tbl) for tbl in self.inflight.values())})

    def _restore(self) -> bool:
        # 監査ログ整合性チェック → 状態読込（現行 or ロールバック）
        if not self.audit.verify_all(verbose=True):
            # 改ざん/破損がある場合は新チェーン開始（状態は復旧を試みる）
            self.audit.start_new_chain(note="verify-failed-restart-chain")

        obj = self.persist.load()
        if not obj: return False
        try:
            self.epoch_id = obj["epoch_id"]
            self.roster   = obj["roster"]
            self.tape     = GroupTape.from_dict(obj["tape"])
            # メンバー復元
            restored_members = {}
            for mid, md in obj["members"].items():
                restored_members[mid] = Member.from_dict(md)
            self.members = restored_members
            # inflight復元
            restored_inflight: Dict[str, Dict[int, Inflight]] = {}
            for sid, tbl in obj["inflight"].items():
                restored_inflight[sid] = {int(seq): Inflight.from_dict(v) for seq, v in tbl.items()}
            self.inflight = restored_inflight
            self.audit.append({"event":"RESTORE_OK","epoch":self.epoch_id,
                               "roster":self.roster,"inflight_total":
                               sum(len(tbl) for tbl in self.inflight.values())})
            return True
        except Exception as e:
            self.audit.append({"event":"RESTORE_FAIL","reason":str(e)})
            return False

# ===== デモ =====
def run_demo():
    ids = ["A","B","C"]
    chat = GroupReliablePersistent(ids)

    # 起動直後に全て配達済みなら、少し投げる（復元起動なら送らず配達のみでもOK）
    if chat.all_delivered():
        for i in range(4):
            for sid in ids:
                chat.send(sid, f"{sid}-hello-{i+1}")

    chat.run_until_done()

    # 監査ログ検証
    chat.audit.verify_all(verbose=True)

    # 結果表示
    for mid in ids:
        inbox = chat.members[mid].inbox
        print(f"=== {mid} が受け取った（合計 {len(inbox)} 通）===")
        print(", ".join(inbox))
        print()

    # ロールバック復旧のテスト（任意）：state.bin をわざと壊して再読込
    # with open(STATE_FILE, "ab") as f: f.write(b"corrupt")
    # chat2 = GroupReliablePersistent(ids)  # state.prev.bin で復旧するはず

if __name__ == "__main__":
    run_demo()
