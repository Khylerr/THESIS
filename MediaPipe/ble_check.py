#!/usr/bin/env python3
"""BLE glove check: run this when fslRecorder can't connect to the glove.

1. Scans for 10 s and lists every BLE device (name, address, signal, whether it
   advertises the AISL glove service).
2. Connects to the glove, lists its services, subscribes, and counts data packets
   for 5 s (rate, packet size, dropped packets, first decoded values).

Run in VS Code (Run Python File) or:  python ble_check.py
Needs: pip install bleak
"""
import asyncio
import struct
import sys
import time

try:
    from bleak import BleakClient, BleakScanner
except ImportError:
    sys.exit(f"bleak is not installed for this Python. Run:\n  \"{sys.executable}\" -m pip install bleak")

NAME = "AISL_Glove"
SERVICE = "e1273d67-cf0f-4bb7-9477-4f5d92124a6f"
DATA = "ecbd02f0-3d5f-4ad5-952a-9e75b163eeab"
STATUS = "493ccb74-46cd-4966-8a16-ba3cca3fd116"
PACKET = struct.Struct("<HI5h3h3hB")


async def main():
    print(f"Python: {sys.executable}")
    print("Scanning for BLE devices (10 s)...\n")
    found = await BleakScanner.discover(timeout=10.0, return_adv=True)
    glove = None
    rows = sorted(found.values(), key=lambda da: -(da[1].rssi or -999))
    for dev, adv in rows:
        name = adv.local_name or dev.name or "(no name)"
        has_svc = SERVICE in [u.lower() for u in (adv.service_uuids or [])]
        is_glove = name == NAME or has_svc
        mark = "  <-- GLOVE" if is_glove else ""
        print(f"  {name:28s} {dev.address}  RSSI {adv.rssi:>4} dBm"
              f"  glove service: {'yes' if has_svc else 'no '}{mark}")
        if is_glove and glove is None:
            glove = dev
    print(f"\n{len(found)} device(s) found.")

    if glove is None:
        print(f"\nRESULT: '{NAME}' was NOT found in the BLE scan.")
        print("  - Is the glove powered and running hand_sign_glove_ble? (USB Serial Monitor at")
        print("    115200 should print 'BLE advertising as \"AISL_Glove\"')")
        print("  - Is a phone (nRF Connect / Serial Bluetooth Terminal) connected to it? Disconnect.")
        print("  - Is it paired in Windows Bluetooth settings? Remove it there, press EN, retry.")
        return

    print(f"\nConnecting to {glove.address} ...")
    n, sizes, seqs, first, status = 0, set(), [], None, []

    def on_data(_s, data):
        nonlocal n, first
        n += 1
        sizes.add(len(data))
        if len(data) == PACKET.size:
            v = PACKET.unpack(bytes(data))
            seqs.append(v[0])
            if first is None:
                first = v

    def on_status(_s, data):
        status.append(bytes(data).decode(errors="ignore"))

    t0 = time.perf_counter()
    try:
        async with BleakClient(glove, timeout=20.0) as client:
            print(f"  connected in {time.perf_counter() - t0:.1f} s, MTU {getattr(client, 'mtu_size', '?')}")
            for svc in client.services:
                tag = "  <-- glove service" if svc.uuid.lower() == SERVICE else ""
                print(f"  service {svc.uuid}{tag}")
                for ch in svc.characteristics:
                    print(f"     char {ch.uuid}  {','.join(ch.properties)}")
            await client.start_notify(STATUS, on_status)
            await client.start_notify(DATA, on_data)
            print("  receiving for 5 s ...")
            await asyncio.sleep(5.0)
    except Exception as e:
        print(f"\nRESULT: connection FAILED: {type(e).__name__}: {e}")
        print("  Most common fix on Windows: remove AISL_Glove from Settings > Bluetooth & devices,")
        print("  press EN on the ESP32, close any phone app connected to it, then run this again.")
        return

    dropped = sum(((b - a - 1) & 0xFFFF) for a, b in zip(seqs, seqs[1:]))
    print(f"\n  packets: {n} in 5 s = {n / 5:.1f} Hz   sizes: {sorted(sizes)} bytes   dropped: {dropped}")
    if first:
        seq, t_ms, *v = first
        print(f"  first packet: seq {seq}, t {t_ms} ms, flex {v[0:5]}, acc {v[5:8]}, gyro {v[8:11]}, flags {v[11]:08b}")
    for line in status[:5]:
        print(f"  glove status: {line}")
    if n == 0:
        print("\nRESULT: connected but NO data. Re-upload hand_sign_glove_ble and check the Serial Monitor.")
    elif sizes != {PACKET.size}:
        print(f"\nRESULT: packets have the wrong size (expected {PACKET.size}); BLE MTU too small?")
    else:
        print("\nRESULT: BLE glove OK. fslRecorder should connect.")


if __name__ == "__main__":
    asyncio.run(main())
