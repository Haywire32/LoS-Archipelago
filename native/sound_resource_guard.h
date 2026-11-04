#pragma once
#include <windows.h>
#include <cstdint>
#include <cstring>
#include <cstdio>

// Retail 1.0.2.9 CSoundFMod::Load ignores CFile::Open failure before Size().
// The 2026-11-01 dump proves both stream backings null for WitchChild's
// AttackBoomInit_02.wav. Use its EXISTING destructor/skip branch, never fake a
// successful read, suppress an exception, or change the general file routines.
namespace los_sound_guard {
static constexpr std::uint32_t kSite=0x41f0fa, kResume=0x41f103;
static constexpr std::uint32_t kCleanup=0x41f13b, kSize=0x13ca0;
static std::uintptr_t sizeCall, resume, cleanup;
static const char* const* resourcePrefix;
static volatile LONG installed, reported, skipped;
static HANDLE logFile=INVALID_HANDLE_VALUE;
static SRWLOCK logLock=SRWLOCK_INIT;

inline void Log(const char* text) {
    DWORD saved=GetLastError();
    if(logFile!=INVALID_HANDLE_VALUE && TryAcquireSRWLockExclusive(&logLock)) {
        DWORD written;WriteFile(logFile,text,static_cast<DWORD>(strlen(text)),&written,nullptr);
        FlushFileBuffers(logFile);ReleaseSRWLockExclusive(&logLock);
    }
    SetLastError(saved);
}
inline void OpenLog(HMODULE self) {
    if(logFile!=INVALID_HANDLE_VALUE) return;
    wchar_t path[1024]{};if(!GetModuleFileNameW(self,path,1024)) return;
    wchar_t* slash=wcsrchr(path,L'\\');if(!slash) return;
    wcscpy_s(slash+1,1024-(slash+1-path),L"LoS-sound-guard.log");
    logFile=CreateFileW(path,FILE_APPEND_DATA,FILE_SHARE_READ|FILE_SHARE_WRITE,nullptr,OPEN_ALWAYS,0,nullptr);
    LARGE_INTEGER length{};
    if(logFile!=INVALID_HANDLE_VALUE && GetFileSizeEx(logFile,&length) && length.QuadPart>1024*1024) {
        CloseHandle(logFile);
        logFile=CreateFileW(path,FILE_APPEND_DATA,FILE_SHARE_READ|FILE_SHARE_WRITE,nullptr,CREATE_ALWAYS,0,nullptr);
    }
}
inline void Copy(char* dest,size_t size,const char* src) {
    size_t i=0;
    __try { if(src) for(;i+1<size && src[i];++i) dest[i]=(src[i]=='\r'||src[i]=='\n')?' ':src[i]; }
    __except(EXCEPTION_EXECUTE_HANDLER) { i=0; }
    dest[i]=0;
}
static void __cdecl Missing(const char* name) {
    LONG count=InterlockedIncrement(&skipped);
    if(count>200) return; // bounded diagnostics even if an unavailable cue repeats
    char prefix[300]{},file[300]{},line[750];
    const char* p=nullptr;
    __try { if(resourcePrefix) p=*resourcePrefix; }
    __except(EXCEPTION_EXECUTE_HANDLER) {}
    Copy(prefix,sizeof(prefix),p);Copy(file,sizeof(file),name);
    _snprintf_s(line,_TRUNCATE,"pid=%lu skipped unavailable sound #%ld: %s%s; retail cleanup\r\n",GetCurrentProcessId(),count,prefix,file);
    Log(line);
    if(count==200) Log("Further missing-sound log entries suppressed for this process. Guard remains active.\r\n");
}

// Entered by JMP at the exact verified instruction boundary: no extra return
// address. Original stack layout and SEH state remain owned by CSoundFMod::Load.
// +18 is the CFile object; +0c is FILE*, +14 is archive backing.
__declspec(naked) static void Guard() {
    __asm {
        cmp dword ptr [esp+24h],0
        jne valid
        cmp dword ptr [esp+2ch],0
        jne valid
        pushfd
        pushad
        lea eax,[esp+12ch] // original esp+108h filename, plus 36 saved bytes
        push eax
        call Missing
        add esp,4
        popad
        popfd
        jmp dword ptr [cleanup]
    valid:
        lea ecx,[esp+18h]
        call dword ptr [sizeCall]
        jmp dword ptr [resume]
    }
}

inline bool Signature(const unsigned char* base) {
    // All compared instructions are position-independent. Includes complete
    // instructions at both replay and failure destinations, not just the hook.
    const unsigned char before[]={0x6a,1,0x8d,0x84,0x24,0x0c,1,0,0,0x50,0x8d,0x4c,0x24,0x20,0xe8,0x4a,0xd5,0xbe,0xff};
    const unsigned char site[]={0x8d,0x4c,0x24,0x18,0xe8,0x9d,0x4b,0xbf,0xff};
    const unsigned char end[]={0xc7,0x84,0x24,0x18,2,0,0,0xff,0xff,0xff,0xff,0x8d,0x4c,0x24,0x18,0xe8,0x8e,9,0xbf,0xff,0xe9,0x4a,1,0,0};
    // Size wrapper dispatches between archive backing and the stdio adapter.
    const unsigned char sizeThunk[]={0xe9,0xdb,0xb8,3,0};
    const unsigned char sizeBody[]={0x83,0x79,0x14,0,0x75,5,0xe9,0xf7,0xb0,0xfb,0xff,0x8b,0x41,0x18,0xc3};
    return !memcmp(base+0x41f0e7,before,sizeof(before)) && !memcmp(base+kSite,site,sizeof(site)) &&
           !memcmp(base+kCleanup,end,sizeof(end)) && !memcmp(base+kSize,sizeThunk,sizeof(sizeThunk)) &&
           !memcmp(base+0x4f580,sizeBody,sizeof(sizeBody));
}
inline bool InstallAt(unsigned char* base,std::size_t bytes,std::uint32_t timestamp) {
    if(installed) return true;
    if(timestamp!=0x522464eb || bytes<0xa13664 || !Signature(base)) return false;
    // Only invoked on the game's input/window thread, before loading a level.
    DWORD old;if(!VirtualProtect(base+kSite,9,PAGE_EXECUTE_READWRITE,&old)) return false;
    sizeCall=reinterpret_cast<std::uintptr_t>(base)+kSize;
    resume=reinterpret_cast<std::uintptr_t>(base)+kResume;
    cleanup=reinterpret_cast<std::uintptr_t>(base)+kCleanup;
    resourcePrefix=reinterpret_cast<const char* const*>(base+0xa13660);
    unsigned char branch[9]={0xe9,0,0,0,0,0x90,0x90,0x90,0x90};
    auto relative=static_cast<std::uint32_t>(reinterpret_cast<std::uintptr_t>(&Guard)-reinterpret_cast<std::uintptr_t>(base+kSite+5));
    memcpy(branch+1,&relative,4);memcpy(base+kSite,branch,9);
    FlushInstructionCache(GetCurrentProcess(),base+kSite,9);
    DWORD ignored;VirtualProtect(base+kSite,9,old,&ignored);
    InterlockedExchange(&installed,1);Log("ARMED sound resource guard v1: failed opens use retail sound cleanup; valid sounds unchanged.\r\n");
    return true;
}
inline void Install(HMODULE self) {
    if(installed) return;
    OpenLog(self);
    __try {
        auto* base=reinterpret_cast<unsigned char*>(GetModuleHandleW(nullptr));
        auto* dos=reinterpret_cast<IMAGE_DOS_HEADER*>(base);
        if(dos->e_magic!=IMAGE_DOS_SIGNATURE) return;
        auto* nt=reinterpret_cast<IMAGE_NT_HEADERS*>(base+dos->e_lfanew);
        if(nt->Signature!=IMAGE_NT_SIGNATURE) return;
        if(!InstallAt(base,nt->OptionalHeader.SizeOfImage,nt->FileHeader.TimeDateStamp) &&
           !InterlockedExchange(&reported,1))
            Log("NOT ARMED: executable not yet unpacked, unsupported signature, or write protection failed; will retry on window thread.\r\n");
    } __except(EXCEPTION_EXECUTE_HANDLER) {}
}
} // namespace los_sound_guard
