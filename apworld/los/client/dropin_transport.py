from __future__ import annotations

import ctypes
from ctypes import wintypes
import threading


class DropInUnavailable(RuntimeError):
    pass


MAPPING_NAME = "Local\\LoSArchipelagoDropInBridgeV1"
REQUEST_EVENT_NAME = "Local\\LoSArchipelagoDropInRequestV1"
RESPONSE_EVENT_NAME = "Local\\LoSArchipelagoDropInResponseV1"
MAGIC = 0x4C534450
VERSION = 1

HOST_READY = 1
COMMAND_READY = 2
COMPLETE = 4
FAILED = 5

FILE_MAP_ALL_ACCESS = 0xF001F
EVENT_MODIFY_STATE = 0x0002
SYNCHRONIZE = 0x00100000
WAIT_OBJECT_0 = 0


class SharedCommand(ctypes.Structure):
    _pack_ = 4
    _fields_ = (
        ("magic", ctypes.c_uint32),
        ("version", ctypes.c_uint32),
        ("state", ctypes.c_int32),
        ("target_pid", ctypes.c_uint32),
        ("target_thread_id", ctypes.c_uint32),
        ("target_window", ctypes.c_uint32),
        ("sequence", ctypes.c_uint32),
        ("executor_address", ctypes.c_uint32),
        ("result_pointer_address", ctypes.c_uint32),
        ("exception_code", ctypes.c_uint32),
        ("command", ctypes.c_char * 131072),
        ("cleanup_command", ctypes.c_char * 1024),
        ("result", ctypes.c_char * 8192),
        ("error", ctypes.c_char * 512),
    )


if ctypes.sizeof(SharedCommand) != 140840:
    raise RuntimeError("The Lords of Shadow drop-in bridge layout is invalid.")


def _windows_api():
    if not hasattr(ctypes, "WinDLL"):
        raise DropInUnavailable("The drop-in bridge is only available on Windows.")
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.OpenFileMappingW.argtypes = (
        wintypes.DWORD,
        wintypes.BOOL,
        wintypes.LPCWSTR,
    )
    kernel32.OpenFileMappingW.restype = wintypes.HANDLE
    kernel32.MapViewOfFile.argtypes = (
        wintypes.HANDLE,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.DWORD,
        ctypes.c_size_t,
    )
    kernel32.MapViewOfFile.restype = ctypes.c_void_p
    kernel32.OpenEventW.argtypes = (
        wintypes.DWORD,
        wintypes.BOOL,
        wintypes.LPCWSTR,
    )
    kernel32.OpenEventW.restype = wintypes.HANDLE
    kernel32.SetEvent.argtypes = (wintypes.HANDLE,)
    kernel32.SetEvent.restype = wintypes.BOOL
    kernel32.ResetEvent.argtypes = (wintypes.HANDLE,)
    kernel32.ResetEvent.restype = wintypes.BOOL
    kernel32.WaitForSingleObject.argtypes = (wintypes.HANDLE, wintypes.DWORD)
    kernel32.WaitForSingleObject.restype = wintypes.DWORD
    kernel32.UnmapViewOfFile.argtypes = (ctypes.c_void_p,)
    kernel32.UnmapViewOfFile.restype = wintypes.BOOL
    kernel32.CloseHandle.argtypes = (wintypes.HANDLE,)
    kernel32.CloseHandle.restype = wintypes.BOOL
    return kernel32


class DropInTransport:
    """Synchronous IPC to the DLL loaded by Lords of Shadow itself."""

    def executable_path(self):
        from pathlib import Path
        api=ctypes.WinDLL('kernel32',use_last_error=True)
        api.OpenProcess.argtypes=(wintypes.DWORD,wintypes.BOOL,wintypes.DWORD)
        api.OpenProcess.restype=wintypes.HANDLE
        api.QueryFullProcessImageNameW.argtypes=(wintypes.HANDLE,wintypes.DWORD,wintypes.LPWSTR,ctypes.POINTER(wintypes.DWORD))
        api.QueryFullProcessImageNameW.restype=wintypes.BOOL
        api.CloseHandle.argtypes=(wintypes.HANDLE,)
        handle=api.OpenProcess(0x1000,False,self._shared.target_pid)
        if not handle:raise DropInUnavailable('Cannot locate the running game executable')
        try:
            buffer=ctypes.create_unicode_buffer(32768);size=wintypes.DWORD(len(buffer))
            if not api.QueryFullProcessImageNameW(handle,0,buffer,ctypes.byref(size)):
                raise DropInUnavailable('Cannot read the running game path')
            return Path(buffer.value)
        finally:api.CloseHandle(handle)

    def __init__(self) -> None:
        self._api = _windows_api()
        self._mapping = self._api.OpenFileMappingW(
            FILE_MAP_ALL_ACCESS, False, MAPPING_NAME
        )
        if not self._mapping:
            raise DropInUnavailable(
                "CastlevaniaLoSUE.exe is not running or dinput8.dll is not installed"
            )
        self._view = self._api.MapViewOfFile(
            self._mapping, FILE_MAP_ALL_ACCESS, 0, 0, ctypes.sizeof(SharedCommand)
        )
        self._request = self._api.OpenEventW(
            EVENT_MODIFY_STATE | SYNCHRONIZE, False, REQUEST_EVENT_NAME
        )
        self._response = self._api.OpenEventW(
            EVENT_MODIFY_STATE | SYNCHRONIZE, False, RESPONSE_EVENT_NAME
        )
        if not self._view or not self._request or not self._response:
            self.close()
            raise DropInUnavailable("The in-game bridge is still starting")
        self._shared = SharedCommand.from_address(self._view)
        if self._shared.magic != MAGIC or self._shared.version != VERSION:
            self.close()
            raise DropInUnavailable("The installed game bridge has the wrong version")
        if self._shared.state == 0:
            self.close()
            raise DropInUnavailable("The in-game bridge is still starting")
        self._sequence = 0
        self._lock = threading.Lock()

    def close(self) -> None:
        self._shared = None
        view = getattr(self, "_view", None)
        if view:
            self._api.UnmapViewOfFile(view)
            self._view = None
        for name in ("_response", "_request", "_mapping"):
            handle = getattr(self, name, None)
            if handle:
                self._api.CloseHandle(handle)
                setattr(self, name, None)

    @staticmethod
    def _read_text(value) -> str:
        return bytes(value).split(b"\0", 1)[0].decode("utf-8", errors="replace")

    @staticmethod
    def _encoded(value: str, capacity: int, label: str) -> bytes:
        encoded = value.encode("utf-8")
        if len(encoded) >= capacity:
            raise DropInUnavailable(f"The {label} is too large for the game bridge")
        return encoded

    def execute(
        self,
        lua: str,
        *,
        cleanup: str = 'Game.Set("InitLuaLine","")',
        timeout: float = 20.0,
    ) -> str:
        command = self._encoded(lua, 131072, "Lua command")
        cleanup_command = self._encoded(cleanup, 1024, "cleanup command")
        with self._lock:
            if self._shared is None:
                raise DropInUnavailable("The in-game bridge is closed")
            self._sequence = (self._sequence + 1) & 0xFFFFFFFF
            if self._sequence == 0:
                self._sequence = 1
            self._api.ResetEvent(self._response)
            self._shared.sequence = self._sequence
            self._shared.command = command
            self._shared.cleanup_command = cleanup_command
            self._shared.result = b""
            self._shared.error = b""
            self._shared.exception_code = 0
            self._shared.state = COMMAND_READY
            if not self._api.SetEvent(self._request):
                raise DropInUnavailable("The in-game bridge request could not be sent")
            wait = self._api.WaitForSingleObject(
                self._response, max(1, int(timeout * 1000))
            )
            if wait != WAIT_OBJECT_0:
                raise DropInUnavailable("The game did not answer the bridge request")
            state = int(self._shared.state)
            result = self._read_text(self._shared.result)
            error = self._read_text(self._shared.error)
            if state != COMPLETE:
                detail = error or f"bridge command failed in state {state}"
                if self._shared.exception_code:
                    detail += f" (exception 0x{self._shared.exception_code:08X})"
                raise DropInUnavailable(detail)
            self._shared.state = HOST_READY
            return result

    @property
    def target_pid(self) -> int:
        return int(self._shared.target_pid) if self._shared is not None else 0
