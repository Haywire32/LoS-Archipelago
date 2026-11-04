#define WIN32_LEAN_AND_MEAN
#include <winsock2.h>
#include <windows.h>
#include <unknwn.h>

#include <cstddef>
#include <cstdint>
#include <cstring>
#include <string>

#include "dropin_bridge_protocol.h"
#include "legacy_save_compat.h"
#include "enemy_archive_view.h"
#include "sound_resource_guard.h"

namespace {

using namespace los_dropin_bridge;
using LuaExecutor = void(__cdecl*)(const char*);
using DirectInput8CreateFn = HRESULT(WINAPI*)(HINSTANCE, DWORD, REFIID,
                                              LPVOID*, LPUNKNOWN);

constexpr std::uint32_t kLuaExecutorPointerRva = 0x009B1004;
constexpr std::uint32_t kInitLuaLineValuePointerRva = 0x00A50A6C;

HMODULE g_proxy_module = nullptr;
HMODULE g_real_dinput = nullptr;
DirectInput8CreateFn g_real_create = nullptr;
HANDLE g_mapping = nullptr;
HANDLE g_request_event = nullptr;
HANDLE g_response_event = nullptr;
SharedCommand* g_shared = nullptr;
HWND g_window = nullptr;
WNDPROC g_original_window_proc = nullptr;
bool g_socket_mode = false;
volatile LONG g_started = 0;
volatile LONG g_subclassed = 0;
bool g_legacy_save_compat_installed = false;
los_save_compat::ReadString g_retail_read_string = nullptr;

// The isolated development host supplies these. Retail always leaves them 0.
HWND g_test_window = nullptr;
std::uint32_t g_test_executor = 0;
std::uint32_t g_test_result_pointer = 0;

int __fastcall ReadConfigName(void* stream, void*, char* name, int capacity) {
    const auto vtable = *reinterpret_cast<std::uintptr_t**>(stream);
    const auto read_bytes = reinterpret_cast<los_save_compat::ReadBytes>(vtable[5]);
    return los_save_compat::ReadName(stream, name, capacity,
                                    g_retail_read_string, read_bytes);
}

void InstallLegacySaveCompatibility() {
    if (g_legacy_save_compat_installed || g_test_executor != 0) return;
    const auto base = reinterpret_cast<std::uintptr_t>(GetModuleHandleW(nullptr));
    // Supported retail build only. These are the two config NAME reads, not
    // the value reads at 0x4443C6 / 0x444419. Verify the unpacked instructions
    // before changing either call. Run only on the game's window thread.
    auto* first = reinterpret_cast<unsigned char*>(base + 0x44359);
    auto* next = reinterpret_cast<unsigned char*>(base + 0x4443F);
    const unsigned char first_expected[] = {0xE8, 0xCC, 0x23, 0xFD, 0xFF};
    const unsigned char next_expected[] = {0xE8, 0xE6, 0x22, 0xFD, 0xFF};
    const unsigned char reader_expected[] = {0x51, 0x53, 0x56, 0x57, 0x8B, 0xF1};
    __try {
        if (std::memcmp(first, first_expected, sizeof(first_expected)) != 0 ||
            std::memcmp(next, next_expected, sizeof(next_expected)) != 0 ||
            std::memcmp(reinterpret_cast<void*>(base + 0x4DBE0),
                        reader_expected, sizeof(reader_expected)) != 0) return;
        // Both sites are on one page: acquire write access before touching any
        // byte, and restore that page's original protection afterwards.
        DWORD old_protection = 0;
        if (!VirtualProtect(first, next - first + 5, PAGE_EXECUTE_READWRITE,
                            &old_protection)) return;
        g_retail_read_string = reinterpret_cast<los_save_compat::ReadString>(
            base + 0x4DBE0);
        const auto target = reinterpret_cast<std::uintptr_t>(&ReadConfigName);
        const std::uint32_t first_relative = static_cast<std::uint32_t>(
            target - reinterpret_cast<std::uintptr_t>(first + 5));
        const std::uint32_t next_relative = static_cast<std::uint32_t>(
            target - reinterpret_cast<std::uintptr_t>(next + 5));
        std::memcpy(first + 1, &first_relative, sizeof(first_relative));
        std::memcpy(next + 1, &next_relative, sizeof(next_relative));
        FlushInstructionCache(GetCurrentProcess(), first, next - first + 5);
        DWORD ignored = 0;
        VirtualProtect(first, next - first + 5, old_protection, &ignored);
        g_legacy_save_compat_installed = true;
        OutputDebugStringA("LoS AP: legacy mailbox save compatibility installed\n");
    } __except (EXCEPTION_EXECUTE_HANDLER) {
        // A packed/unsupported image is not patched. Retry on a later message.
    }
}

void CopyText(char* destination, std::size_t capacity, const char* source) {
    if (capacity == 0) return;
    std::size_t index = 0;
    if (source != nullptr) {
        __try {
            while (index + 1 < capacity && source[index] != '\0') {
                destination[index] = source[index];
                ++index;
            }
        } __except (EXCEPTION_EXECUTE_HANDLER) {
            destination[0] = '\0';
            return;
        }
    }
    destination[index] = '\0';
}

void SignalFailure(const char* message, std::uint32_t exception = 0) {
    if (g_shared == nullptr) return;
    g_shared->exception_code = exception;
    CopyText(g_shared->error, sizeof(g_shared->error), message);
    MemoryBarrier();
    InterlockedExchange(&g_shared->state, kFailed);
    if (g_response_event != nullptr) SetEvent(g_response_event);
}

bool ReadPointer(std::uintptr_t address, std::uint32_t& value) {
    __try {
        value = *reinterpret_cast<const std::uint32_t*>(address);
        return true;
    } __except (EXCEPTION_EXECUTE_HANDLER) {
        value = 0;
        return false;
    }
}

bool ResultLineIsEmpty(std::uint32_t result_pointer_address) {
    std::uint32_t value_pointer = 0;
    if (!ReadPointer(result_pointer_address, value_pointer) || value_pointer == 0) {
        return false;
    }
    __try {
        return *reinterpret_cast<const char*>(value_pointer) == '\0';
    } __except (EXCEPTION_EXECUTE_HANDLER) {
        return false;
    }
}

bool RestoreRetailWindowProcedure() {
    if (g_window == nullptr || g_original_window_proc == nullptr ||
        InterlockedCompareExchange(&g_subclassed, 0, 0) == 0) {
        return true;
    }
    SetLastError(0);
    const LONG_PTR previous = SetWindowLongPtrW(
        g_window, GWLP_WNDPROC,
        reinterpret_cast<LONG_PTR>(g_original_window_proc));
    if (previous == 0 && GetLastError() != 0) return false;
    InterlockedExchange(&g_subclassed, 0);
    return true;
}

LRESULT CALLBACK BridgeWindowProc(HWND window, UINT message, WPARAM w_param,
                                  LPARAM l_param);

bool InstallBridgeWindowProcedure(HWND window) {
    if (window == nullptr || !IsWindow(window)) return false;
    if (InterlockedCompareExchange(&g_subclassed, 0, 0) != 0 &&
        g_window == window) {
        return true;
    }
    SetLastError(0);
    const LONG_PTR previous = SetWindowLongPtrW(
        window, GWLP_WNDPROC, reinterpret_cast<LONG_PTR>(&BridgeWindowProc));
    if (previous == 0 && GetLastError() != 0) return false;
    g_window = window;
    g_original_window_proc = reinterpret_cast<WNDPROC>(previous);
    InterlockedExchange(&g_subclassed, 1);
    return g_original_window_proc != nullptr;
}

void RefreshRetailAddresses() {
    if (g_shared == nullptr) return;
    if (g_test_executor != 0 && g_test_result_pointer != 0) {
        g_shared->executor_address = g_test_executor;
        g_shared->result_pointer_address = g_test_result_pointer;
        return;
    }
    const auto base = reinterpret_cast<std::uintptr_t>(GetModuleHandleW(nullptr));
    std::uint32_t executor = 0;
    if (base != 0 && ReadPointer(base + kLuaExecutorPointerRva, executor)) {
        g_shared->executor_address = executor;
        g_shared->result_pointer_address = static_cast<std::uint32_t>(
            base + kInitLuaLineValuePointerRva);
    } else {
        g_shared->executor_address = 0;
        g_shared->result_pointer_address = 0;
    }
}

void ExecuteCommand() {
    if (g_shared == nullptr || g_shared->magic != kMagic ||
        g_shared->version != kVersion ||
        g_shared->target_pid != GetCurrentProcessId()) {
        SignalFailure("drop-in shared-command identity mismatch");
        return;
    }
    RefreshRetailAddresses();
    if (g_shared->executor_address == 0 ||
        g_shared->result_pointer_address == 0) {
        SignalFailure("the retail Lua executor is not ready");
        return;
    }
    if (!ResultLineIsEmpty(g_shared->result_pointer_address)) {
        SignalFailure("InitLuaLine was not safely empty; nothing was sent");
        return;
    }

    InterlockedExchange(&g_shared->state, kExecuting);
    auto executor = reinterpret_cast<LuaExecutor>(g_shared->executor_address);
    const char* result = nullptr;
    __try {
        executor(g_shared->command);
        result = *reinterpret_cast<const char**>(
            g_shared->result_pointer_address);
        CopyText(g_shared->result, sizeof(g_shared->result), result);
        if (g_shared->cleanup_command[0] != '\0') {
            executor(g_shared->cleanup_command);
        }
    } __except (EXCEPTION_EXECUTE_HANDLER) {
        SignalFailure("the retail Lua executor raised an exception",
                      GetExceptionCode());
        return;
    }

    g_shared->error[0] = '\0';
    g_shared->exception_code = 0;
    MemoryBarrier();
    InterlockedExchange(&g_shared->state, kComplete);
}

LRESULT CALLBACK BridgeWindowProc(HWND window, UINT message, WPARAM w_param,
                                  LPARAM l_param) {
    los_sound_guard::Install(g_proxy_module);
    InstallLegacySaveCompatibility();
    WNDPROC original = g_original_window_proc;
    if (message == kWindowMessage) {
        if (g_shared != nullptr && g_shared->state == kCommandReady &&
            g_shared->sequence == static_cast<std::uint32_t>(w_param)) {
            // Nested messages generated by the game Lua executor must go to the
            // retail procedure, not back through this bridge.
            RestoreRetailWindowProcedure();
            ExecuteCommand();
            if (IsWindow(window)) InstallBridgeWindowProcedure(window);
            if (g_response_event != nullptr) SetEvent(g_response_event);
        }
        return 0;
    }
    return original != nullptr
               ? CallWindowProcW(original, window, message, w_param, l_param)
               : DefWindowProcW(window, message, w_param, l_param);
}

struct WindowSearch {
    DWORD pid;
    HWND window;
};

BOOL CALLBACK FindWindowCallback(HWND window, LPARAM parameter) {
    auto* search = reinterpret_cast<WindowSearch*>(parameter);
    DWORD pid = 0;
    GetWindowThreadProcessId(window, &pid);
    if (pid == search->pid && GetWindow(window, GW_OWNER) == nullptr &&
        IsWindowVisible(window)) {
        search->window = window;
        return FALSE;
    }
    return TRUE;
}

HWND FindGameWindow() {
    if (g_test_window != nullptr && IsWindow(g_test_window)) return g_test_window;
    WindowSearch search{GetCurrentProcessId(), nullptr};
    EnumWindows(FindWindowCallback, reinterpret_cast<LPARAM>(&search));
    return search.window;
}

bool CreateTransport() {
    if (g_socket_mode) {
        // Private mailbox: a Windows shared-memory client cannot race the socket client.
        g_shared = static_cast<SharedCommand*>(VirtualAlloc(nullptr,sizeof(SharedCommand),MEM_COMMIT|MEM_RESERVE,PAGE_READWRITE));
    } else {
    g_mapping = CreateFileMappingW(INVALID_HANDLE_VALUE, nullptr, PAGE_READWRITE,
                                   0, sizeof(SharedCommand), kMappingName);
    if (g_mapping == nullptr) return false;
    g_shared = static_cast<SharedCommand*>(MapViewOfFile(
        g_mapping, FILE_MAP_ALL_ACCESS, 0, 0, sizeof(SharedCommand)));
    }
    if (g_shared == nullptr) return false;
    g_request_event = CreateEventW(nullptr, FALSE, FALSE, g_socket_mode ? nullptr : kRequestEventName);
    g_response_event = CreateEventW(nullptr, FALSE, FALSE, g_socket_mode ? nullptr : kResponseEventName);
    if (g_request_event == nullptr || g_response_event == nullptr) return false;
    std::memset(g_shared, 0, sizeof(SharedCommand));
    g_shared->magic = kMagic;
    g_shared->version = kVersion;
    g_shared->target_pid = GetCurrentProcessId();
    return true;
}

#include "dropin_socket.h"

DWORD WINAPI BridgeWorker(LPVOID) {
    SocketLog(g_socket_mode ? "bridge startup: Proton/loopback mode" : "bridge startup: Windows shared-memory mode");
    if (!CreateTransport()) { SocketLog("CreateTransport failed"); return 1; }
    if (g_socket_mode) {
        HANDLE socket_thread=CreateThread(nullptr,0,&SocketWorker,nullptr,0,nullptr);
        if(socket_thread)CloseHandle(socket_thread);else SocketLog("socket thread creation failed");
    }
    for (;;) {
        HWND window = FindGameWindow();
        if (window != nullptr && InstallBridgeWindowProcedure(window)) {
            g_shared->target_window = reinterpret_cast<std::uint32_t>(window);
            g_shared->target_thread_id = GetWindowThreadProcessId(window, nullptr);
            RefreshRetailAddresses();
            MemoryBarrier();
            InterlockedExchange(&g_shared->state, kHostReady);
            SocketLog("game window attached; Lua readiness checked per request");
            break;
        }
        Sleep(100);
    }

    for (;;) {
        const DWORD wait = WaitForSingleObject(g_request_event, INFINITE);
        if (wait != WAIT_OBJECT_0) return 2;
        if (g_shared->state != kCommandReady) continue;
        HWND window = FindGameWindow();
        if (window == nullptr || !InstallBridgeWindowProcedure(window)) {
            SignalFailure("the game window is not ready");
            continue;
        }
        g_shared->target_window = reinterpret_cast<std::uint32_t>(window);
        g_shared->target_thread_id = GetWindowThreadProcessId(window, nullptr);
        if (!PostMessageW(window, kWindowMessage,
                          static_cast<WPARAM>(g_shared->sequence), 0)) {
            SignalFailure("the game window rejected the bridge request");
        }
    }
}

void StartBridge() {
    if (InterlockedCompareExchange(&g_started, 1, 0) != 0) return;
    char forced[8]{};
    g_socket_mode = GetProcAddress(GetModuleHandleW(L"ntdll.dll"),"wine_get_version") != nullptr ||
        (GetEnvironmentVariableA("LOS_AP_SOCKET",forced,sizeof(forced)) && strcmp(forced,"1")==0);
    HANDLE thread = CreateThread(nullptr, 0, &BridgeWorker, nullptr, 0, nullptr);
    if (thread != nullptr) CloseHandle(thread);
}

bool ResolveRealDInput() {
    if (g_real_create != nullptr) return true;
    wchar_t system_directory[MAX_PATH]{};
    const UINT length = GetSystemDirectoryW(system_directory, MAX_PATH);
    if (length == 0 || length >= MAX_PATH - 12) return false;
    std::wstring path(system_directory, length);
    path += L"\\dinput8.dll";
    g_real_dinput = LoadLibraryW(path.c_str());
    if (g_real_dinput == nullptr) return false;
    g_real_create = reinterpret_cast<DirectInput8CreateFn>(
        GetProcAddress(g_real_dinput, "DirectInput8Create"));
    return g_real_create != nullptr;
}

}  // namespace

extern "C" HRESULT WINAPI ProxyDirectInput8Create(HINSTANCE instance,
                                                    DWORD version,
                                                    REFIID interface_id,
                                                    LPVOID* output,
                                                    LPUNKNOWN outer) {
    if (!ResolveRealDInput()) { SocketLog("system dinput8 forwarding failed"); return E_FAIL; }
    los_archive_view::Install(g_proxy_module);
    los_sound_guard::Install(g_proxy_module);
    StartBridge();
    return g_real_create(instance, version, interface_id, output, outer);
}

extern "C" __declspec(dllexport) DWORD WINAPI LoSAPBridgeStartForTest(
    HWND window, std::uint32_t executor, std::uint32_t result_pointer) {
    if (window == nullptr || executor == 0 || result_pointer == 0) return 0;
    g_test_window = window;
    g_test_executor = executor;
    g_test_result_pointer = result_pointer;
    StartBridge();
    return 1;
}

BOOL WINAPI DllMain(HINSTANCE instance, DWORD reason, LPVOID) {
    if (reason == DLL_PROCESS_ATTACH) {
        g_proxy_module = instance;
        DisableThreadLibraryCalls(instance);
        // Install the import redirect before the executable opens its archives.
        // This only edits a resolved IAT slot. Hashing/view construction waits
        // until the game's later CreateFile call, outside the loader lock.
        los_archive_view::Install(instance);
    }
    return TRUE;
}
