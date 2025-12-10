#!/usr/bin/env python3
"""
SimBricks experiment script: x86 application accessing external memory through SimBricks interface

System architecture:
Application(x86) --> gem5 x86 CPU --> SimBricks interface --> Target memory system

This script creates two components:
1. gem5 x86 system running shm_rw application
2. External memory system (can be simple memory model or other architecture)
"""

from simbricks.orchestration import system
from simbricks.orchestration import simulation as sim
from simbricks.orchestration import instantiation as inst
from simbricks.orchestration.helpers import instantiation as inst_helpers
from simbricks.orchestration.system import mem as sys_mem
from simbricks.orchestration.system import host as sys_host
from simbricks.orchestration.system import disk_images

# Create empty instantiations list that simbricks-run expects
instantiations = []

print("Creating experiment for x86 application accessing external memory through SimBricks...")
print("System architecture: Application(x86) --> gem5 x86 CPU --> SimBricks interface --> Target memory system")
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

# Note: Memory layout is handled by gem5 automatically
# The shared memory at 0x3FC0000 should be accessible within the 1GB range
# We'll rely on the SimBricks memory interconnect to handle the address mapping

host.add_disk(system.DistroDiskImage(sys, name="shm-rw"))
host.add_disk(system.LinuxConfigDiskImage(sys, host))

# Create shared memory device
shared_mem = sys_mem.MemSimpleDevice(sys)
shared_mem.name = "shared_mem"
shared_mem._addr = 0x3FC0000  # Physical address used by shm_rw
shared_mem._size = 4 * 1024 * 1024  # 4MB
shared_mem._as_id = 0

# x86 CPU (gem5) → MemHostInterface → BasicInterconnect → MemDeviceInterface → BasicMem
#     ↓                    ↓                    ↓                 ↓              ↓
#  Gem5Sim         MemHostInterface    MemInterconnect        _mem_if     MemSimpleDevice

mem_interconnect = sys_mem.MemInterconnect(sys)
mem_interconnect.name = "mem_interconnect"

# Connect the interconnect to the memory device (creates MemHostInterface on interconnect)
# This establishes the SimBricks memory connection that gem5 will detect
interconnect_channel = mem_interconnect.connect_device(shared_mem._mem_if)

# The correct approach is to create a MemHostInterface for the host first
# and then connect it to the interconnect
host_mem_if = sys_mem.MemHostInterface(host)
host_mem_if.name = "host_mem_if"

# Add the memory interface to the host component
host.add_if(host_mem_if)

# Connect the host memory interface to the interconnect
# This creates a MemChannel connecting the host interface to a device interface on the interconnect
host_mem_channel = mem_interconnect.connect_host(host_mem_if)

# Add memory route for the shared memory device
# This tells the interconnect how to route memory accesses to the device
# Find the MemHostInterface that was created when connecting the device
interconnect_host_if = None
for intf in mem_interconnect.interfaces():
    if isinstance(intf, sys_mem.MemHostInterface):
        interconnect_host_if = intf
        break

if interconnect_host_if:
    mem_interconnect.add_route(
        dev=interconnect_host_if,  # The interconnect's host interface
        vaddr=0x3FC0000,  # Virtual address (same as physical in this case)
        len=4 * 1024 * 1024,  # Length of the memory region
        paddr=0x3FC0000  # Physical address in the device
    )

print(f"Memory interconnect created")
print(f"Shared memory device: addr=0x{shared_mem._addr:x}, size={shared_mem._size} bytes")
print(f"Memory interconnect will bridge CPU accesses to external memory")

# Configure application - use correct concrete class
shm_rw_app = sys_host.app.GenericRawCommandApplication(host)
shm_rw_app.binary = "/home/wyou/shm_rw"
shm_rw_app.args = []
host.add_app(shm_rw_app)

# Create simulation configuration
simulation = sim.Simulation("shm_rw_simbricks_test", sys)

# Configure simulation parameters to prevent early exit
simulation.timeout = 600  # 60 seconds timeout
simulation.verbose = True  # Enable verbose output for debugging

# Configure component mapping
host_sim = sim.Gem5Sim(simulation)
host_sim.name = "x86_host_sim"
host_sim.add(host)

# Create BasicInterconnect simulator for the memory interconnect
interconnect_sim = sim.BasicInterconnect(simulation)
interconnect_sim.name = "mem_interconnect_sim"
interconnect_sim.add(mem_interconnect)

mem_sim = sim.BasicMem(simulation)
mem_sim.name = "shared_mem_sim"
mem_sim.add(shared_mem)

# Create instantiation
instantiation = inst_helpers.simple_instantiation(simulation)
fragment = inst.Fragment()
fragment.add_simulators(host_sim, interconnect_sim, mem_sim)
instantiation.fragments = [fragment]

# Add to instantiations list
instantiations.append(instantiation)

print(f"Experiment created successfully, containing {len(instantiations)} instantiations")
