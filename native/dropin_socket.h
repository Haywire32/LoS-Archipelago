// Included inside the proxy namespace after transport creation. Socket I/O runs
// on its own thread; only the established window-thread bridge executes Lua.
#pragma comment(lib, "ws2_32.lib")

std::wstring SocketPath(const wchar_t* name) {
    wchar_t path[32768]{};
    GetModuleFileNameW(g_proxy_module, path, 32768);
    std::wstring dir(path);
    dir.resize(dir.find_last_of(L"\\/") + 1);
    return dir + L"APEnemy\\" + name;
}

void SocketLog(const char* message) {
    auto path = SocketPath(L"bridge.log");
    WIN32_FILE_ATTRIBUTE_DATA info{};
    if (GetFileAttributesExW(path.c_str(), GetFileExInfoStandard, &info) && info.nFileSizeLow > 1048576)
        MoveFileExW(path.c_str(), SocketPath(L"bridge.previous.log").c_str(), MOVEFILE_REPLACE_EXISTING);
    HANDLE f = CreateFileW(path.c_str(), FILE_APPEND_DATA, FILE_SHARE_READ | FILE_SHARE_WRITE,
                          nullptr, OPEN_ALWAYS, FILE_ATTRIBUTE_NORMAL, nullptr);
    if (f == INVALID_HANDLE_VALUE) return;
    SYSTEMTIME t; GetSystemTime(&t);
    char line[1024];
    sprintf_s(line, "%04u-%02u-%02uT%02u:%02u:%02uZ pid=%lu %s\r\n",
              t.wYear,t.wMonth,t.wDay,t.wHour,t.wMinute,t.wSecond,GetCurrentProcessId(),message);
    DWORD n; WriteFile(f,line,static_cast<DWORD>(strlen(line)),&n,nullptr); CloseHandle(f);
}

bool SocketIO(SOCKET s, char* data, int size, bool writing) {
    while (size > 0) {
        int n = writing ? send(s,data,size,0) : recv(s,data,size,0);
        if (n <= 0) return false;
        data += n; size -= n;
    }
    return true;
}
struct SocketFrame { char magic[4]; uint32_t kind, sequence, size; };
static_assert(sizeof(SocketFrame)==16, "socket header");
bool SocketReply(SOCKET s, uint32_t kind, uint32_t seq, const std::string& text) {
    SocketFrame h{{'L','S','A','P'},kind,seq,static_cast<uint32_t>(text.size())};
    return SocketIO(s,reinterpret_cast<char*>(&h),sizeof(h),true) &&
           SocketIO(s,const_cast<char*>(text.data()),static_cast<int>(text.size()),true);
}
bool SocketRead(SOCKET s, SocketFrame& h, std::string& text) {
    if (!SocketIO(s,reinterpret_cast<char*>(&h),sizeof(h),false)) return false;
    if (memcmp(h.magic,"LSAP",4) || h.size>140840 || !h.sequence) return false;
    text.resize(h.size);
    return SocketIO(s,text.data(),static_cast<int>(h.size),false);
}

DWORD WINAPI SocketWorker(LPVOID) {
    SocketLog("0.7.6 socket worker starting (loopback only)");
    WSADATA ws{};
    if (WSAStartup(MAKEWORD(2,2),&ws)) { SocketLog("WSAStartup failed"); return 1; }
    SOCKET listener=socket(AF_INET,SOCK_STREAM,IPPROTO_TCP);
    sockaddr_in address{};address.sin_family=AF_INET;address.sin_addr.s_addr=htonl(INADDR_LOOPBACK);
    if (listener==INVALID_SOCKET || bind(listener,reinterpret_cast<sockaddr*>(&address),sizeof(address)) || listen(listener,2)) {
        SocketLog("listener creation/bind failed"); if(listener!=INVALID_SOCKET)closesocket(listener);WSACleanup();return 2;
    }
    int length=sizeof(address);getsockname(listener,reinterpret_cast<sockaddr*>(&address),&length);
    unsigned char random[32];
    if (BCryptGenRandom(nullptr,random,sizeof(random),BCRYPT_USE_SYSTEM_PREFERRED_RNG)<0) {
        SocketLog("random token generation failed");closesocket(listener);WSACleanup();return 3;
    }
    char token[65];for(int i=0;i<32;++i)sprintf_s(token+i*2,3,"%02x",random[i]);
    char endpoint[256];sprintf_s(endpoint,"{\"protocol\":1,\"port\":%u,\"pid\":%lu,\"token\":\"%s\"}\n",ntohs(address.sin_port),GetCurrentProcessId(),token);
    auto temp=SocketPath(L"bridge.json.tmp");
    HANDLE f=CreateFileW(temp.c_str(),GENERIC_WRITE,FILE_SHARE_READ,nullptr,CREATE_ALWAYS,FILE_ATTRIBUTE_NORMAL,nullptr);
    DWORD written=0;
    bool published=f!=INVALID_HANDLE_VALUE && WriteFile(f,endpoint,static_cast<DWORD>(strlen(endpoint)),&written,nullptr) && written==strlen(endpoint);
    if(f!=INVALID_HANDLE_VALUE){FlushFileBuffers(f);CloseHandle(f);}
    if(!published || !MoveFileExW(temp.c_str(),SocketPath(L"bridge.json").c_str(),MOVEFILE_REPLACE_EXISTING|MOVEFILE_WRITE_THROUGH)) {
        SocketLog("endpoint publish failed: APEnemy must be writable");closesocket(listener);WSACleanup();return 4;
    }
    SocketLog("endpoint published; waiting for native client; credentials omitted");
    for (;;) {
        SOCKET client=accept(listener,nullptr,nullptr);if(client==INVALID_SOCKET){SocketLog("accept failed");Sleep(250);continue;}
        BOOL no_delay=TRUE;setsockopt(client,IPPROTO_TCP,TCP_NODELAY,reinterpret_cast<char*>(&no_delay),sizeof(no_delay));
        DWORD limit=5000;
        setsockopt(client,SOL_SOCKET,SO_RCVTIMEO,reinterpret_cast<char*>(&limit),sizeof(limit));
        setsockopt(client,SOL_SOCKET,SO_SNDTIMEO,reinterpret_cast<char*>(&limit),sizeof(limit));
        SocketFrame h{};std::string body;
        if(!SocketRead(client,h,body) || h.kind!=1 || body!=token) {
            SocketLog("client handshake rejected");closesocket(client);continue;
        }
        char hello[96];sprintf_s(hello,"%lu|0.7.6|%ld",GetCurrentProcessId(),g_shared->state);
        if(!SocketReply(client,1,h.sequence,hello)){closesocket(client);continue;}
        SocketLog("client authenticated");uint32_t previous=h.sequence;
        limit=30000;setsockopt(client,SOL_SOCKET,SO_RCVTIMEO,reinterpret_cast<char*>(&limit),sizeof(limit));
        while(SocketRead(client,h,body)) {
            uint32_t expected=previous+1;if(!expected)expected=1;
            if(h.kind!=2 || h.sequence!=expected || body.size()<8)break;
            previous=h.sequence;
            uint32_t command_size=0,cleanup_size=0;
            memcpy(&command_size,body.data(),4);memcpy(&cleanup_size,body.data()+4,4);
            if(command_size>=sizeof(g_shared->command) || cleanup_size>=sizeof(g_shared->cleanup_command) ||
               body.size()!=8+command_size+cleanup_size || memchr(body.data()+8,0,command_size+cleanup_size))break;
            if(g_shared->state!=kHostReady) {
                SocketReply(client,3,h.sequence,"Game bridge not ready: wait at main menu; see APEnemy/bridge.log.");break;
            }
            ResetEvent(g_response_event);
            memcpy(g_shared->command,body.data()+8,command_size);g_shared->command[command_size]=0;
            memcpy(g_shared->cleanup_command,body.data()+8+command_size,cleanup_size);g_shared->cleanup_command[cleanup_size]=0;
            g_shared->sequence=h.sequence;g_shared->result[0]=0;g_shared->error[0]=0;g_shared->exception_code=0;
            MemoryBarrier();InterlockedExchange(&g_shared->state,kCommandReady);SetEvent(g_request_event);
            DWORD start=GetTickCount();DWORD wait=WaitForSingleObject(g_response_event,20000);
            if(wait!=WAIT_OBJECT_0) {
                SocketLog("request timeout: no replay; mailbox held until window thread finishes");
                SocketReply(client,3,h.sequence,"Game window did not answer within 20 seconds. Request was not replayed. Collect bridge.log.");
                // Never overwrite an in-flight command after a disconnect or timeout.
                WaitForSingleObject(g_response_event,INFINITE);
                InterlockedExchange(&g_shared->state,kHostReady);break;
            }
            bool ok=g_shared->state==kComplete;
            std::string answer=ok?g_shared->result:g_shared->error;
            char summary[200];sprintf_s(summary,"request seq=%u bytes=%u elapsed_ms=%lu state=%ld exception=%08x",h.sequence,command_size,GetTickCount()-start,g_shared->state,g_shared->exception_code);
            if(!ok || h.sequence%64==0 || GetTickCount()-start>2000)SocketLog(summary);
            if(!ok)SocketLog(g_shared->error);
            InterlockedExchange(&g_shared->state,kHostReady);
            if(!SocketReply(client,ok?2:3,h.sequence,answer))break;
        }
        closesocket(client);SocketLog("client disconnected; accepting reconnect");
    }
}
