#!/usr/bin/env python3
"""
Memory Proxy Component SimBricks experiment script

This script implements a memory proxy component approach where:
1. A memory controller component sits between the host and interconnect
2. The memory controller has the MemHostInterface that Gem5Sim processes
3. The memory controller connects to the interconnect for external memory access
4. This isolates the MemHostInterface from the LinuxHost component

System architecture:
Application(x86) --> gem5 x86 CPU --> Memory Controller --> BasicInterconnect --> External memory
"""

from simbricks.orchestration import system
from simbricks.orchestration import simulation as sim
from simbricks.orchestration import instantiation as inst
from simbricks.orchestration.helpers import instantiation as inst_helpers
from simbricks.orchestration.system import mem as sys_mem
from simbricks.orchestration.system import host as sys_host
from simbricks.orchestration.system import disk_images
from simbricks.orchestration.system import base as sys_base

# Create empty instantiations list that simbricks-run expects
instantiations = []

print("Creating memory proxy component experiment...")
print("System architecture: Host → Memory Controller → BasicInterconnect → External memory")
print(f"Shared memory address: 0x3FC0000")
print(f"Shared memory size: 4MB")
print("Expected output: [shared_bmk] PASS: all 1024 bytes match")

# Create system
sys = system.System()

# Create x86 host
host = sys_host.LinuxHost(sys)
host.name = "x86_host"
host.memory = 1024  # 1GB memory
host.cores = 1
host.cpu_freq = "3GHz"

host.add_disk(system.DistroDiskImage(sys, name="shm-rw"))
host.add_disk(system.LinuxConfigDiskImage(sys, host))

# Create external memory device
external_mem = sys_mem.MemSimpleDevice(sys)
external_mem.name = "external_mem"
external_mem._addr = 0x3FC0000  # Physical address used by shm_rw
external_mem._size = 4 * 1024 * 1024  # 4MB
external_mem._as_id = 0

# Create memory proxy/controller component
# This component will sit between the host and interconnect
# It will have the MemHostInterface that Gem5Sim processes
class MemoryProxy(sys_base.Component):
    def __init__(self, s: sys_base.System):
        super().__init__(s)
        self.name = "memory_proxy"
        # Create a MemHostInterface that Gem5Sim will process
        self._mem_if = sys_mem.MemHostInterface(self)
        self._mem_if.name = "proxy_mem_if"
        self.add_if(self._mem_if)

# Create the memory proxy component
mem_proxy = MemoryProxy(sys)

# Create memory interconnect for external memory access
mem_interconnect = sys_mem.MemInterconnect(sys)
mem_interconnect.name = "mem_interconnect"

# Connect the interconnect to the external memory device
interconnect_channel = mem_interconnect.connect_device(external_mem._mem_if)

# Connect the memory proxy to the interconnect
# This creates a MemDeviceInterface on the interconnect
proxy_channel = mem_interconnect.connect_host(mem_proxy._mem_if)

# Add memory route for the external memory device
interconnect_host_if = None
for intf in mem_interconnect.interfaces():
    if isinstance(intf, sys_mem.MemHostInterface):
        interconnect_host_if = intf
        break

if interconnect_host_if:
    mem_interconnect.add_route(
        dev=interconnect_host_if,
        vaddr=0x3FC0000,
        len=4 * 1024 * 1024,
        paddr=0x3FC0000
    )

# Now connect the host to the memory proxy
# This creates a special connection that doesn't use MemHostInterface directly
# The host will access memory through the proxy component

# For this to work, we need to establish a connection between host and proxy
# Let's try using a custom interface or channel that Gem5Sim doesn't process as memory

# Create a custom interface for host-to-proxy communication
class HostProxyInterface(sys_base.Interface):
    def __init__(self, c: sys_base.Component):
        super().__init__(c)

# Add this interface to both host and proxy
host_proxy_if = HostProxyInterface(host)
host_proxy_if.name = "host_proxy_if"
host.add_if(host_proxy_if)

proxy_host_if = HostProxyInterface(mem_proxy)
proxy_host_if.name = "proxy_host_if"
mem_proxy.add_if(proxy_host_if)

# Connect them with a custom channel
class HostProxyChannel(sys_base.Channel):
    def __init__(self, host_if: HostProxyInterface, proxy_if: HostProxyInterface):
        super().__init__(host_if, proxy_if)

host_proxy_channel = HostProxyChannel(host_proxy_if, proxy_host_if)

print(f"Memory proxy component created")
print(f"External memory device: addr=0x{external_mem._addr:x}, size={external_mem._size} bytes")
print(f"Memory proxy will bridge host accesses to external memory through interconnect")

# Configure application
shm_rw_app = sys_host.app.GenericRawCommandApplication(host)
shm_rw_app.binary = "/home/wyou/shm_rw"
shm_rw_app.args = []
host.add_app(shm_rw_app)

# Create simulation configuration
simulation = sim.Simulation("shm_rw_simbricks_proxy_test", sys)
simulation.timeout = 60
simulation.verbose = True

# Configure component mapping
host_sim = sim.Gem5Sim(simulation)
host_sim.name = "x86_host_sim"
host_sim.add(host)

# Add the memory proxy component to the same simulator as the host
# This way, Gem5Sim will process the proxy's MemHostInterface
host_sim.add(mem_proxy)

# Create BasicInterconnect for the external memory system
interconnect_sim = sim.BasicInterconnect(simulation)
interconnect_sim.name = "mem_interconnect_sim"
interconnect_sim.add(mem_interconnect)

# Create BasicMem for the external memory device
mem_sim = sim.BasicMem(simulation)
mem_sim.name = "external_mem_sim"
mem_sim.add(external_mem)

# Create instantiation
instantiation = inst_helpers.simple_instantiation(simulation)
fragment = inst.Fragment()
fragment.add_simulators(host_sim, interconnect_sim, mem_sim)
instantiation.fragments = [fragment]

# Add to instantiations list
instantiations.append(instantiation)

print(f"Memory proxy component experiment created successfully, containing {len(instantiations)} instantiations")
print("This approach isolates the MemHostInterface from the LinuxHost while providing external memory access")
