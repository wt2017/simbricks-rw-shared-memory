
Chain:
x86 CPU (gem5) → MemHostInterface → BasicInterconnect → MemDeviceInterface → BasicMem
     ↓                    ↓                    ↓                    ↓
  Gem5Sim         MemHostInterface    BasicInterconnect    BasicMem


1. CPU accesses 0x3FC0000
2. gem5 detects external memory access
3. Routes through MemHostInterface -> socket
4. BasicInterconnect receives on socket
5. Routes to MemDeviceInterface -> socket  
6. BasicMem processes memory request
7. Response follows reverse path
