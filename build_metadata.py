"""Windows file properties for the branded desktop executable."""
def windows_version(name, version, filename):
    from PyInstaller.utils.win32.versioninfo import (
        VSVersionInfo, FixedFileInfo, StringFileInfo, StringTable, StringStruct,
        VarFileInfo, VarStruct,
    )
    numbers = tuple(int(part) for part in version.split('.'))
    numbers = (numbers + (0, 0, 0, 0))[:4]
    return VSVersionInfo(
        ffi=FixedFileInfo(filevers=numbers, prodvers=numbers, mask=0x3f, flags=0,
                          OS=0x40004, fileType=1, subtype=0, date=(0, 0)),
        kids=[StringFileInfo([StringTable('040904B0', [
            StringStruct('FileDescription', name), StringStruct('ProductName', name),
            StringStruct('FileVersion', version), StringStruct('ProductVersion', version),
            StringStruct('InternalName', 'OGStudioVideo'),
            StringStruct('OriginalFilename', filename),
        ])]), VarFileInfo([VarStruct('Translation', [1033, 1200])])],
    )
