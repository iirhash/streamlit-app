# -*- coding: utf-8 -*-
"""
Created on Mon Jun 22 08:30:53 2026

@author: Karina Nur C
"""

# utils.py  – shared helpers for all instrument tools
import streamlit as st
import random
from datetime import datetime


def rssi_bars_html(rssi):
    strength = max(0, min(4, int((rssi + 100) / 12.5)))
    bars = ""
    for i in range(4):
        h   = 5 + i * 4
        col = "#00aaff" if i < strength else "#1a1d28"
        bars += f'<div style="display:inline-block;width:5px;height:{h}px;background:{col};border-radius:1px;margin-right:2px;vertical-align:bottom"></div>'
    return f'<span>{bars}</span>'


def fake_hex_packet(value):
    raw = int(abs(value) * 100) & 0xFFFF
    b0  = 0x3A
    b1  = (raw >> 8) & 0xFF
    b2  = raw & 0xFF
    b3  = 0x00
    b4  = (b0 ^ b1 ^ b2 ^ b3) & 0xFF
    return f"{b0:02X} {b1:02X} {b2:02X} {b3:02X} {b4:02X}"


def add_packet(value, direction="RX"):
    if "bt_packets" not in st.session_state:
        st.session_state.bt_packets = []
    pkt = {
        "time": datetime.now().strftime("%H:%M:%S.%f")[:-4],
        "dir":  direction,
        "hex":  fake_hex_packet(value),
        "dec":  f"{value:.3f}",
    }
    st.session_state.bt_packets.insert(0, pkt)
    if len(st.session_state.bt_packets) > 30:
        st.session_state.bt_packets = st.session_state.bt_packets[:30]


def send_bt_capture(meas_mm, unit, target, tol):
    val    = meas_mm if unit == "mm" else meas_mm / 25.4
    tgt    = target  if unit == "mm" else target  / 25.4
    tl     = tol     if unit == "mm" else tol     / 25.4
    passed = abs(val - tgt) <= tl
    add_packet(meas_mm, "TX")
    if "bt_log" not in st.session_state:
        st.session_state.bt_log = []
    st.session_state.bt_log.insert(0, {
        "time":   datetime.now().strftime("%H:%M:%S.%f")[:-3],
        "value":  f"{val:.3f} {unit}",
        "raw_mm": meas_mm,
        "passed": passed,
    })


def disp_val(mm, unit, offset=0.0):
    v = mm - offset
    return v if unit == "mm" else v / 25.4


def in_tol(val, target, tol):
    return abs(val - target) <= tol


def mm_to_in(v):
    return v / 25.4