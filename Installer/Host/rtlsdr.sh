#!/bin/bash
prepare_rtlsdr() {
    printf '%s\n' 'blacklist dvb_usb_rtl28xxu' |
        host_root tee /etc/modprobe.d/rtl-sdr.conf >/dev/null
    host_root rm -f /etc/udev/rules.d/20.rtlsdr.rules
    printf '%s\n' 'SUBSYSTEM=="usb", ATTRS{idVendor}=="0bda", ATTRS{idProduct}=="2838", MODE:="0666"' |
        host_root tee /etc/udev/rules.d/99-fissure-rtlsdr.rules >/dev/null
    host_reload_udev
    echo "[✓] RTL-SDR access prepared; reconnect the device."
    echo "[i] Reboot may be needed if the DVB driver is already loaded."
}
