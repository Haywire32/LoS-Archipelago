#pragma once

#define WIN32_LEAN_AND_MEAN
#include <windows.h>

#include <cstdint>

namespace los_dropin_bridge {

constexpr wchar_t kMappingName[] =
    L"Local\\LoSArchipelagoDropInBridgeV1";
constexpr wchar_t kRequestEventName[] =
    L"Local\\LoSArchipelagoDropInRequestV1";
constexpr wchar_t kResponseEventName[] =
    L"Local\\LoSArchipelagoDropInResponseV1";
constexpr UINT kWindowMessage = WM_APP + 0x4C54;
constexpr std::uint32_t kMagic = 0x4C534450u;  // "LSDP"
constexpr std::uint32_t kVersion = 1;

enum State : LONG {
    kEmpty = 0,
    kHostReady = 1,
    kCommandReady = 2,
    kExecuting = 3,
    kComplete = 4,
    kFailed = 5,
};

// This layout is shared with the 64-bit Archipelago Python process. Keep every
// scalar explicitly 32-bit and retain four-byte packing.
#pragma pack(push, 4)
struct SharedCommand {
    std::uint32_t magic;
    std::uint32_t version;
    volatile LONG state;
    std::uint32_t target_pid;
    std::uint32_t target_thread_id;
    std::uint32_t target_window;
    std::uint32_t sequence;
    std::uint32_t executor_address;
    std::uint32_t result_pointer_address;
    std::uint32_t exception_code;
    char command[131072];
    char cleanup_command[1024];
    char result[8192];
    char error[512];
};
#pragma pack(pop)

static_assert(sizeof(SharedCommand) == 140840,
              "drop-in bridge protocol layout changed");

}  // namespace los_dropin_bridge
