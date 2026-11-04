#pragma once

#include <cstdint>
#include <cstring>

// E182: the old numeric mailbox was serialized as an engine GVar. On the
// next process it was unknown, so retail treated its int payload as the length
// of the next GVar name. Only the TWO name reads in the config loader use this
// adapter. Values, gameplay saves and all other string reads remain retail.
namespace los_save_compat {
using ReadString = int(__thiscall*)(void*, char*, int);
using ReadBytes = int(__thiscall*)(void*, void*, int);

inline int ReadName(void* stream, char* name, int capacity,
                    ReadString read_string, ReadBytes read_bytes) {
    int count = read_string(stream, name, capacity);
    while (std::strcmp(name, "APBridgeCommandInt") == 0) {
        std::uint32_t discarded = 0;
        if (read_bytes(stream, &discarded, sizeof(discarded)) != sizeof(discarded)) {
            // A truncated legacy record is not a usable next name.
            name[0] = '\0';
            return count;
        }
        count += sizeof(discarded);
        count += read_string(stream, name, capacity);
    }
    return count;
}
}  // namespace los_save_compat
