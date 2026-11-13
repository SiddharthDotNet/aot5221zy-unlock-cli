"""The tested two-field LAN SSH configuration recipe."""

import xml.etree.ElementTree as ET


def apply_lan_ssh(root, username=None):
    """Stage the tested XML recipe previously verified on this firmware.

    Sets the SSH management interface to LAN and its port, and, when the
    matching web login entry can be found, lowers that account's UserLevel
    to 0 (full admin) so the SSH service accepts it as an owner account.
    """
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

    if username:
        mgmt = root.find("X_5067F0_Ext/LoginPrivilegeMgmt")
        if mgmt is not None:
            for entry in mgmt:
                name = entry.find("UserName")
                if name is not None and name.text == username:
                    level = entry.find("UserLevel")
                    if level is not None:
                        level.text = "0"
                    break
