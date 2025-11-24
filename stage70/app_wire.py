# -*- coding: utf-8 -*-
# app_wire.py
import json

def send_control_message(ssl_obj, obj):
    data = json.dumps(obj, separators=(",", ":")).encode()
    ssl_obj.send(data + b"\n")

def handle_control_message(line_bytes: bytes, key_update_mgr):
    # line_bytes は1行ぶんの JSON バイト列
    obj = json.loads(line_bytes.decode())
    if obj.get("type") == "epoch_notice":
        peer_epoch = int(obj["epoch"])
        key_update_mgr.epoch = peer_epoch

