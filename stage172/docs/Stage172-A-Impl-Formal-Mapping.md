# Stage172-A
## QSP Implementation ↔ Formal Model Mapping

---

## 1. Handshake / Authentication

| 実装要素 | 対応Tamarin lemma | 仮定 | 非ゴール | PoC検証 |
|---------|------------------|------|----------|---------|
|         |                  |      |          |         |

---

## 2. Key Derivation / Key Separation

| 実装要素 | 対応Tamarin lemma | 仮定 | 非ゴール | PoC検証 |
|---------|------------------|------|----------|---------|
|         |                  |      |          |         |
| hkdf-based key mixing (PQC + QKD + transcript) | lemma key_separation_and_binding | HKDFは理想PRFとして扱う | 鍵長・アルゴリズム強度評価は非対象 | 実QKD入力・異種実装間での鍵一致検証 |


---

## 3. Rekey / Epoch Management

| 実装要素 | 対応Tamarin lemma | 仮定 | 非ゴール | PoC検証 |
|---------|------------------|------|----------|---------|
|         |                  |      |          |         |
| epoch mismatch check | lemma fail_closed_on_epoch_mismatch | 正当な当事者は epoch を単調増加させる | 可用性（DoS耐性）は保証しない | 実装間Interopでのepoch同期検証 |


---

## 4. Application Data Protection

| 実装要素 | 対応Tamarin lemma | 仮定 | 非ゴール | PoC検証 |
|---------|------------------|------|----------|---------|
| handshake completion gate | lemma no_data_before_handshake | 正当なハンドシェイク完了が前提 | 早期データ(0-RTT)は非対応 | 他実装とのhandshake状態遷移検証 |


---

## 5. QKD / PQC Fallback

| 実装要素 | 対応Tamarin lemma | 仮定 | 非ゴール | PoC検証 |
|---------|------------------|------|----------|---------|


---

## 6. Global Assumptions

- 署名方式は EUF-CMA 安全であると仮定する
- HKDF / AEAD は理想的暗号プリミティブとして扱う
- 乱数生成（nonce / key material）は十分に予測不能である
- 物理QKDの量子特性（QBER等）は形式モデルの対象外とする



---

## 7. Non-Goals

(TBD)

---

## 8. Items for PoC Validation

(TBD)
