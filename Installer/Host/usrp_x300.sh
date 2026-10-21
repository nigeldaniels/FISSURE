#!/bin/bash
prepare_usrp_x300() {
    # The dispatcher prepares UHD once, even when both names are selected.
    host_root sysctl -w net.core.wmem_max=24862979
    echo "[✓] X300/X310 socket buffer configured (reapply after reboot)."
}
