"""Windows Job Object limits for untrusted child processes.

The module intentionally exposes a very small API.  Keeping the job handle
alive ties the child to a process-memory and CPU-time limit; closing it also
terminates any descendants that the child managed to create.
"""

from __future__ import annotations

from dataclasses import dataclass
import os
import subprocess
from typing import Self


if os.name == "nt":  # pragma: no branch - definitions are platform specific
    import ctypes
    from ctypes import wintypes

    ULONG_PTR = wintypes.WPARAM
    SIZE_T = ctypes.c_size_t

    class _IoCounters(ctypes.Structure):
        _fields_ = [
            ("ReadOperationCount", ctypes.c_ulonglong),
            ("WriteOperationCount", ctypes.c_ulonglong),
            ("OtherOperationCount", ctypes.c_ulonglong),
            ("ReadTransferCount", ctypes.c_ulonglong),
            ("WriteTransferCount", ctypes.c_ulonglong),
            ("OtherTransferCount", ctypes.c_ulonglong),
        ]

    class _BasicLimitInformation(ctypes.Structure):
        _fields_ = [
            ("PerProcessUserTimeLimit", ctypes.c_longlong),
            ("PerJobUserTimeLimit", ctypes.c_longlong),
            ("LimitFlags", wintypes.DWORD),
            ("MinimumWorkingSetSize", SIZE_T),
            ("MaximumWorkingSetSize", SIZE_T),
            ("ActiveProcessLimit", wintypes.DWORD),
            ("Affinity", ULONG_PTR),
            ("PriorityClass", wintypes.DWORD),
            ("SchedulingClass", wintypes.DWORD),
        ]

    class _ExtendedLimitInformation(ctypes.Structure):
        _fields_ = [
            ("BasicLimitInformation", _BasicLimitInformation),
            ("IoInfo", _IoCounters),
            ("ProcessMemoryLimit", SIZE_T),
            ("JobMemoryLimit", SIZE_T),
            ("PeakProcessMemoryUsed", SIZE_T),
            ("PeakJobMemoryUsed", SIZE_T),
        ]

    _kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    _kernel32.CreateJobObjectW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR]
    _kernel32.CreateJobObjectW.restype = wintypes.HANDLE
    _kernel32.SetInformationJobObject.argtypes = [
        wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD
    ]
    _kernel32.SetInformationJobObject.restype = wintypes.BOOL
    _kernel32.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
    _kernel32.AssignProcessToJobObject.restype = wintypes.BOOL
    _kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    _kernel32.CloseHandle.restype = wintypes.BOOL

    _JOB_OBJECT_EXTENDED_LIMIT_INFORMATION = 9
    _JOB_OBJECT_LIMIT_PROCESS_TIME = 0x00000002
    _JOB_OBJECT_LIMIT_PROCESS_MEMORY = 0x00000100
    _JOB_OBJECT_LIMIT_DIE_ON_UNHANDLED_EXCEPTION = 0x00000400
    _JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x00002000


@dataclass(slots=True)
class WindowsJobLimit:
    """Own a configured Job Object until the attached process has exited."""

    _handle: int

    @classmethod
    def attach(
        cls,
        process: subprocess.Popen[bytes],
        *,
        memory_limit_mb: int,
        cpu_limit_ms: int,
    ) -> WindowsJobLimit | None:
        if os.name != "nt":
            return None
        handle = _kernel32.CreateJobObjectW(None, None)
        if not handle:
            return None
        limits = _ExtendedLimitInformation()
        limits.BasicLimitInformation.LimitFlags = (
            _JOB_OBJECT_LIMIT_PROCESS_TIME
            | _JOB_OBJECT_LIMIT_PROCESS_MEMORY
            | _JOB_OBJECT_LIMIT_DIE_ON_UNHANDLED_EXCEPTION
            | _JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        )
        # Windows measures user-mode CPU in 100 ns units.  A small startup
        # allowance avoids treating interpreter initialization as learner CPU.
        limits.BasicLimitInformation.PerProcessUserTimeLimit = max(
            2_000, int(cpu_limit_ms) * 2
        ) * 10_000
        limits.ProcessMemoryLimit = int(memory_limit_mb) * 1024 * 1024
        configured = _kernel32.SetInformationJobObject(
            handle,
            _JOB_OBJECT_EXTENDED_LIMIT_INFORMATION,
            ctypes.byref(limits),
            ctypes.sizeof(limits),
        )
        process_handle = getattr(process, "_handle", None)
        assigned = bool(
            configured
            and process_handle
            and _kernel32.AssignProcessToJobObject(handle, process_handle)
        )
        if not assigned:
            _kernel32.CloseHandle(handle)
            return None
        return cls(int(handle))

    def close(self) -> None:
        if os.name == "nt" and self._handle:
            _kernel32.CloseHandle(self._handle)
            self._handle = 0

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *_args: object) -> None:
        self.close()
