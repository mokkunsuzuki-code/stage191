# stage50_group_reliable.py
# 段階50：グループ通信 × ダブルラチェット（Sender Keys） × 信頼配送（ACK/再送/順序整列/重複排除）
# 実行: pip install cryptography && python stage50_group_reliable.py

import os, time, random, hmac, hashlib, collections
from dataclasses import dataclass
from typing import Dict, Tuple, List, Optional
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

# ====== パラメータ（軽量でサクサク動く設定） ======
GROUP_IDS     = ["A", "B", "C"]
MSG_PER_USER  = 6           # 各メンバーが送る通数
IKM_BYTES     = 32          # 1エポックのQKD素材（模擬）
CHUNK_BYTES   = 1024        # テープ補充単位
SKIP_WINDOW   = 16          # 受信の順序乱れを吸収する“取り置き鍵”の上限
ACK_TIMEOUT   = 0.12        # ACK待ちタイムアウト（秒）
MAX_RETRIES   = 6           # 再送最大回数（受信者ごと）
RUNTIME_SEC   = 2.5         # メインループ上限時間
DROP_PROB     = 0.12        # 擬似ネットの損失率
REORDER_PROB  = 0.25        # 擬似ネットの並べ替え確率
MAX_DELAY     = 0.02        # 擬似ネットの1ホップ最大遅延（秒）

random.seed(7)

# ====== 便利関数 ======
def hkdf(ikm: bytes, length: int, info: bytes) -> bytes:
    return HKDF(algorithm=hashes.SHA256(), length=length, salt=None, info=info).derive(ikm)

# ====== QKDグループ・テープ（模擬：全員が同じ塊を共有） ======
class GroupTape:
    def __init__(self): self.buf = bytearray()
    def ensure(self, min_bytes=IKM_BYTES):
        while len(self.buf) < min_bytes:
            self.buf.extend(os.urandom(CHUNK_BYTES))
    def take_ikm(self, n=IKM_BYTES)->bytes:
        self.ensure(n); ikm = bytes(self.buf[:n]); del self.buf[:n]; return ikm

# ====== 送受ラチェット（Sender Keys） ======
@dataclass
class SenderState:
    send_ck: bytes
    nonce_base: bytes  # 8B
    seq: int = 0
    def next_mk_nonce(self) -> Tuple[bytes, bytes, int]:
        mk = hmac.new(self.send_ck, b"MSG", hashlib.sha256).digest()
        self.send_ck = hmac.new(self.send_ck, b"NEXT", hashlib.sha256).digest()
        nonce = self.seq.to_bytes(4, "big") + self.nonce_base
        out_seq = self.seq
        self.seq += 1
        return mk, nonce, out_seq

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
        # --- 改良版：対象の鍵は“その場で作る”、手前は取り置き ---
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

# ====== グループ・エポック（全員一斉の初期化） ======
class GroupEpoch:
    def __init__(self, epoch_id: int, ikm: bytes, member_ids: List[str]):
        self.id = epoch_id
        self.root = hkdf(ikm, 32, b"group-root:"+str(epoch_id).encode())
        self.sender_seeds: Dict[str, Tuple[bytes, bytes]] = {}
        for sid in member_ids:
            seed = hkdf(self.root, 40, b"sender-seed:"+sid.encode())
            self.sender_seeds[sid] = (seed[:32], seed[32:40])  # (send_ck, nonce_base)

# ====== メンバー ======
class Member:
    def __init__(self, mid: str, all_ids: List[str]):
        self.id = mid
        self.all_ids = list(all_ids)
        self.sender: Optional[SenderState] = None
        self.receivers: Dict[str, ReceiverState] = {}
        self.epoch_id: int = -1
        self.inbox: List[str] = []
        self.seen: set = set()  # (sender, epoch, seq) の重複排除用
    def enter_epoch(self, epoch: GroupEpoch):
        self.epoch_id = epoch.id
        sc, nb = epoch.sender_seeds[self.id]
        self.sender = SenderState(sc, nb, 0)
        self.receivers = {}
        for sid in self.all_ids:
            if sid == self.id: continue
            rc, rnb = epoch.sender_seeds[sid]
            self.receivers[sid] = ReceiverState(rc, rnb, 0)
        self.seen.clear()
    # 送信（1→多）
    def encrypt_for_group(self, text: str, aad: bytes=b""):
        mk, nonce, seq = self.sender.next_mk_nonce()
        ct = AESGCM(mk).encrypt(nonce, text.encode(), aad)
        return ("DATA", self.id, self.epoch_id, seq, nonce, ct, aad)
    # 受信（1←送信者）
    def recv_data(self, sender_id: str, epoch: int, seq: int, nonce: bytes, ct: bytes, aad: bytes=b""):
        key = (sender_id, epoch, seq)
        if key in self.seen:
            # 既に読んだ（重複）→ それでもACKは返す
            return True, ("ACK", sender_id, epoch, seq, self.id)
        if epoch != self.epoch_id:     # エポック違いは読めない
            return False, None
        if sender_id not in self.receivers:
            return False, None
        mk, expected = self.receivers[sender_id].key_for(seq)
        if expected != nonce:
            return False, None
        try:
            pt = AESGCM(mk).decrypt(nonce, ct, aad).decode()
        except Exception:
            return False, None
        self.inbox.append(f"{sender_id}@E{epoch}: {pt}")
        self.seen.add(key)
        return True, ("ACK", sender_id, epoch, seq, self.id)

# ====== 擬似ネット（to=宛先ID を持つ単一路線バス） ======
class UnreliableBus:
    def __init__(self, drop=DROP_PROB, reorder=REORDER_PROB, max_delay=MAX_DELAY):
        self.drop=drop; self.reorder=reorder; self.max_delay=max_delay
        self.buf: List[Tuple[float, str, tuple]] = []  # (到着時刻, 宛先ID, パケット)
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

# ====== 送信者側：信頼配送トラッカー（ACK収集・再送） ======
@dataclass
class Inflight:
    epoch: int
    seq: int
    nonce: bytes
    ct: bytes
    aad: bytes
    waiting: set               # まだACKを待つ受信者ID
    last_send: Dict[str,float] # 受信者ごとの最終送信時刻
    tries: Dict[str,int]       # 受信者ごとの送信回数

# ====== グループ管理（エポック初期化＋信頼配送） ======
class GroupReliableChat:
    def __init__(self, member_ids: List[str]):
        self.ids = list(member_ids)
        self.members = {mid: Member(mid, self.ids) for mid in self.ids}
        self.tape = GroupTape()
        self.bus = UnreliableBus()
        self.epoch_id = -1
        self.inflight: Dict[str, Dict[int, Inflight]] = {mid:{} for mid in self.ids}  # sender -> seq -> Inflight
        self._start_epoch()

    def _start_epoch(self):
        self.epoch_id += 1
        ikm = self.tape.take_ikm(IKM_BYTES)
        epoch = GroupEpoch(self.epoch_id, ikm, self.ids)
        for m in self.members.values(): m.enter_epoch(epoch)
        print(f"[REKEY] エポック開始: E{self.epoch_id}")

    # 1→多 送信：即座に全受信者へデータを投入し、ACK待ちテーブルに載せる
    def send(self, sender_id: str, text: str, aad: bytes=b""):
        pkt = self.members[sender_id].encrypt_for_group(text, aad)
        _, sid, ep, seq, nonce, ct, aad = pkt
        waiting = set(self.ids) - {sid}
        infl = Inflight(ep, seq, nonce, ct, aad, waiting, {}, {})
        self.inflight[sender_id][seq] = infl
        now = time.time()
        for rid in waiting:
            self.bus.send(rid, pkt)
            infl.last_send[rid]=now; infl.tries[rid]=1

    # ネット受信→各メンバーへ配達→ACKが出たら送信者へ積む
    def _deliver_bus(self):
        for to_id, pkt in self.bus.recv_ready():
            typ = pkt[0]
            if typ == "DATA":
                _, sid, ep, seq, nonce, ct, aad = pkt
                ok, ack = self.members[to_id].recv_data(sid, ep, seq, nonce, ct, aad)
                if ack:  # 成功でも重複でもACKは返す
                    self.bus.send(sid, ack)
            elif typ == "ACK":
                _, sid, ep, seq, from_id = pkt
                infl = self.inflight.get(sid, {}).get(seq)
                if infl and from_id in infl.waiting and ep==infl.epoch:
                    infl.waiting.remove(from_id)

    # タイムアウトした宛先へだけ再送
    def _retransmit_timeouts(self):
        now=time.time()
        for sid, table in self.inflight.items():
            for seq, infl in list(table.items()):
                # 全員からACKが来たら完了
                if not infl.waiting:
                    del table[seq]
                    continue
                for rid in list(infl.waiting):
                    last = infl.last_send.get(rid, 0.0)
                    tries = infl.tries.get(rid, 0)
                    if now - last > ACK_TIMEOUT and tries < MAX_RETRIES:
                        pkt = ("DATA", sid, infl.epoch, infl.seq, infl.nonce, infl.ct, infl.aad)
                        self.bus.send(rid, pkt)
                        infl.last_send[rid]=now; infl.tries[rid]=tries+1

    def all_delivered(self) -> bool:
        return all(len(tbl)==0 for tbl in self.inflight.values())

    # デモ用：まとめて送って、全ACKが揃うまで回す
    def run_until_done(self, time_limit=RUNTIME_SEC):
        end=time.time()+time_limit
        while time.time()<end and not self.all_delivered():
            self._deliver_bus()
            self._retransmit_timeouts()
            time.sleep(0.003)
        # 取り残しを最後にもう一掃き
        self._deliver_bus()

# ====== デモ ======
def run_demo():
    chat = GroupReliableChat(GROUP_IDS)

    # 各メンバーが順番にMSG_PER_USER通ずつ送信（混在順）
    for i in range(MSG_PER_USER):
        for sid in GROUP_IDS:
            chat.send(sid, f"MSG#{i+1} from {sid}")
    chat.run_until_done()

    # 結果表示
    for mid in GROUP_IDS:
        inbox = chat.members[mid].inbox
        print(f"=== {mid} が受け取った（合計 {len(inbox)} 通）===")
        print(", ".join(inbox))
        print()

    # 成功判定（AはB/Cから、BはA/Cから、CはA/Bから：各 2*MSG_PER_USER 通）
    target_each = (len(GROUP_IDS)-1) * MSG_PER_USER
    ok = all(len(chat.members[mid].inbox) == target_each for mid in GROUP_IDS)
    print(f"信頼配送の判定：{'成功' if ok else '一部未達あり'}（各ノードは {target_each} 通受信すべき）")

if __name__ == "__main__":
    run_demo()
    