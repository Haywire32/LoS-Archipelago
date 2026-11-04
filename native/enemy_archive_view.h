#pragma once
// Redirect only the supported Data00 file to a private, delete-on-close view.
// The OS still owns reads, seeks, mapped views and asynchronous completion.
// No Lua/native engine call occurs inside this file hook.
#include <bcrypt.h>
#include <vector>
#include <algorithm>
#pragma comment(lib, "bcrypt.lib")

namespace los_archive_view {
using Open = decltype(&CreateFileA);
static Open original_open = &CreateFileA;
static SRWLOCK lock = SRWLOCK_INIT;
static std::wstring archive_path, patch_path, log_path, view_path;
static HANDLE view_owner = INVALID_HANDLE_VALUE;
static bool attempted = false, installed = false;

inline void Log(const char* text) {
    HANDLE f = CreateFileW(log_path.c_str(), FILE_APPEND_DATA, FILE_SHARE_READ,
                          nullptr, OPEN_ALWAYS, FILE_ATTRIBUTE_NORMAL, nullptr);
    if (f == INVALID_HANDLE_VALUE) return;
    DWORD n;
    WriteFile(f, text, static_cast<DWORD>(strlen(text)), &n, nullptr);
    WriteFile(f, "\r\n", 2, &n, nullptr);
    CloseHandle(f);
}
inline bool Hash(const unsigned char* p, size_t n, const unsigned char* expected) {
    unsigned char digest[32];
    return n <= MAXDWORD &&
        [&]() {
            BCRYPT_ALG_HANDLE alg = nullptr;
            if (BCryptOpenAlgorithmProvider(&alg, BCRYPT_SHA256_ALGORITHM, nullptr, 0) < 0) return false;
            auto status = BCryptHash(alg, nullptr, 0, const_cast<PUCHAR>(p),
                                     static_cast<ULONG>(n), digest, sizeof(digest));
            BCryptCloseAlgorithmProvider(alg, 0);
            return status >= 0 && memcmp(digest, expected, 32) == 0;
        }();
}
inline bool Load(const std::wstring& path, std::vector<unsigned char>& data, DWORD limit) {
    HANDLE f = CreateFileW(path.c_str(), GENERIC_READ, FILE_SHARE_READ, nullptr,
                          OPEN_EXISTING, FILE_ATTRIBUTE_NORMAL, nullptr);
    if (f == INVALID_HANDLE_VALUE) return false;
    LARGE_INTEGER size{};
    bool ok = GetFileSizeEx(f, &size) && size.QuadPart > 0 && size.QuadPart <= limit;
    if (ok) {
        data.resize(static_cast<size_t>(size.QuadPart));
        DWORD got = 0;
        ok = ReadFile(f, data.data(), static_cast<DWORD>(data.size()), &got, nullptr) && got == data.size();
    }
    CloseHandle(f);
    return ok;
}
inline DWORD U32(const unsigned char* p) { DWORD n; memcpy(&n, p, 4); return n; }

inline bool Prepare() {
    if (attempted) return view_owner != INVALID_HANDLE_VALUE;
    attempted = true;
    std::vector<unsigned char> patch, data;
    if (!Load(patch_path, patch, 128 * 1024 * 1024) || patch.size() < 80 ||
        memcmp(patch.data(), "LOSAV001", 8) != 0) { Log("ERROR: missing/invalid archive-view.bin"); return false; }
    const DWORD size = U32(patch.data() + 8), count = U32(patch.data() + 12);
    if (size != 214517551 || count != 52 || !Hash(patch.data()+80, patch.size()-80, patch.data()+48) ||
        !Load(archive_path, data, size) || data.size() != size ||
        !Hash(data.data(), data.size(), patch.data()+16)) {
        Log("ERROR: retail archive or view checksum mismatch"); return false;
    }
    size_t cursor = 80, previous = 0;
    for (DWORD i = 0; i < count; ++i) {
        if (patch.size()-cursor < 72) { Log("ERROR: truncated view"); return false; }
        const auto* r = patch.data()+cursor;
        size_t offset = U32(r), length = U32(r+4);
        cursor += 72;
        if (!length || offset < previous || offset > data.size() || length > data.size()-offset ||
            length > patch.size()-cursor || !Hash(data.data()+offset, length, r+8) ||
            !Hash(patch.data()+cursor, length, r+40)) { Log("ERROR: invalid view region"); return false; }
        memcpy(data.data()+offset, patch.data()+cursor, length);
        previous = offset + length; cursor += length;
    }
    if (cursor != patch.size()) { Log("ERROR: trailing view data"); return false; }
    wchar_t directory[MAX_PATH], temporary[MAX_PATH];
    DWORD n = GetTempPathW(MAX_PATH, directory);
    if (!n || n >= MAX_PATH || !GetTempFileNameW(directory, L"LAP", 0, temporary)) {
        Log("ERROR: temporary archive path unavailable"); return false;
    }
    HANDLE f = CreateFileW(temporary, GENERIC_READ | GENERIC_WRITE, FILE_SHARE_READ | FILE_SHARE_WRITE | FILE_SHARE_DELETE,
                          nullptr, TRUNCATE_EXISTING, FILE_ATTRIBUTE_TEMPORARY | FILE_FLAG_DELETE_ON_CLOSE, nullptr);
    if (f == INVALID_HANDLE_VALUE) { DeleteFileW(temporary); Log("ERROR: cannot create private archive view"); return false; }
    DWORD written = 0;
    if (!WriteFile(f, data.data(), static_cast<DWORD>(data.size()), &written, nullptr) ||
        written != data.size() || !FlushFileBuffers(f)) {
        CloseHandle(f); Log("ERROR: incomplete private archive view"); return false;
    }
    view_path = temporary;
    view_owner = f; // OS deletes the temporary view when the process releases its handles.
    Log("READY: 52 early-loader regions; original Data00.dat unchanged");
    return true;
}
inline bool IsArchive(const char* name) {
    if (!name) return false;
    wchar_t wide[MAX_PATH], full[MAX_PATH];
    if (!MultiByteToWideChar(CP_ACP, 0, name, -1, wide, MAX_PATH)) return false;
    DWORD n = GetFullPathNameW(wide, MAX_PATH, full, nullptr);
    return n && n < MAX_PATH && _wcsicmp(full, archive_path.c_str()) == 0;
}
inline HANDLE WINAPI OpenArchive(LPCSTR name, DWORD access, DWORD sharing,
    LPSECURITY_ATTRIBUTES security, DWORD creation, DWORD flags, HANDLE template_file) {
    if (!IsArchive(name)) return original_open(name, access, sharing, security, creation, flags, template_file);
    // Never redirect writes or truncate/create operations into the virtual file.
    if (creation != OPEN_EXISTING || (access & (GENERIC_WRITE | DELETE | FILE_WRITE_DATA | FILE_APPEND_DATA))) {
        SetLastError(ERROR_ACCESS_DENIED); return INVALID_HANDLE_VALUE;
    }
    AcquireSRWLockExclusive(&lock);
    bool ready = false;
    try { ready = Prepare(); } catch (...) { Log("ERROR: archive view allocation failed"); }
    HANDLE result = INVALID_HANDLE_VALUE;
    if (ready) result = CreateFileW(view_path.c_str(), access, sharing | FILE_SHARE_DELETE | FILE_SHARE_WRITE,
                                   security, creation, flags, template_file);
    DWORD error = ready ? GetLastError() : ERROR_INVALID_DATA;
    ReleaseSRWLockExclusive(&lock);
    SetLastError(error);
    return result;
}
inline bool Install(HMODULE proxy) {
    if (installed) return true;
    wchar_t path[MAX_PATH];
    if (!GetModuleFileNameW(proxy, path, MAX_PATH)) return false;
    std::wstring bin(path); bin.resize(bin.find_last_of(L"\\/"));
    patch_path = bin + L"\\APEnemy\\archive-view.bin";
    log_path = bin + L"\\APEnemy\\archive-view.log";
    // Optional feature: old skill-only installations remain unchanged.
    if (GetFileAttributesW(patch_path.c_str()) == INVALID_FILE_ATTRIBUTES) return false;
    archive_path = bin.substr(0, bin.find_last_of(L"\\/")) + L"\\Data00.dat";
    auto* base = reinterpret_cast<unsigned char*>(GetModuleHandleW(nullptr));
    auto* dos = reinterpret_cast<IMAGE_DOS_HEADER*>(base);
    auto* nt = reinterpret_cast<IMAGE_NT_HEADERS*>(base + dos->e_lfanew);
    auto dir = nt->OptionalHeader.DataDirectory[IMAGE_DIRECTORY_ENTRY_IMPORT];
    if (!dir.VirtualAddress) return false;
    auto* desc = reinterpret_cast<IMAGE_IMPORT_DESCRIPTOR*>(base + dir.VirtualAddress);
    for (; desc->Name; ++desc) {
        auto* slot = reinterpret_cast<IMAGE_THUNK_DATA*>(base + desc->FirstThunk);
        for (; slot->u1.Function; ++slot) {
            if (slot->u1.Function != reinterpret_cast<ULONG_PTR>(&CreateFileA)) continue;
            DWORD protection;
            if (!VirtualProtect(&slot->u1.Function, sizeof(ULONG_PTR), PAGE_READWRITE, &protection)) return false;
            InterlockedExchangePointer(reinterpret_cast<PVOID volatile*>(&slot->u1.Function), reinterpret_cast<void*>(&OpenArchive));
            DWORD ignored; VirtualProtect(&slot->u1.Function, sizeof(ULONG_PTR), protection, &ignored);
            installed = true;
        }
    }
    Log(installed ? "ARMED: native CreateFileA archive view" : "ERROR: CreateFileA import not found");
    return installed;
}
} // namespace los_archive_view
