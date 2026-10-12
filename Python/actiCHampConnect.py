"""Connect to a Brain Products actiCHamp (Plus) through EEG_SharedMemoryProducer.exe.

The producer (C++, see ../Producer) talks to the amplifier via the Brain Products
AmplifierSDK and publishes everything in a named Windows shared memory block
("EEG_SharedMemory"). This module starts the producer and reads that block:

    device = ActiCHampDevice()
    device.connect()                    # starts the producer, amplifier measures impedances
    imp = device.get_impedances()       # Ohm: [GND, REF, Ch1, Ch2, ...]
    device.start_acquisition(1000)      # leaves impedance mode, starts streaming
    data = device.get_data(5000)        # samples x channels
    device.disconnect()                 # stops the producer

The ctypes structures below must match ../Producer/SharedBuffer.h exactly.
Windows only (Win32 shared memory and vendor DLLs).
"""

import ctypes
import os
import subprocess
import time
from ctypes import wintypes
from pathlib import Path

import numpy as np

# --- must match Producer/SharedBuffer.h -------------------------------------
BUFFER_SIZE = 200000   # ring buffer length in samples
MAX_CHANNELS = 43      # columns per sample
SHM_NAME = "EEG_SharedMemory"
STOP_EVENT_NAME = "EEG_StopEvent"

FILE_MAP_ALL_ACCESS = 0xF001F
EVENT_MODIFY_STATE = 0x0002
SYNCHRONIZE = 0x00100000
CREATE_NO_WINDOW = 0x08000000
CREATE_NEW_CONSOLE = 0x00000010
PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
STILL_ACTIVE = 259

DEFAULT_PRODUCER_DIR = Path(__file__).resolve().parent.parent / "Producer"


class ControlBlock(ctypes.Structure):
    # std::atomic<float> = 4 bytes, std::atomic<bool> = 1 byte (MSVC x64)
    _fields_ = [
        ("targetSamplingRate", ctypes.c_float),
        ("stopRequested", ctypes.c_bool),
        ("useActiveElectrodes", ctypes.c_bool),
        # 19 further bool flags are reserved in SharedBuffer.h. The producer does not
        # evaluate them yet; they only have to be here so the layout stays identical.
        ("reservedFlags", ctypes.c_bool * 19),
    ]


class SharedBuffer(ctypes.Structure):
    _fields_ = [
        ("writeIndex", ctypes.c_int32),
        ("readIndex", ctypes.c_int32),
        ("data", (ctypes.c_float * MAX_CHANNELS) * BUFFER_SIZE),
        ("lostSamples", ctypes.c_int32),
        ("control", ControlBlock),
        ("impedances", ctypes.c_float * (MAX_CHANNELS + 2)),
        ("impSize", ctypes.c_int32),
        ("acquisitionReady", ctypes.c_bool),
    ]


class ActiCHampDevice:
    def __init__(self, producer_dir=DEFAULT_PRODUCER_DIR, timeout=10.0):
        """producer_dir: folder with EEG_SharedMemoryProducer.exe and the SDK DLLs.
        timeout: seconds to wait for the producer / the amplifier to respond."""
        self.producer_dir = Path(producer_dir)
        self.timeout = float(timeout)
        self.fs = 0.0
        self._process = None
        self._ptr = None      # address of the mapped view
        self._shm = None      # SharedBuffer living in the mapped view
        self._data = None     # numpy view on SharedBuffer.data

    # ------------------------------------------------------------------
    def connect(self):
        """Start the producer and attach to its shared memory.

        After this call the amplifier is in impedance mode until
        start_acquisition() is called.
        """
        if os.name != "nt":
            raise RuntimeError("The actiCHamp SDK is only available on Windows.")
        if self._shm is not None:
            raise RuntimeError("Already connected.")

        exe = self.producer_dir / "EEG_SharedMemoryProducer.exe"
        if not exe.exists():
            raise FileNotFoundError(f"Producer not found: {exe}")

        # A producer left over from a previous run still owns the amplifier. Close it first.
        self._close_running_producer(exe.name)

        # The shared memory can outlive the producer while another program (e.g. an open
        # MATLAB that used the MEX functions) still holds it. A new producer then reuses
        # the old block, so reset the fields it does not initialise itself.
        stale = self._open_mapping()
        if stale is not None:
            old = SharedBuffer.from_address(stale)
            old.control.targetSamplingRate = 0.0
            old.readIndex = 0
            old.impSize = 0
            old.acquisitionReady = False
            del old
            self._unmap(stale)

        # The producer needs its own folder as working directory (DLLs, *.bit files).
        # It gets its own console window that shows its output, as in MATLAB.
        self._process = subprocess.Popen(
            [str(exe)],
            cwd=str(self.producer_dir),
            creationflags=CREATE_NEW_CONSOLE,
        )

        deadline = time.time() + self.timeout
        while self._ptr is None:
            self._ptr = self._open_mapping()
            if self._ptr is None:
                self._check_producer_alive()
                if time.time() > deadline:
                    self.disconnect()
                    raise TimeoutError("Producer did not create the shared memory in time.")
                time.sleep(0.05)

        self._shm = SharedBuffer.from_address(self._ptr)
        self._data = np.ctypeslib.as_array(self._shm.data)  # shape (BUFFER_SIZE, MAX_CHANNELS)

        # The producer exits by itself if it finds no amplifier. Give it a moment.
        time.sleep(1.0)
        self._check_producer_alive()

    def get_impedances(self, wait=True):
        """Return the latest impedances in Ohm as [GND, REF, Ch1, Ch2, ...].

        Entries of channels that are not available are -1. Only possible before
        start_acquisition(): the amplifier cannot measure impedance and record
        EEG at the same time. Returns an empty array if nothing was measured yet
        (wait=False) or within the timeout.
        """
        self._require_connection()
        if self.fs > 0:
            raise RuntimeError(
                "Impedance can only be measured before start_acquisition(). "
                "Disconnect and connect again to measure impedances."
            )
        deadline = time.time() + self.timeout
        while self._shm.impSize <= 0:
            self._check_producer_alive()
            if not wait or time.time() > deadline:
                return np.array([])
            time.sleep(0.05)
        n = min(self._shm.impSize, MAX_CHANNELS + 2)
        return np.array(self._shm.impedances[:n], dtype=float)

    def start_acquisition(self, fs):
        """Leave impedance mode and start streaming with sampling rate fs (Hz).

        The producer maps fs to the nearest supported rate: 100, 200, 500, 1000,
        2000, 2500, 5000, 10000, 20000, 25000, 50000 or 100000 Hz. The applied
        rate is shown in the console window of the producer.
        """
        self._require_connection()
        if self.fs > 0:
            raise RuntimeError("Acquisition is already running. The sampling rate cannot be changed.")
        if fs <= 0:
            raise ValueError("fs must be positive.")
        self.fs = float(fs)
        self._shm.control.targetSamplingRate = self.fs

        deadline = time.time() + self.timeout
        while not self._shm.acquisitionReady:
            self._check_producer_alive()
            if time.time() > deadline:
                raise TimeoutError("Amplifier did not start the acquisition in time.")
            time.sleep(0.01)
        self.clear_buffer()

    def clear_buffer(self):
        """Drop all samples that are waiting in the ring buffer."""
        self._require_connection()
        self._shm.readIndex = self._shm.writeIndex

    def get_data(self, samples):
        """Block until `samples` new samples arrived and return them.

        Returns an array of shape (samples, 43), see README for the columns.
        Fewer rows are returned only if the producer stops in between.
        """
        self._require_connection()
        if self.fs <= 0:
            raise RuntimeError("Call start_acquisition(fs) before get_data().")

        samples = int(samples)
        out = np.zeros((samples, MAX_CHANNELS))
        # Generous limit so a stalled amplifier cannot block forever.
        deadline = time.time() + 3.0 * samples / self.fs + self.timeout

        copied = 0
        while copied < samples:
            read_idx = self._shm.readIndex
            available = self._shm.writeIndex - read_idx
            if available <= 0:
                self._check_producer_alive()
                if self._shm.control.stopRequested:
                    break
                if time.time() > deadline:
                    raise TimeoutError(f"Only {copied} of {samples} samples arrived.")
                time.sleep(0.001)
                continue

            n = min(available, samples - copied)
            start = read_idx % BUFFER_SIZE
            first = min(n, BUFFER_SIZE - start)          # part up to the end of the ring
            out[copied:copied + first] = self._data[start:start + first]
            out[copied + first:copied + n] = self._data[:n - first]  # wrapped part
            copied += n
            self._shm.readIndex = read_idx + n           # tell the producer what was consumed

        return out[:copied]

    def lost_samples(self):
        """Samples the producer had to drop because the ring buffer was full."""
        self._require_connection()
        return int(self._shm.lostSamples)

    def disconnect(self):
        """Stop the producer (releases the amplifier) and detach from the shared memory."""
        if self._shm is not None:
            self._shm.control.stopRequested = True
            self._signal_stop_event()

        if self._process is not None:
            try:
                self._process.wait(timeout=self.timeout)
            except subprocess.TimeoutExpired:
                self._process.kill()
            self._process = None

        self._data = None
        self._shm = None
        if self._ptr is not None:
            self._unmap(self._ptr)
            self._ptr = None
        self.fs = 0.0

    # ------------------------------------------------------------------
    @staticmethod
    def _producer_running(exe_name):
        tasks = subprocess.run(
            ["tasklist", "/FI", f"IMAGENAME eq {exe_name}", "/FO", "CSV", "/NH"],
            capture_output=True, text=True, errors="replace", creationflags=CREATE_NO_WINDOW,
        ).stdout
        kernel32 = ctypes.windll.kernel32
        kernel32.OpenProcess.restype = wintypes.HANDLE
        kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        kernel32.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
        kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
        for line in tasks.splitlines():
            fields = line.strip().strip('"').split('","')
            if len(fields) < 2 or fields[0].lower() != exe_name.lower():
                continue
            # tasklist also lists processes that already exited but are not cleaned up yet
            # (same test as Process.HasExited on the MATLAB side).
            handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, int(fields[1]))
            if not handle:
                return True
            code = wintypes.DWORD(STILL_ACTIVE)
            kernel32.GetExitCodeProcess(handle, ctypes.byref(code))
            kernel32.CloseHandle(handle)
            if code.value == STILL_ACTIVE:
                return True
        return False

    @staticmethod
    def _signal_stop_event():
        kernel32 = ctypes.windll.kernel32
        kernel32.OpenEventW.restype = wintypes.HANDLE
        kernel32.OpenEventW.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.LPCWSTR]
        kernel32.SetEvent.argtypes = [wintypes.HANDLE]
        kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
        event = kernel32.OpenEventW(EVENT_MODIFY_STATE | SYNCHRONIZE, False, STOP_EVENT_NAME)
        if event:
            kernel32.SetEvent(event)
            kernel32.CloseHandle(event)

    def _close_running_producer(self, exe_name):
        """Stop a producer that is already running, e.g. left over from a crashed script."""
        if not self._producer_running(exe_name):
            return
        print(f"{exe_name} is already running, closing it.")

        # Ask it to stop first, so it can release the amplifier properly.
        try:
            ptr = self._open_mapping()
        except RuntimeError:
            ptr = None   # producer with another layout, can only be killed
        if ptr is not None:
            SharedBuffer.from_address(ptr).control.stopRequested = True
            self._unmap(ptr)
        self._signal_stop_event()

        deadline = time.time() + self.timeout
        while self._producer_running(exe_name):
            if time.time() > deadline:
                subprocess.run(["taskkill", "/F", "/IM", exe_name],
                               capture_output=True, creationflags=CREATE_NO_WINDOW)
                time.sleep(0.5)
                if self._producer_running(exe_name):
                    raise RuntimeError(f"{exe_name} is still running and could not be closed.")
                break
            time.sleep(0.1)

    def _open_mapping(self):
        """Map the shared memory block. Returns its address or None if it does not exist."""
        kernel32 = ctypes.windll.kernel32
        kernel32.OpenFileMappingW.restype = wintypes.HANDLE
        kernel32.OpenFileMappingW.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.LPCWSTR]
        kernel32.MapViewOfFile.restype = ctypes.c_void_p
        kernel32.MapViewOfFile.argtypes = [wintypes.HANDLE, wintypes.DWORD, wintypes.DWORD,
                                           wintypes.DWORD, ctypes.c_size_t]
        kernel32.CloseHandle.argtypes = [wintypes.HANDLE]

        handle = kernel32.OpenFileMappingW(FILE_MAP_ALL_ACCESS, False, SHM_NAME)
        if not handle:
            return None
        # Fails if the block is smaller than our structure, i.e. the layouts differ.
        ptr = kernel32.MapViewOfFile(handle, FILE_MAP_ALL_ACCESS, 0, 0, ctypes.sizeof(SharedBuffer))
        kernel32.CloseHandle(handle)  # the view stays valid
        if not ptr:
            raise RuntimeError(
                "Shared memory layout mismatch. SharedBuffer in actiCHampConnect.py "
                "must match Producer/SharedBuffer.h."
            )
        return ptr

    @staticmethod
    def _unmap(ptr):
        kernel32 = ctypes.windll.kernel32
        kernel32.UnmapViewOfFile.argtypes = [wintypes.LPCVOID]
        kernel32.UnmapViewOfFile(ptr)

    def _require_connection(self):
        if self._shm is None:
            raise RuntimeError("Not connected. Call connect() first.")

    def _check_producer_alive(self):
        if self._process is not None and self._process.poll() is not None:
            code = self._process.returncode
            self.disconnect()
            raise RuntimeError(
                f"Producer exited (code {code}). Is the actiCHamp connected via USB, powered "
                f"and not in use by another program (e.g. BrainVision Recorder)?"
            )
