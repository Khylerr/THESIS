"""Shared IDs for the AISL-A glove carrier project.

build_schematic.py and build_carrier_pcb.py both import this, so a schematic symbol and its
PCB footprint always carry the same UUID. That link is what lets KiCad's "schematic parity"
check and "Update PCB from Schematic" recognise them as the same part. Do not change
NAMESPACE: every UUID in both files would change.
"""
import uuid

PROJECT = "aisl_glove_carrier"
NAMESPACE = uuid.UUID("a15a0a15-6c0e-4000-8000-0000ca221e01")


def uid(key):
    """Deterministic UUID for a name, so regenerating a file gives the same IDs."""
    return str(uuid.uuid5(NAMESPACE, key))


ROOT_UUID = uid("root-sheet")


def symbol_uuid(ref):
    """UUID of the schematic symbol with this reference (U1, R3, ...)."""
    return uid("symbol:" + ref)


def nc_net(ref, pin_name, pad):
    """Net name KiCad gives a pin that carries a no-connect mark in the schematic."""
    if pin_name in ("", "~"):
        return "unconnected-(%s-Pad%s)" % (ref, pad)
    return "unconnected-(%s-%s-Pad%s)" % (ref, pin_name, pad)
