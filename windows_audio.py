"""Read Windows recording endpoint settings without changing them."""
from contextlib import ExitStack, contextmanager
import ctypes as ct
from dataclasses import dataclass
import os
from uuid import UUID


@dataclass(frozen=True)
class InputStatus:
    muted: bool
    volume: float


def _guid(value):
    return (ct.c_ubyte * 16).from_buffer_copy(UUID(value).bytes_le)


def _check(result, operation):
    if result < 0:
        raise OSError(f'{operation} falhou (HRESULT 0x{result & 0xFFFFFFFF:08X})')


def _method(interface, slot, result, *argtypes):
    pointer = ct.c_void_p
    vtable = ct.cast(interface, ct.POINTER(ct.POINTER(pointer))).contents
    function = ct.WINFUNCTYPE(result, pointer, *argtypes)(vtable[slot])
    return lambda *args: function(interface, *args)


def _release(interface):
    _method(interface, 2, ct.c_ulong)()  # IUnknown::Release


@contextmanager
def _com():
    ole = ct.WinDLL('ole32')
    ptr = ct.c_void_p
    hresult = ct.c_long
    ole.CoInitializeEx.argtypes = (ptr, ct.c_ulong)
    ole.CoInitializeEx.restype = hresult
    ole.CoUninitialize.argtypes = ()
    ole.CoUninitialize.restype = None

    with ExitStack() as cleanup:
        result = ole.CoInitializeEx(None, 0)  # COINIT_MULTITHREADED
        if result >= 0:
            cleanup.callback(ole.CoUninitialize)
        elif result & 0xFFFFFFFF != 0x80010106:  # Thread already has a different COM apartment.
            _check(result, 'CoInitializeEx')
        yield ole, cleanup


def default_input_status():
    if os.name != 'nt':
        return None
    ptr = ct.c_void_p
    out_ptr = ct.POINTER(ptr)
    hresult = ct.c_long
    with _com() as (ole, cleanup):
        ole.CoCreateInstance.argtypes = (ptr, ptr, ct.c_ulong, ptr, out_ptr)
        ole.CoCreateInstance.restype = hresult
        enumerator = ptr()
        _check(ole.CoCreateInstance(_guid('BCDE0395-E52F-467C-8E3D-C4579291692E'), None, 23,
                                    _guid('A95664D2-9614-4F35-A746-DE8DB63617E6'),
                                    ct.byref(enumerator)), 'IMMDeviceEnumerator')
        cleanup.callback(_release, enumerator)

        endpoint = ptr()
        get_default = _method(enumerator, 4, hresult, ct.c_int, ct.c_int, out_ptr)
        _check(get_default(1, 0, ct.byref(endpoint)), 'GetDefaultAudioEndpoint')  # eCapture, eConsole
        cleanup.callback(_release, endpoint)
        return _endpoint_status(endpoint)


def _endpoint_status(endpoint):
    ptr = ct.c_void_p
    hresult = ct.c_long
    with ExitStack() as cleanup:
        volume = ptr()
        activate = _method(endpoint, 3, hresult, ptr, ct.c_ulong, ptr, ct.POINTER(ptr))
        _check(activate(_guid('5CDF2C82-841E-4546-9722-0CF74078229A'), 23, None, ct.byref(volume)),
               'IAudioEndpointVolume')
        cleanup.callback(_release, volume)

        muted, level = ct.c_long(), ct.c_float()
        get_mute = _method(volume, 15, hresult, ct.POINTER(ct.c_long))
        get_level = _method(volume, 9, hresult, ct.POINTER(ct.c_float))
        _check(get_mute(ct.byref(muted)), 'GetMute')
        _check(get_level(ct.byref(level)), 'GetMasterVolumeLevelScalar')
        return InputStatus(bool(muted.value), level.value)


def wasapi_input_status(device_index, portaudio_library):
    if os.name != 'nt' or not portaudio_library:
        return None
    library = ct.CDLL(portaudio_library)
    get_endpoint = getattr(library, 'PaWasapi_GetIMMDevice', None)
    if get_endpoint is None:
        return None

    with _com():
        endpoint = ct.c_void_p()
        get_endpoint.argtypes = (ct.c_int, ct.POINTER(ct.c_void_p))
        get_endpoint.restype = ct.c_int
        if get_endpoint(device_index, ct.byref(endpoint)) != 0 or not endpoint:
            return None
        # The already-loaded PortAudio library owns this borrowed IMMDevice.
        return _endpoint_status(endpoint)


def warn_if_selected_input_muted(device_index, device_name, portaudio_library):
    try:
        status = wasapi_input_status(device_index, portaudio_library)
    except OSError:
        return
    if status and status.muted:
        print(f'O microfone selecionado [{device_index}] {device_name} esta silenciado no Windows '
              f'(volume {status.volume:.0%}). Verifica o botao de silencio em Som > Entrada.', flush=True)


def warn_if_default_input_muted():
    try:
        status = default_input_status()
    except OSError:
        return  # Core Audio diagnostics must not block other capture backends.
    if status and status.muted:
        print(f'A entrada padrao de gravacao do Windows esta silenciada (volume {status.volume:.0%}). '
              'Verifica Definicoes > Sistema > Som > Entrada.', flush=True)
