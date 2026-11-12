"""The tested two-field LAN SSH configuration recipe."""

import xml.etree.ElementTree as ET


def apply_lan_ssh(root):
    """Stage the two-leaf XML recipe previously verified on this firmware."""
    ssh = root.find("X_5067F0_RemoteMGMT/SSH")
    if ssh is None:
        raise ValueError(
            "This backup lacks the supported SSH management block. Download a fresh AOT5221ZY backup."
        )
    for tag, value, attributes in [
        ("Interface", "LAN", dict(TYPE="string", LENGTH="64")),
        ("Port", "2222", dict(TYPE="uint32", MAX="4294967295", MIN="0")),
    ]:
        leaf = ssh.find(tag)
        if leaf is None:
            leaf = ET.SubElement(ssh, tag, PARAMETER="configured", **attributes)
        leaf.text = value
